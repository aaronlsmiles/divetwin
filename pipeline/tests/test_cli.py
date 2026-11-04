import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

import cli

PIPELINE = Path(__file__).resolve().parent.parent


# ---- strict JSON and None-safe reading -------------------------------------------------------------

def test_dump_is_strict_and_keeps_scalar_lists_on_one_line(tmp_path):
    p = tmp_path / "x.json"
    cli._dump(p, {"a": [1.0, float("nan"), float("inf"), 3], "b": float("-inf"), "c": {"d": ["x", "y"]}, "e": []})
    text = p.read_text()
    got = json.loads(text, parse_constant=lambda c: pytest.fail(c))
    assert got == {"a": [1.0, None, None, 3], "b": None, "c": {"d": ["x", "y"]}, "e": []}
    assert '"a": [1.0, null, null, 3]' in text


def test_fmt_and_arrays_survive_none():
    assert cli._fmt(None) == "—" and cli._fmt(float("nan")) == "—" and cli._fmt(1.234) == "1.23"
    assert cli._fmt(None, none="n/a") == "n/a"
    a = cli._arr([1.0, None, 3.0])
    assert np.isnan(a[1]) and np.nanmedian(a) == 2.0
    assert cli._nan_summary([None, None]) == {"median": None, "max": None}
    assert cli._nan_summary([1.0, None, 5.0]) == {"median": 3.0, "max": 5.0}


def _entry(**kw):
    e = {"clip": "c1", "D": [None, 1.2, None], "verified": [0.9, None, 0.7], "path_disagreement": None,
         "path_disagreement_frame": 0, "travel": 120.0, "lost_from": 1, "primary_path": "icp", "far_end": None,
         "wall_frame": None, "far_end_valid": False}
    e.update(kw)
    return e


def test_summary_line_handles_none_everywhere():
    line = cli.summarize_entry(_entry())
    assert "D0=—" in line and "Vmin=0.70" in line and "disagree=—su" in line and "far_end=—" in line
    assert "D0 outside" in line                                    # an unreadable D0 is flagged
    ok = cli.summarize_entry(_entry(D=[1.1, 1.0], path_disagreement=12.0, far_end=1300.0, wall_frame=40))
    assert "D0=1.10" in ok and "disagree=12su (10% of travel" in ok and "wall=40" in ok and "D0 outside" not in ok
    cli.summarize_entry(_entry(D=[None], verified=[None], travel=None))  # nothing finite at all: no crash


@pytest.fixture(scope="module")
def small_tank():
    from camera import Pose
    from dive import make_tank
    from mapping import box_intrinsics
    from synth import corridor_colors, corridor_depth
    from units import Intrinsics
    k_real = Intrinsics(fx=830.0, fy=830.0, cx=639.5, cy=359.5, width=1280, height=720)
    fxb = 830.0 * 63.0
    k_half = box_intrinsics(k_real, (0.0, 0.0, 1280.0, 720.0), 640, 360)
    z = corridor_depth(k_half, Pose.identity())
    return make_tank("synthetic", k_real, fxb, ((fxb / z) / 2.0).astype(np.float32),
                     corridor_colors(k_half, Pose.identity(), z), floor=0.05, work=(640, 360))


def test_summary_reads_a_real_run_clip_entry(small_tank):
    """The entry run_clip writes for a clip lost at frame 1 is full of nulls; the summary must print it."""
    from camera import straight_path
    from dive import fill_nearest, run_clip
    from render import render
    k = small_tank.k_grid((0.0, 0.0, 1280.0, 720.0), 640, 360)
    frames, inv = [], []
    for i, p in enumerate(straight_path(n=6, travel=20.0)):
        rd = render(small_tank.mesh, k, p)
        frames.append(fill_nearest(rd.color, rd.seen) if i < 1 else np.full((360, 640, 3), 128, np.uint8))
        inv.append(fill_nearest(np.nan_to_num(rd.inv_depth), rd.seen))
    entry, _ = run_clip(small_tank, frames, np.array(inv), None, (0.0, 0.0, 1280.0, 720.0), primary="tracks", clip_id="lost1")
    assert entry["lost_from"] == 1 and entry["path_disagreement"] is None
    assert any(v is None for v in entry["D"])                       # the case this guards against
    line = cli.summarize_entry(entry)
    assert line.startswith("lost1")


# ---- Gate S ----------------------------------------------------------------------------------------

def _info(start, kind, tail):
    return {"start": start, "kind": kind, "tail": tail}


def test_gate_s_rules():
    assert cli.gate_s_reason(_info(396, "empty", [386, 396]), False) is None
    assert cli.gate_s_reason(_info(396, "empty", [386, 396]), True) is None
    assert cli.gate_s_reason(_info(351, "quiet", [291, 351]), False) is not None
    assert cli.gate_s_reason(_info(351, "quiet", [291, 351]), True) is None        # --allow-quiet, with a tail
    assert cli.gate_s_reason(_info(None, None, None), True) is not None
    # a start from before the hand left: tail None means Gate S whatever else is true
    why = cli.gate_s_reason(_info(120, "empty", None), True)
    assert why and "before the hand left" in why
    assert cli.gate_s_reason(_info(120, "quiet", None), True) is not None          # --allow-quiet does not help here


class _FakeRec:
    def __init__(self, tmp_path, n=40):
        self.name, self.n_frames = "fake_rec", n
        cv2.imwrite(str(tmp_path / "f.png"), np.random.default_rng(0).integers(0, 255, (60, 100, 3), dtype=np.uint8))
        self.p = tmp_path

    def left_path(self, k):
        return self.p / "f.png"


def _write_masks(runs, name, plan):
    """plan: per frame (hand?, bottle box or None) on the 621 x 1104 half grid."""
    n = len(plan)
    bottle = np.zeros((n, 621, 1104), bool)
    hand = np.zeros((n, 621, 1104), bool)
    for k, (h, b) in enumerate(plan):
        if h:
            hand[k, 100:200, 100:300] = True
        if b is not None:
            y0, x0 = b
            bottle[k, y0:y0 + 120, x0:x0 + 60] = True
    (runs / "masks").mkdir(parents=True, exist_ok=True)
    np.savez_compressed(runs / "masks" / f"{name}.npz", width=1104, bottle=np.packbits(bottle, axis=-1),
                        hand=np.packbits(hand, axis=-1))


def _run_start_frames(tmp_path, monkeypatch, plan, *argv):
    tmp_path.mkdir(exist_ok=True)
    rec = _FakeRec(tmp_path, len(plan))
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path / "runs"))
    _write_masks(tmp_path / "runs", rec.name, plan)
    monkeypatch.setattr(cli, "recordings", lambda: {"fake": rec})
    monkeypatch.setattr(cli, "START_FRAMES", tmp_path / "start_frames.json")
    code = 0
    try:
        cli.main(["start-frames", *argv])
    except SystemExit as e:
        code = e.code
    return code, json.loads((tmp_path / "start_frames.json").read_text())["fake_rec"]


def _plan_ending_still():
    # 8 hand frames, 10 frames of a moving bottle, then 22 frames of a still bottle
    return [(True, (300, 400))] * 8 + [(False, (200 + 15 * i, 300)) for i in range(10)] + [(False, (350, 500))] * 22


def test_start_frames_gate_s_and_allow_quiet(tmp_path, monkeypatch, capsys):
    code, info = _run_start_frames(tmp_path, monkeypatch, _plan_ending_still())
    assert code == 2 and info["kind"] == "quiet" and info["tail"] is not None and "GATE S" in capsys.readouterr().out
    assert info["states"][:8] == ["hand"] * 8 and len(info["states"]) == len(info["ious"]) == 40
    assert info["ious"][0] is None and info["ious"][-1] == pytest.approx(1.0)       # IoUs written beside the states
    code, info = _run_start_frames(tmp_path / "again", monkeypatch, _plan_ending_still(), "--allow-quiet", "fake")
    assert code == 0 and info["recipe"] == "tail" and info["start"] == 39


def test_start_frames_without_a_hand_free_tail_is_gate_s_even_with_a_start(tmp_path, monkeypatch, capsys):
    # an empty tank early, then the hand comes in and stays to the last frame
    plan = [(False, None)] * 10 + [(True, (300, 400))] * 30
    code, info = _run_start_frames(tmp_path, monkeypatch, plan, "--allow-quiet", "fake")
    out = capsys.readouterr().out
    assert info["start"] == 9 and info["tail"] is None          # realside still reports a start...
    assert code == 2 and "before the hand left" in out          # ...and the command still stops


# ---- floor checks ----------------------------------------------------------------------------------

def test_require_floor_messages(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path))

    class R:
        name = "rec_a"
    with pytest.raises(SystemExit, match="no noise floor.*cli.py floor"):
        cli._require_floor([R()])
    (tmp_path / "floor").mkdir()
    (tmp_path / "floor" / "rec_a.json").write_text('{"floor": null}')
    with pytest.raises(SystemExit, match="not a finite positive"):
        cli._require_floor([R()])
    (tmp_path / "floor" / "rec_a.json").write_text('{"floor": 0.12}')
    cli._require_floor([R()])


def test_selftest_and_dive_check_the_floor_before_anything_else(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path))

    class R:
        def __init__(self, n):
            self.name = n
    monkeypatch.setattr(cli, "recordings", lambda: {"a": R("rec_a")})
    with pytest.raises(SystemExit, match="no noise floor"):
        cli.main(["selftest"])
    (tmp_path / "clips_index.json").write_text(json.dumps({"c": {"condition": "a"}}))
    with pytest.raises(SystemExit, match="no noise floor"):
        cli.main(["dive"])



# ---- call 50: cmd_dive passes each condition's trusted travel; the self-test path is not capped ---------------

def test_dive_passes_pellets_cap_and_no_cap_elsewhere(tmp_path, monkeypatch):
    import dive
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path))

    class R:
        def __init__(self, n):
            self.name = n
    recs = {"saltwater-pellets": R("rec_p"), "saltwater": R("rec_s")}
    monkeypatch.setattr(cli, "recordings", lambda: recs)
    (tmp_path / "floor").mkdir()
    (tmp_path / "mapping").mkdir()
    idx = {}
    for cid, cond in (("p1", "saltwater-pellets"), ("s1", "saltwater")):
        (tmp_path / "floor" / f"{recs[cond].name}.json").write_text(json.dumps({"floor": 0.1}))
        (tmp_path / "mapping" / f"{cid}.json").write_text(json.dumps({"ok": True, "box": [0, 0, 1280, 720]}))
        np.savez(tmp_path / f"{cid}.npz", inv=np.ones((2, 4, 6), np.float32))
        idx[cid] = {"condition": cond, "video": "v", "depth": str(tmp_path / f"{cid}.npz")}
    (tmp_path / "clips_index.json").write_text(json.dumps(idx))
    monkeypatch.setattr(dive, "load_tank", lambda rec, runs: rec.name)
    monkeypatch.setattr(dive, "primary_path", lambda: "icp")
    monkeypatch.setattr(dive, "read_video", lambda v: [np.zeros((4, 6, 3), np.uint8)] * 2)
    seen = {}

    def fake_run_clip(tank, frames, inv, moving, box, primary, clip_id="", meta=None, trusted_travel=None):
        seen[clip_id] = trusted_travel
        return ({"clip": clip_id, "fit": {"s": 1.0, "t": 0.0}, "D_at": {}, "V_at": {}, "lost_from": None,
                 "wall_frame": None, "travel": 0.0}, {"C": np.zeros((2, 3))})
    monkeypatch.setattr(dive, "run_clip", fake_run_clip)
    cli.main(["dive"])
    assert seen == {"p1": 100.0, "s1": None}


# ---- the vertical-offset scoring (R2 step 2b) ----------------------------------------------------------

def _maps(h=120, w=200, seed=0):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    truth = (80.0 + 0.2 * xx + 0.1 * yy).astype(np.float32)
    return truth, rng


def test_score_dy_maps_on_synthetic_data():
    truth, rng = _maps()
    published = truth + 3.0 + rng.normal(0, 0.3, truth.shape).astype(np.float32)   # biased by 3 px
    shifted = truth + rng.normal(0, 0.3, truth.shape).astype(np.float32)             # unbiased
    published[:20] = np.nan                                                          # 1/6 of the image invalid, published only
    shifted[:, :10] = 0.0                                                            # 5 % invalid, shifted only (0 = invalid)
    xs = rng.integers(10, 190, 200)
    ys = rng.integers(25, 115, 200)
    m = {"x": xs.astype(float), "y": ys.astype(float), "dx": truth[ys, xs].astype(float), "dy": np.zeros(200)}
    s = cli.score_dy_maps(published, shifted, m)
    assert s["median_abs_diff"] == pytest.approx(3.0, abs=0.2)
    assert s["valid_published"] == pytest.approx(1 - 20 / 120, abs=1e-6)
    assert s["valid_shifted"] == pytest.approx(1 - 10 / 200, abs=1e-6)
    assert s["sift_n"] == 200 and s["sift_n_used"] == 200
    assert s["sift_err_published"] == pytest.approx(3.0, abs=0.3) and s["sift_err_shifted"] < 0.5
    assert s["sift_gain"] > 0.8


def test_score_dy_maps_restricts_to_the_tank_region_and_to_points_valid_in_both():
    truth, rng = _maps()
    published, shifted = truth.copy(), truth + 1.0
    region = np.zeros(truth.shape, bool)
    region[:, :100] = True
    shifted[50:60, :] = np.nan                                        # a hole in the shifted map only
    m = {"x": np.array([20.0, 30.0, 150.0]), "y": np.array([55.0, 70.0, 70.0]), "dx": truth[[55, 70, 70], [20, 30, 150]].astype(float),
         "dy": np.zeros(3)}
    s = cli.score_dy_maps(published, shifted, m, region)
    assert s["sift_n"] == 3 and s["sift_n_used"] == 2                  # the point in the hole is dropped from both errors
    assert s["sift_err_published"] == pytest.approx(0.0, abs=1e-4) and s["sift_err_shifted"] == pytest.approx(1.0, abs=1e-4)
    assert s["sift_gain"] == pytest.approx(0.0) or s["sift_gain"] is None  # zero published error: no gain defined
    assert s["valid_published"] == pytest.approx(1.0) and s["valid_shifted"] == pytest.approx(1 - 10 / 120)
    assert s["median_abs_diff"] == pytest.approx(1.0, abs=1e-4)


def test_score_dy_maps_with_nothing_valid():
    nan = np.full((10, 10), np.nan, np.float32)
    s = cli.score_dy_maps(nan, nan, {"x": np.array([1.0]), "y": np.array([1.0]), "dx": np.array([5.0]), "dy": np.array([0.0])})
    assert s["median_abs_diff"] is None and s["sift_err_published"] is None and s["sift_gain"] is None
    assert s["valid_published"] == 0.0


def test_sift_matches_on_a_shifted_pair():
    from test_modal_helpers import _blobs
    base = _blobs(420, 580, 7)
    left, right = base[10:410, 20:560], base[13:413, 28:568]            # dx = +8, dy = +3
    m = cli.sift_matches(cv2.cvtColor(left, cv2.COLOR_BGR2GRAY), cv2.cvtColor(right, cv2.COLOR_BGR2GRAY), top=200)
    assert 10 < len(m["dx"]) <= 200
    assert np.median(m["dx"]) == pytest.approx(8.0, abs=0.3) and np.median(m["dy"]) == pytest.approx(3.0, abs=0.3)


def _dy_fixture(tmp_path, monkeypatch, biases, n_used_ok=True, pairs_per=1):
    """Fake recordings a..e, each with a published and a shifted map. biases: [(published, shifted)] per pair."""
    from test_modal_helpers import _blobs
    tmp_path.mkdir(exist_ok=True)
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path / "runs"))
    base = _blobs(420, 580, 3)
    left, right = base[10:410, 20:560], base[13:413, 28:568]
    cv2.imwrite(str(tmp_path / "l.png"), left)
    cv2.imwrite(str(tmp_path / "r.png"), right)

    class Rec:
        def __init__(self, c):
            self.condition, self.name = c, f"rec_{c}"

        def left_path(self, f):
            return tmp_path / "l.png"

        def right_path(self, f):
            return tmp_path / "r.png"
    recs = {c: Rec(c) for c in "abcde"[:len(biases)]}
    monkeypatch.setattr(cli, "recordings", lambda: recs)
    root = tmp_path / "runs" / "disp_dytest"
    manifest = []
    for (c, r), (bp, bs) in zip(recs.items(), biases):
        for k in range(pairs_per):
            for mode, bias in (("published", bp), ("shifted", bs)):
                p = root / mode / r.name / f"{5 + k:06d}.npz"
                p.parent.mkdir(parents=True, exist_ok=True)
                # half-res disparity 4 -> 8 px at full res; None = no valid pixel at all (nothing measurable)
                half = np.full((621, 1104), np.nan if bias is None else 4.0 + bias / 2, np.float32)
                np.savez_compressed(p, disp_half=half, iscale=np.float32(2), dy_px=np.float32(3), dy_applied=np.float32(0))
            manifest.append({"condition": c, "recording": r.name, "frame": 5 + k, "dy_px": 3.0, "dy_applied": 3.0})
    (root / "pairs.json").write_text(json.dumps(manifest))
    return root


def _dy_exit(capsys):
    try:
        cli.main(["dy-score"])
        code = 0
    except SystemExit as e:
        code = e.code
    return code, capsys.readouterr().out


def test_dy_score_end_to_end_and_stop_rule(tmp_path, monkeypatch, capsys):
    """Published maps are biased, shifted maps are right on 5 pairs -> the stop rule fires (exit 3)."""
    root = _dy_fixture(tmp_path, monkeypatch, [(2.0, 0.0)] * 5)
    code, out = _dy_exit(capsys)
    assert code == 3 and "FIRES" in out and "| a | 5 |" in out
    rep = json.loads((root / "report.json").read_text())
    assert rep["stop_rule"] == "FIRES" and len(rep["rows"]) == 5 and rep["rows"][0]["sift_err_shifted"] < 0.5
    assert rep["rows"][0]["sift_n_used"] >= cli.DY_MIN_USED


def test_dy_score_holds_when_the_shift_does_not_help(tmp_path, monkeypatch, capsys):
    root = _dy_fixture(tmp_path, monkeypatch, [(1.0, 1.0)] * 5)   # both maps 1 px off: the shift gains nothing
    code, out = _dy_exit(capsys)
    assert code == 0 and "holds" in out and "INCONCLUSIVE" not in out
    assert json.loads((root / "report.json").read_text())["stop_rule"] == "holds"


def test_dy_score_is_inconclusive_when_it_could_not_measure(tmp_path, monkeypatch, capsys):
    """I5: maps with no valid pixel give no SIFT comparison; that must not read as 'holds'."""
    root = _dy_fixture(tmp_path, monkeypatch, [(None, None)] * 5)
    code, out = _dy_exit(capsys)
    assert code == 4 and "INCONCLUSIVE" in out and "fewer than 3" in out
    assert json.loads((root / "report.json").read_text())["stop_rule"] == "INCONCLUSIVE"
    # two measurable pairs and three that are not: still inconclusive
    _dy_fixture(tmp_path / "two", monkeypatch, [(2.0, 0.0)] * 2 + [(None, None)] * 3)
    code, out = _dy_exit(capsys)
    assert code == 4


def _row(cond, used, gain):
    return {"condition": cond, "sift_n_used": used, "sift_gain": gain}


def test_dy_verdict_counts_a_pair_only_with_30_matches_used():
    assert cli.DY_MIN_USED == 30 and cli.DY_STOP_PAIRS == 3
    assert cli.dy_verdict([_row(c, 29, 0.5) for c in "abc"])[0] == "INCONCLUSIVE"
    assert cli.dy_verdict([_row(c, 30, 0.5) for c in "abc"]) == ("FIRES", ["a", "b", "c"], 3)
    # three measured pairs that do not improve, two unmeasurable ones that look great: holds, the two do not count
    verdict, better, measured = cli.dy_verdict([_row(c, 30, 0.05) for c in "abc"] + [_row(c, 3, 0.9) for c in "de"])
    assert (verdict, better, measured) == ("holds", [], 3)
    assert cli.dy_verdict([_row("a", 30, None)] * 3)[0] == "INCONCLUSIVE"


def test_dy_pool_pools_the_matches_of_a_recording():
    e = lambda *v: np.array(v, float)
    pooled = cli.dy_pool({"a": [(e(1, 1, 1), e(0, 0, 0)), (e(3, 3), e(1, 1))], "b": []})
    (a, b) = pooled
    assert a["condition"] == "a" and a["pairs"] == 2 and a["sift_n_used"] == 5
    assert a["sift_err_published"] == pytest.approx(1.0) and a["sift_err_shifted"] == pytest.approx(0.0)   # medians of 5 pooled errors
    assert a["sift_gain"] == pytest.approx(1.0)
    assert b["sift_n_used"] == 0 and b["sift_gain"] is None and b["sift_err_published"] is None


def _few_matches(monkeypatch, n=12):
    """Each pair gives only n matches (below DY_MIN_USED on its own); disparity 8 at full resolution."""
    xs = np.linspace(100, 2000, n)
    monkeypatch.setattr(cli, "sift_matches", lambda l, r: {"x": xs, "y": np.full(n, 600.0), "dx": np.full(n, 8.0), "dy": np.zeros(n)})


def test_dy_score_pools_matches_per_recording(tmp_path, monkeypatch, capsys):
    """12 matches per pair is too few alone; pooled over 3 frames it is 36, so the recording counts (and the shift wins)."""
    _dy_fixture(tmp_path, monkeypatch, [(2.0, 0.0)] * 4, pairs_per=3)
    _few_matches(monkeypatch)
    code, out = _dy_exit(capsys)
    assert code == 3 and "FIRES" in out
    assert "| a | 5 |" in out and "| a | 6 |" in out and "| a | 7 |" in out        # the per-pair rows stay
    assert "| a | 3 | 36 |" in out                                                    # and the pooled row: pairs, matches used
    rep = json.loads((tmp_path / "runs" / "disp_dytest" / "report.json").read_text())
    assert len(rep["rows"]) == 12 and [p["sift_n_used"] for p in rep["pooled"]] == [36] * 4


def test_dy_score_two_frames_of_12_matches_is_still_inconclusive(tmp_path, monkeypatch, capsys):
    _dy_fixture(tmp_path, monkeypatch, [(2.0, 0.0)] * 4, pairs_per=2)
    _few_matches(monkeypatch)
    code, out = _dy_exit(capsys)
    assert code == 4 and "INCONCLUSIVE" in out and "recordings" in out


def test_dy_score_pooled_holds_when_the_shift_does_not_help(tmp_path, monkeypatch, capsys):
    _dy_fixture(tmp_path, monkeypatch, [(1.0, 1.0)] * 4, pairs_per=3)
    _few_matches(monkeypatch)
    code, out = _dy_exit(capsys)
    assert code == 0 and "holds" in out


def test_dy_score_a_recording_with_nothing_measurable_does_not_count(tmp_path, monkeypatch, capsys):
    """Three recordings win; a fourth has no valid pixel (like the pellets pair): the three still fire the rule."""
    _dy_fixture(tmp_path, monkeypatch, [(2.0, 0.0)] * 3 + [(None, None)], pairs_per=3)
    _few_matches(monkeypatch)
    code, out = _dy_exit(capsys)
    assert code == 3
    rep = json.loads((tmp_path / "runs" / "disp_dytest" / "report.json").read_text())
    assert rep["measured_recordings"] == 3


# ---- Gate S: --allow-quiet names conditions, each entry records its reason, later steps refuse ---------

def _two_still_recordings(tmp_path, monkeypatch):
    plan = _plan_ending_still()
    recs = {}
    for c in ("air", "freshwater"):
        r = _FakeRec(tmp_path, len(plan))
        r.name = f"rec_{c}"
        recs[c] = r
        _write_masks(tmp_path / "runs", r.name, plan)
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path / "runs"))
    monkeypatch.setattr(cli, "recordings", lambda: recs)
    monkeypatch.setattr(cli, "START_FRAMES", tmp_path / "start_frames.json")
    return recs


def _main_code(argv):
    try:
        cli.main(argv)
        return 0
    except SystemExit as e:
        return e.code


def test_allow_quiet_accepts_only_the_named_recordings(tmp_path, monkeypatch, capsys):
    """M6: Gate S call S1 accepts Air only; Freshwater's quiet start still stops the run."""
    _two_still_recordings(tmp_path, monkeypatch)
    assert _main_code(["start-frames", "--allow-quiet", "air"]) == 2
    table = json.loads((tmp_path / "start_frames.json").read_text())
    assert table["rec_air"]["gate_s"] is None                       # I6: every entry carries its Gate S reason
    assert "only a still bottle" in table["rec_freshwater"]["gate_s"] and "--allow-quiet freshwater" in table["rec_freshwater"]["gate_s"]
    assert "GATE S: freshwater" in capsys.readouterr().out
    assert _main_code(["start-frames", "--allow-quiet", "air", "freshwater"]) == 0
    table = json.loads((tmp_path / "start_frames.json").read_text())
    assert table["rec_air"]["gate_s"] is None and table["rec_freshwater"]["gate_s"] is None


def test_allow_quiet_rejects_a_bare_flag_and_an_unknown_name(tmp_path, monkeypatch, capsys):
    _two_still_recordings(tmp_path, monkeypatch)
    assert _main_code(["start-frames", "--allow-quiet"]) == 2       # argparse: expected at least one condition
    assert "--allow-quiet" in capsys.readouterr().err
    code = _main_code(["start-frames", "--allow-quiet", "aire"])
    assert code not in (0, None) and "aire" in str(code) and "air" in str(code)
    assert not (tmp_path / "start_frames.json").exists()


class _GateRec:
    name = "rec_bad"
    n_frames = 10
    start_info = {"start": 9, "tail": None, "recipe": "all", "kind": "empty",
                  "gate_s": "no hand-free run at the end of the recording"}

    @property
    def start_frame(self):
        raise AssertionError("must refuse before asking for the start frame")


def test_tank_and_recon_refuse_after_a_gate_s_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path / "runs"))
    monkeypatch.setattr(cli, "recordings", lambda: {"bad": _GateRec()})
    import dive
    monkeypatch.setattr(dive, "load_tank", lambda *a, **k: pytest.fail("load_tank reached"))
    for cmd in ("tank", "recon"):
        code = _main_code([cmd])
        assert code not in (0, None) and "Gate S" in str(code) and "no hand-free run" in str(code), (cmd, code)


# ---- M7: the half-resolution factor comes from the disparity files -----------------------------------------

def _tank_setup(tmp_path, monkeypatch, iscale):
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path / "runs"))

    class Rec:
        name, n_frames, matched_frames = "r", 12, []
        calibration = type("Cal", (), {"fx": 1000.0, "baseline_mm": 60.0})()
        start_info = {"start": 11, "tail": [0, 11], "recipe": "tail", "kind": "empty", "gate_s": None}
    _write_masks(tmp_path / "runs", "r", [(False, None)] * 12)
    d = tmp_path / "runs" / "disp" / "r"
    d.mkdir(parents=True)
    for f in range(12):                                   # a tank pixel needs 10 valid observations
        np.savez_compressed(d / f"{f:06d}.npz", disp_half=np.full((621, 1104), 3.0, np.float16),
                            iscale=np.float32(iscale), dy_px=np.float32(0))
    monkeypatch.setattr(cli, "recordings", lambda: {"c": Rec()})
    return Rec()


def test_tank_records_and_prints_the_disparity_files_iscale(tmp_path, monkeypatch, capsys):
    _tank_setup(tmp_path, monkeypatch, 2.0)
    cli.main(["tank"])
    out = capsys.readouterr().out
    assert "median disp=6.0 px (full res)" in out
    assert float(np.load(tmp_path / "runs" / "tank" / "r.npz")["iscale"]) == 2.0


def test_tank_refuses_an_iscale_that_does_not_match_the_grid(tmp_path, monkeypatch):
    _tank_setup(tmp_path, monkeypatch, 4.0)
    code = _main_code(["tank"])
    assert code not in (0, None) and "iscale" in str(code)


def test_tank_work_scales_by_the_tank_files_iscale(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path / "runs"))
    (tmp_path / "runs" / "tank").mkdir(parents=True)

    class Rec:
        name = "r"
    half = np.full((621, 1104), 3.0, np.float32)
    np.savez(tmp_path / "runs" / "tank" / "r.npz", tank_disp_half=half, iscale=np.float32(4.0))
    d, ok = cli._tank_work(Rec())
    assert ok.any() and np.allclose(d[ok], 12.0)
    np.savez(tmp_path / "runs" / "tank" / "r.npz", tank_disp_half=half)                  # an older tank file: 2
    d, ok = cli._tank_work(Rec())
    assert np.allclose(d[ok], 6.0)


# ---- M8: kill rules have exit codes ---------------------------------------------------------------------------

def _floor_setup(tmp_path, monkeypatch, ar):
    import types
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path / "runs"))
    recs = {}
    for c in ("a", "b", "c", "d", "e"):
        r = types.SimpleNamespace(name=f"rec_{c}")
        recs[c] = r
        p = tmp_path / "runs" / "da3" / "floor"
        p.mkdir(parents=True, exist_ok=True)
        np.savez(p / f"{r.name}.npz", frames=np.array([0, 1]), inv=np.ones((2, 720, 1280), np.float16))
    monkeypatch.setattr(cli, "recordings", lambda: recs)
    monkeypatch.setattr(cli, "_tank_work", lambda rec: (np.ones((720, 1280)), np.ones((720, 1280), bool)))
    monkeypatch.setattr(cli, "_masks", lambda rec: (np.zeros((2, 621, 1104), bool), np.zeros((2, 621, 1104), bool)))
    monkeypatch.setattr(cli, "huber_affine_fit", lambda g, d, M: types.SimpleNamespace(apply=lambda x: x, to_dict=lambda: {}))
    monkeypatch.setattr(cli, "rel_residual", lambda a, b: np.zeros((720, 1280)))
    monkeypatch.setattr(cli, "abs_rel", lambda r, M: ar)


def test_floor_exits_5_when_kill_rule_1_fires(tmp_path, monkeypatch, capsys):
    _floor_setup(tmp_path, monkeypatch, 0.4)
    assert _main_code(["floor"]) == 5
    out = capsys.readouterr().out
    assert "FIRES" in out and "exit 5" in out


def test_floor_exits_0_when_kill_rule_1_holds(tmp_path, monkeypatch, capsys):
    _floor_setup(tmp_path, monkeypatch, 0.10)
    assert _main_code(["floor"]) == 0
    assert "holds" in capsys.readouterr().out


def _scores(err):
    return {c: {"tracks": {"endpoint_err_frac": err, "yaw_err_deg_max": 1.0},
                "icp": {"endpoint_err_frac": err, "yaw_err_deg_max": 1.0}} for c in "abcde"}


def test_selftest_exits_6_when_kill_rule_4_fires(tmp_path, monkeypatch, capsys):
    import dive
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path / "runs"))
    monkeypatch.setattr(dive, "PATH_CHOICE", tmp_path / "path_choice.json")
    with pytest.raises(SystemExit) as e:
        cli._selftest_conclude(_scores(0.30), {})
    assert e.value.code == 6
    out = capsys.readouterr().out
    assert "FIRES" in out and "exit 6" in out
    assert json.loads((tmp_path / "path_choice.json").read_text())["kill_rule_4"] == "FIRES"   # still written
    cli._selftest_conclude(_scores(0.05), {})                                                 # holds: returns
    assert json.loads((tmp_path / "path_choice.json").read_text())["kill_rule_4"] == "holds"


# ---- the commands exist ------------------------------------------------------------------------------

def test_help_lists_every_command():
    r = subprocess.run([sys.executable, str(PIPELINE / "cli.py"), "--help"], capture_output=True, text=True, cwd=PIPELINE)
    assert r.returncode == 0
    for c in ("start-frames", "calib", "seed-sheet", "units", "tank", "floor", "recon", "selftest-prep", "selftest",
              "map", "dive", "dy-score", "summary"):
        assert c in r.stdout, c


# ---- call 45: a short empty tail builds the map; the masked median is only a cross-check ---------------------

def _short_tail_setup(tmp_path, monkeypatch, n_tail):
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path / "runs"))

    class Rec:
        name, n_frames = "r", 12
        matched_frames = list(range(12))
        calibration = type("Cal", (), {"fx": 1000.0, "baseline_mm": 60.0})()
        start_info = {"start": 11, "tail": [12 - n_tail, 11], "recipe": "tail", "kind": "empty", "tail_len": n_tail,
                      "gate_s": None}
    # frames 0..4: a bottle box in view (excluded from the masked median); the rest empty
    _write_masks(tmp_path / "runs", "r", [(False, (300, 400))] * 5 + [(False, None)] * 7)
    d = tmp_path / "runs" / "disp" / "r"
    d.mkdir(parents=True)
    for f in range(12):
        disp = np.full((621, 1104), 3.0, np.float16)
        if f < 5:
            disp[300:420, 400:460] = 50.0                     # the bottle's disparity, only while it is in view
        np.savez_compressed(d / f"{f:06d}.npz", disp_half=disp, iscale=np.float32(2.0), dy_px=np.float32(0))
    rec = Rec()
    monkeypatch.setattr(cli, "recordings", lambda: {"c": rec})
    return rec


def test_tank_builds_the_map_from_a_seven_frame_empty_tail_and_prints_the_crosscheck(tmp_path, monkeypatch, capsys):
    _short_tail_setup(tmp_path, monkeypatch, 7)
    cli.main(["tank"])
    out = capsys.readouterr().out
    z = np.load(tmp_path / "runs" / "tank" / "r.npz")
    assert list(z["frames"]) == list(range(5, 12)) and z["valid"].all() and np.allclose(z["tank_disp_half"], 3.0)
    assert "frames=7" in out and "valid=1.000" in out and "xcheck masked: med=0.000 p90=0.000" in out
    x = json.loads((tmp_path / "runs" / "tank" / "r_xcheck.json").read_text())
    assert x["med"] == 0.0 and x["p90"] == 0.0 and x["n"] > 0 and x["masked_frames"] == 12


def test_tank_with_a_single_frame_tail_reports_iqr_as_not_available(tmp_path, monkeypatch, capsys):
    _short_tail_setup(tmp_path, monkeypatch, 1)
    cli.main(["tank"])
    out = capsys.readouterr().out
    z = np.load(tmp_path / "runs" / "tank" / "r.npz")
    assert list(z["frames"]) == [11] and z["valid"].all()
    assert "frames=1" in out and "rel IQR=n/a" in out


def test_the_crosscheck_never_feeds_the_map(tmp_path, monkeypatch):
    # the masked median sees ten extra frames (12-21), unmasked and at 9.0: it disagrees with the tail's 3.0 by
    # 200 %, yet the tank map stays the tail's plain median
    rec = _short_tail_setup(tmp_path, monkeypatch, 7)
    d = tmp_path / "runs" / "disp" / "r"
    for f in range(12, 22):
        np.savez_compressed(d / f"{f:06d}.npz", disp_half=np.full((621, 1104), 9.0, np.float16),
                            iscale=np.float32(2.0), dy_px=np.float32(0))
    _write_masks(tmp_path / "runs", "r", [(False, None)] * 22)
    rec.matched_frames = list(range(12, 22))
    cli.main(["tank"])
    z = np.load(tmp_path / "runs" / "tank" / "r.npz")
    assert np.allclose(z["tank_disp_half"], 3.0)
    x = json.loads((tmp_path / "runs" / "tank" / "r_xcheck.json").read_text())
    assert x["med"] == pytest.approx(2.0) and x["masked_frames"] == 10
