import json

import numpy as np
import pytest

import clipdepth
import clips
import modal_depth
import spendguard as sg
from clips import ClipSpec
from realside import unpack_masks
from synth_video import noise_frames, write_mp4
from test_modal_helpers import _npy, _Remote, _run_dry

SMALL = (64, 48)


@pytest.fixture
def card(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path / "runs"))
    monkeypatch.setenv("DIVETWIN_RUNWAY_LOG", str(tmp_path / "spend.jsonl"))
    monkeypatch.setitem(clips.GRID, "gen45", SMALL)
    monkeypatch.setitem(clips.GRID, "wan22", SMALL)
    (tmp_path / "runs").mkdir()
    return tmp_path


def _ok_smoke(card, wall_s=None):
    """An ok depth smoke line that costs nothing in the sums: the full run is refused without one."""
    with open(card / "runs" / "modal_spend.jsonl", "a") as fh:
        fh.write(json.dumps({"task": "3.1-depth-smoke", "status": "ok", "n": 121, "usd_upper": 0.0, "gpu": "L40S", "phase": 3,
                             "wall_s": wall_s or 60 + modal_depth.DA3_LOAD_S + 10}) + "\n")


def make_clip(spec):
    return write_mp4(clips.video_path(spec), noise_frames(clips.expected_frames(spec), *SMALL))


def rows(card):
    p = card / "runs" / "modal_spend.jsonl"
    return [json.loads(t) for t in p.read_text().splitlines()] if p.exists() else []


# ---- the filter and the resize -----------------------------------------------------------------------

def test_the_median_removes_a_one_frame_spike_and_keeps_a_ramp():
    x = np.ones((9, 4, 5), np.float32)
    x[4] = 50.0
    assert np.array_equal(clipdepth.temporal_median(x), np.ones_like(x))
    ramp = np.arange(9, dtype=np.float32)[:, None, None] * np.ones((9, 3, 3), np.float32)
    got = clipdepth.temporal_median(ramp)[:, 0, 0]
    assert got[2:7].tolist() == [2.0, 3.0, 4.0, 5.0, 6.0]            # interior frames of a ramp are unchanged
    assert got[0] == 0.0 and got[8] == 8.0                             # edges replicate: frame 0 = median(0,0,0,1,2) = 0


def test_edge_frames_use_replicated_neighbours_so_frame_0_stays_itself():
    x = np.zeros((6, 2, 2), np.float32)
    x[0] = 7.0                                    # frame 0 differs from its future: median(7,7,7,0,0) = 7
    assert clipdepth.temporal_median(x)[0, 0, 0] == 7.0
    assert clipdepth.temporal_median(x)[1, 0, 0] == 0.0                # median(7,7,0,0,0)


def test_the_window_is_five_frames():
    assert clipdepth.MEDIAN_WINDOW == 5
    x = np.zeros((10, 1, 1), np.float32)
    x[3:5] = 9.0                                  # a two-frame blip also goes (needs 3 of 5 to survive)
    assert clipdepth.temporal_median(x).max() == 0.0
    x[3:6] = 9.0                                  # three frames survive
    assert clipdepth.temporal_median(x)[4, 0, 0] == 9.0


def test_resize_gives_float16_on_the_clips_grid():
    lo = np.random.default_rng(0).uniform(0.01, 1, (3, 28, 50)).astype(np.float32)
    out = clipdepth.process(lo, 64, 48)
    assert out.shape == (3, 48, 64) and out.dtype == np.float16 and (out > 0).all()


# ---- the file and its checks -------------------------------------------------------------------------

def test_the_npz_holds_exactly_the_contract_and_a_sidecar_says_what_made_it(card):
    spec = ClipSpec("air", "gen45", "D", 5)
    make_clip(spec)
    inv = np.full((121, 48, 64), 0.5, np.float16)
    p = clipdepth.write_depth_npz(spec, inv)
    assert p == clips.depth_path(spec) and set(np.load(p).files) == {"inv"}
    assert clipdepth.check_depth(spec) == {"ok": True, "reason": None, "frames": 121, "grid": [64, 48]}
    side = json.loads(p.with_suffix(".json").read_text())
    assert side["median_window"] == 5 and side["process_res"] == 504 and side["tracked"] is False
    mov = np.zeros((121, 48, 64), bool)
    mov[:, 5:9, 10:20] = True
    clipdepth.write_depth_npz(spec, inv, mov)
    z = np.load(p)
    assert set(z.files) == {"inv", "moving"} and np.array_equal(unpack_masks(z["moving"], 64), mov)
    assert clipdepth.check_depth(spec)["ok"]


@pytest.mark.parametrize("bad,why", [
    (np.full((100, 48, 64), 0.5, np.float16), "100 depth maps for 121 video frames"),
    (np.full((121, 40, 64), 0.5, np.float16), "depth grid 64x40, expected 64x48"),
    (np.full((121, 48, 64), np.nan, np.float16), "finite and positive"),
    (np.full((121, 48, 64), 0.0, np.float16), "finite and positive"),
])
def test_check_depth_catches_a_mismatch_with_the_mp4(card, bad, why):
    spec = ClipSpec("air", "gen45", "D", 5)
    make_clip(spec)
    clipdepth.write_depth_npz(spec, bad)
    r = clipdepth.check_depth(spec)
    assert not r["ok"] and why in r["reason"]


def test_check_depth_wants_float16_and_nothing_extra(card):
    spec = ClipSpec("air", "gen45", "D", 5)
    make_clip(spec)
    p = clips.depth_path(spec)
    p.parent.mkdir(parents=True)
    np.savez_compressed(p, inv=np.full((121, 48, 64), 0.5, np.float32))
    assert "float16" in clipdepth.check_depth(spec)["reason"]
    np.savez_compressed(p, inv=np.full((121, 48, 64), 0.5, np.float16), extra=np.zeros(1))
    assert "expected inv" in clipdepth.check_depth(spec)["reason"]
    assert clipdepth.check_depth(ClipSpec("air", "gen45", "B", 5))["reason"] == "no depth file"


def test_clip_seeds_are_validated_against_the_clip(card):
    spec = ClipSpec("air", "gen45", "B", 5)
    make_clip(spec)
    assert clipdepth.load_clip_seeds() == {}                          # no file: no tracks
    f = clipdepth.clip_seeds_path()
    f.write_text(json.dumps({spec.id: [{"frame": 0, "obj": "fish", "box": [10, 10, 30, 30]}]}))
    assert clipdepth.load_clip_seeds()[spec.id][0]["obj"] == "fish"
    for bad in ({"frame": 0, "obj": "fish", "box": [10, 10, 99, 30]}, {"frame": 500, "obj": "fish", "box": [1, 1, 5, 5]},
                {"frame": 0, "obj": "fish", "box": [30, 10, 10, 30]}, {"frame": 0, "obj": "", "box": [1, 1, 5, 5]}):
        f.write_text(json.dumps({spec.id: [bad]}))
        with pytest.raises(ValueError, match="bad seed"):
            clipdepth.load_clip_seeds()


def test_union_of_packed_masks_is_the_union():
    a, b = np.zeros((2, 3, 16), bool), np.zeros((2, 3, 16), bool)
    a[0, 0, 1], b[1, 2, 15] = True, True
    u = clipdepth.union_masks({"a": np.packbits(a, axis=-1), "b": np.packbits(b, axis=-1)})
    assert np.array_equal(unpack_masks(u, 16), a | b)


# ---- the Modal entrypoints with a fake remote --------------------------------------------------------

def fake_depth(monkeypatch, fail_on=None, clock=None, step_s=0.0):
    calls = []

    def depth(images, process_res):
        calls.append(len(images))
        if fail_on == len(calls):
            raise RuntimeError("DA3 call failed")
        if clock is not None:
            clock[0] += step_s
        return _npy(np.full((len(images), 28, 50), 0.4, np.float16)), 1.0
    monkeypatch.setattr(modal_depth, "Da3Mono", lambda: type("D", (), {"depth_native": _Remote(depth)})())
    monkeypatch.setattr(modal_depth, "fetch_weights", _Remote(lambda *a, **k: None))
    return calls


def test_the_plan_reads_the_index_and_skips_clips_with_valid_depth(card):
    a, b = ClipSpec("air", "gen45", "D", 5), ClipSpec("air", "wan22", "D", 5)
    make_clip(a), make_clip(b)
    make_clip(ClipSpec("air", "gen45", "D", 2, "probe"))              # a probe: never planned
    todo, n, line = modal_depth.plan_clips()
    assert [s.id for s in todo] == [a.id, b.id] and n == 242
    assert "Phase 3" in line and "cap $1.70" in line and "estimate $" in line
    clipdepth.write_depth_npz(a, np.full((121, 48, 64), 0.5, np.float16))
    assert [s.id for s in modal_depth.plan_clips()[0]] == [b.id]
    assert [s.id for s in modal_depth.plan_clips(smoke=True)[0]] == [b.id]
    with pytest.raises(SystemExit, match="not in clips_index.json"):
        modal_depth.plan_clips(only="air__gen45__B__5s")


def test_depth_clips_writes_the_npz_updates_the_index_and_logs_a_phase_3_line(card, monkeypatch):
    _ok_smoke(card)
    a, b = ClipSpec("air", "gen45", "D", 5), ClipSpec("air", "gen45", "D", 10)
    make_clip(a), make_clip(b)
    calls = fake_depth(monkeypatch)
    modal_depth.run_clips()
    assert calls == [24] * 10 + [1] + [24] * 5 + [1]                  # the 10 s clip sorts first; 24 frames a call, within the class timeout
    for s in (a, b):
        r = clipdepth.check_depth(s)
        assert r["ok"] and r["frames"] == clips.expected_frames(s)
    z = np.load(clips.depth_path(a))["inv"]
    assert z.dtype == np.float16 and z.shape == (121, 48, 64) and np.allclose(z.astype(float), 0.4, atol=1e-3)
    smoke_line, line = rows(card)                                      # the helper's smoke line, then this run's
    assert smoke_line["task"] == "3.1-depth-smoke"
    assert (line["task"], line["phase"], line["n"], line["status"], line["gpu"]) == ("3.1-depth", 3, 362, "ok", "L40S")
    idx = json.loads((card / "runs" / "clips_index.json").read_text())
    assert set(idx) == {a.id, b.id} and all(__import__("pathlib").Path(e["depth"]).exists() for e in idx.values())
    modal_depth.run_clips()                                            # everything is done: no remote call, no new line
    assert len(rows(card)) == 2 and calls[-1] == 1


def test_smoke_does_one_clip_under_its_own_small_cap(card, monkeypatch):
    make_clip(ClipSpec("air", "gen45", "D", 5)), make_clip(ClipSpec("air", "gen45", "B", 5))
    fake_depth(monkeypatch)
    modal_depth.run_clips(smoke=True)
    (line,) = rows(card)
    assert line["task"] == "3.1-depth-smoke" and line["n"] == 121 and line["cap_usd"] <= 0.25
    assert len(list((card / "runs" / "da3" / "clips").glob("*.npz"))) == 1


def test_a_failed_call_leaves_no_half_file_and_still_logs(card, monkeypatch):
    _ok_smoke(card)
    a = ClipSpec("air", "gen45", "D", 5)
    make_clip(a)
    fake_depth(monkeypatch, fail_on=3)
    with pytest.raises(RuntimeError, match="DA3 call failed"):
        modal_depth.run_clips()
    assert not clips.depth_path(a).exists() and rows(card)[-1]["status"] == "error" and rows(card)[-1]["n"] == 0


def test_the_cap_stops_between_calls_and_writes_nothing_for_a_clip_it_cut(card, monkeypatch):
    _ok_smoke(card)
    import modal_common
    make_clip(ClipSpec("air", "gen45", "D", 5))
    clock = [1000.0]
    monkeypatch.setattr(modal_common.Meter, "_now", staticmethod(lambda: clock[0]))
    calls = fake_depth(monkeypatch, clock=clock, step_s=1500.0)       # each call "takes" 1500 s of wall time
    with pytest.raises(SystemExit) as e:
        modal_depth.run_clips()
    assert "cap reached" in str(e.value.code) and not clips.depth_path(ClipSpec("air", "gen45", "D", 5)).exists()
    assert rows(card)[-1]["status"] == "cap" and rows(card)[-1]["phase"] == 3 and len(calls) < 6


def test_a_depth_count_that_disagrees_with_the_video_is_an_error(card, monkeypatch):
    _ok_smoke(card)
    make_clip(ClipSpec("air", "gen45", "D", 5))
    monkeypatch.setattr(modal_depth, "Da3Mono", lambda: type("D", (), {"depth_native": _Remote(
        lambda images, pr: (_npy(np.full((len(images) - 1, 28, 50), 0.4, np.float16)), 1.0))})())
    monkeypatch.setattr(modal_depth, "fetch_weights", _Remote(lambda *a, **k: None))
    with pytest.raises(RuntimeError, match="depth maps came back"):
        modal_depth.run_clips()


def test_the_phase_3_total_and_the_generation_stop_apply(card, monkeypatch):
    make_clip(ClipSpec("air", "gen45", "D", 5))
    calls = fake_depth(monkeypatch)
    with open(card / "runs" / "modal_spend.jsonl", "w") as fh:
        fh.write(json.dumps({"task": "3.1-depth", "usd_upper": 1.95, "phase": 3}) + "\n")
    with pytest.raises(SystemExit, match="Phase 3 budget"):               # the smoke run needs no smoke line: its own total check
        modal_depth.run_clips(smoke=True)
    _ok_smoke(card)
    with pytest.raises(SystemExit, match="Phase 3"):                      # the full run: the smoke's projection meets the same total
        modal_depth.run_clips()
    assert calls == []
    with open(card / "runs" / "modal_spend.jsonl", "w") as fh:
        fh.write(json.dumps({"task": "old", "usd_upper": 31.2}) + "\n")   # GBP 24.96: DA3 obeys the same stop
    _ok_smoke(card)
    with pytest.raises(SystemExit, match="cap reached"):
        modal_depth.run_clips()
    assert calls == []


def test_tracks_store_the_union_of_the_named_objects_as_moving(card, monkeypatch):
    spec = ClipSpec("air", "gen45", "B", 5)
    make_clip(spec)
    clipdepth.write_depth_npz(spec, np.full((121, 48, 64), 0.5, np.float16))
    clipdepth.clip_seeds_path().write_text(json.dumps({spec.id: [
        {"frame": 0, "obj": "fish", "box": [10, 10, 30, 30]}, {"frame": 0, "obj": "weed", "box": [40, 5, 60, 20]}]}))
    sent = {}

    def track(jpegs, prompts):
        sent["n"], sent["prompts"] = len(jpegs), prompts
        m1, m2 = np.zeros((121, 48, 64), bool), np.zeros((121, 48, 64), bool)
        m1[:, 12:20, 12:20], m2[:, 6:10, 45:50] = True, True
        return {"fish": _npy(np.packbits(m1, axis=-1)), "weed": _npy(np.packbits(m2, axis=-1))}, 1.0
    monkeypatch.setattr(modal_depth, "Sam2Video", lambda: type("S", (), {"track": _Remote(track)})())
    monkeypatch.setattr(modal_depth, "fetch_weights", _Remote(lambda *a, **k: None))
    todo, n, line = modal_depth.plan_tracks()
    assert [s.id for s in todo] == [spec.id] and n == 121 and "cap $0.40" in line
    modal_depth.run_tracks()
    assert sent["n"] == 121 and [p["obj"] for p in sent["prompts"]] == ["fish", "weed"]
    z = np.load(clips.depth_path(spec))
    mv = unpack_masks(z["moving"], 64)
    assert mv.shape == (121, 48, 64) and mv[0, 15, 15] and mv[0, 8, 47] and not mv[0, 0, 0]
    assert z["inv"].dtype == np.float16 and clipdepth.check_depth(spec)["ok"]
    assert rows(card)[-1]["task"] == "3.1-sam2" and rows(card)[-1]["phase"] == 3


def test_no_seeds_means_no_tracks_and_no_spend(card):
    todo, n, line = modal_depth.plan_tracks()
    assert todo == [] and "no clip is tracked" in line
    modal_depth.run_tracks()
    assert rows(card) == []


def test_a_seed_for_a_clip_without_depth_is_refused(card):
    spec = ClipSpec("air", "gen45", "B", 5)
    make_clip(spec)
    clipdepth.clip_seeds_path().write_text(json.dumps({spec.id: [{"frame": 0, "obj": "fish", "box": [1, 1, 9, 9]}]}))
    with pytest.raises(SystemExit, match="no valid depth file"):
        modal_depth.plan_tracks()


def test_phase_3_numbers_follow_the_plan():
    assert modal_depth.CLIP_CAPS == {"smoke": 0.25, "depth": 1.70, "tracks": 0.40}
    assert sum(modal_depth.CLIP_CAPS.values()) > sg.PHASE_TOTAL_USD[3] == 2.00      # the total binds
    assert modal_depth.CAPS == {"smoke": 0.25, "masks": 1.50, "floor": 0.75, "selftest": 0.50}   # Phase 1 untouched
    import modal_common
    assert modal_common.PHASE1_CAP_USD == 5.00


@pytest.mark.parametrize("args,expect", [(["clips", "--dry-run"], "clips, "), (["clips", "--dry-run", "--smoke"], "clips, "),
                                         (["tracks", "--dry-run"], "clips to track")])
def test_dry_runs_work_offline_and_write_nothing(tmp_path, args, expect):
    r = _run_dry("modal_depth.py", *args, tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr[-2000:]       # no clip to do: nothing would be refused
    assert expect in r.stdout and "Phase 3" in r.stdout and "cap $" in r.stdout
    assert not (tmp_path / "runs" / "modal_spend.jsonl").exists()
    assert not (tmp_path / "runs" / "clips_index.json").exists()


# ---- the reviewer's findings: one cost model, the honest estimate, the projection from the smoke -----------------

def test_the_depth_cost_model_is_shared_and_the_honest_number_is_shown():
    assert (sg.DEPTH_S_PER_FRAME, sg.DEPTH_LOAD_S, sg.DEPTH_OVERHEAD_S) == (modal_depth.DA3_S_PER_FRAME, modal_depth.DA3_LOAD_S,
                                                                          modal_depth.DA3_OVERHEAD_S)
    assert modal_depth._clip_est(4835, 35) == pytest.approx(sg.depth_est_usd(4835, 35)) and 1.25 < sg.depth_est_usd(4835, 35) < 1.35
    # Phase 1's floor run measured 497 s for 547 frames. At that rate the 35 finals would NOT fit the $1.70 cap: the plan's
    # 0.25 s a frame is a bet on a tenth of the transfer, and only the smoke run can say (call 64)
    assert sg.PHASE1_MEASURED_S_PER_FRAME == pytest.approx(497 / 547, abs=0.01)
    assert sg.depth_est_usd(4835, 35, sg.PHASE1_MEASURED_S_PER_FRAME) > modal_depth.CLIP_CAPS["depth"]


def _depth_smoke(card, s_per_frame, n=121):
    with open(card / "runs" / "modal_spend.jsonl", "a") as fh:
        fh.write(json.dumps({"task": "3.1-depth-smoke", "status": "ok", "n": n, "wall_s": 60 + modal_depth.DA3_LOAD_S + n * s_per_frame,
                             "usd_upper": 0.1, "gpu": "L40S", "phase": 3}) + "\n")


def test_the_projection_reads_the_smoke_lines_own_numbers(card):
    _depth_smoke(card, 0.5)
    proj = sg.projection_from_smoke("3.1-depth-smoke", 4835, modal_depth.DA3_LOAD_S, sg.rate_per_s("L40S", 4, 16))
    assert proj["s_per_unit"] == pytest.approx(0.5) and proj["units"] == 121
    assert proj["projected_usd"] == pytest.approx((90 + 60 + 4835 * 0.5) * sg.rate_per_s("L40S", 4, 16))
    assert sg.projection_from_smoke("3.1-nothing", 10, 90, 0.001) is None


def test_the_depth_run_is_refused_when_the_smokes_own_rate_does_not_fit(card, monkeypatch, capsys):
    make_clip(ClipSpec("air", "gen45", "D", 5)), make_clip(ClipSpec("air", "gen45", "B", 5))
    calls = fake_depth(monkeypatch)
    _depth_smoke(card, 12.0)                                           # 12 s a frame: 242 frames would be $1.9
    with pytest.raises(SystemExit) as e:
        modal_depth.run_clips()
    assert "does not fit" in str(e.value.code) and "no cap was raised" in str(e.value.code) and calls == []
    assert "re-estimated from the smoke run: 12.00 s a frame" in capsys.readouterr().out


def test_a_smoke_that_fits_lets_depth_run_and_the_dry_run_prints_the_projection(card, monkeypatch, capsys):
    make_clip(ClipSpec("air", "gen45", "D", 5))
    calls = fake_depth(monkeypatch)
    _depth_smoke(card, 0.3)
    modal_depth.run_clips()
    assert calls and "re-estimated from the smoke run: 0.30 s a frame" in capsys.readouterr().out
    r = _run_dry("modal_depth.py", "clips", "--dry-run", tmp_path=card)       # a fresh process with its own runs/: no smoke line
    assert r.returncode == 0 and "estimate $" in r.stdout


def test_with_no_depth_smoke_the_full_run_is_refused(card, monkeypatch, capsys):
    make_clip(ClipSpec("air", "gen45", "D", 5))
    calls = fake_depth(monkeypatch)
    with pytest.raises(SystemExit) as e:
        modal_depth.run_clips()
    assert "no ok smoke run is logged" in str(e.value.code) and calls == []
    assert not (card / "runs" / "modal_spend.jsonl").exists()
    modal_depth.run_clips(smoke=True)                                      # the smoke itself is never refused
    assert calls


def test_the_dry_run_of_the_full_depth_run_says_it_would_be_refused_without_a_smoke(card, capsys):
    make_clip(ClipSpec("air", "gen45", "D", 5))
    with pytest.raises(SystemExit) as e:
        modal_depth._dry_clips(False, "")
    assert e.value.code == 1                                           # the real refusal's code
    assert "the full run would be refused" in capsys.readouterr().out
    modal_depth._dry_clips(True, "")                                   # the smoke's dry run exits 0
    assert "would be refused" not in capsys.readouterr().out


def test_the_depth_calls_are_logged_with_their_wall_time_and_frame_counts(card, monkeypatch):
    make_clip(ClipSpec("air", "gen45", "D", 5))
    fake_depth(monkeypatch)
    modal_depth.run_clips(smoke=True)
    line = [json.loads(t) for t in (card / "runs" / "modal_spend.jsonl").read_text().splitlines()][-1]
    assert sum(u for _, u in line["calls"]) == 121 and line["calls"][0][1] == 0 and len(line["calls"]) == 1 + 6   # the fetch, then 6 batches


def test_the_reserve_and_the_depth_run_read_the_same_smoke_task():
    assert sg.DEPTH_SMOKE_TASK == modal_depth.CLIP_TASKS["smoke"] and sg.DEPTH_LOAD_S == modal_depth.DA3_LOAD_S


# ---- batch 2 review fixes ----------------------------------------------------------------------------------------

def test_the_depth_smoke_defaults_to_the_air_d_clip_not_the_first_in_the_index(card):
    for p in "BDN":
        make_clip(ClipSpec("air", "gen45", p, 5))
    assert [s.id for s in modal_depth.plan_clips()[0]] == ["air__gen45__B__5s", "air__gen45__D__5s", "air__gen45__N__5s"]
    todo, n, line = modal_depth.plan_clips(smoke=True)
    assert [s.id for s in todo] == ["air__gen45__D__5s"] and n == 121 and "3.1-depth-smoke" in line
    assert [s.id for s in modal_depth.plan_clips(smoke=True, only="air__gen45__N__5s")[0]] == ["air__gen45__N__5s"]
    clipdepth.write_depth_npz(ClipSpec("air", "gen45", "D", 5), np.full((121, 48, 64), 0.5, np.float16))
    assert [s.id for s in modal_depth.plan_clips(smoke=True)[0]] == ["air__gen45__B__5s"]       # the smoke clip is done


def test_a_smoke_run_makes_the_air_d_clip(card, monkeypatch):
    for p in "BD":
        make_clip(ClipSpec("air", "gen45", p, 5))
    fake_depth(monkeypatch)
    modal_depth.run_clips(smoke=True)
    assert clipdepth.check_depth(ClipSpec("air", "gen45", "D", 5))["ok"]
    assert not clips.depth_path(ClipSpec("air", "gen45", "B", 5)).exists()


def test_the_dry_runs_never_write_the_clips_index(card, monkeypatch, capsys):
    make_clip(ClipSpec("air", "gen45", "D", 5))
    modal_depth.plan_clips()
    modal_depth._dry_clips(True, "")
    assert not (card / "runs" / "clips_index.json").exists()
    r = _run_dry("modal_depth.py", "clips", "--dry-run", "--smoke", tmp_path=card)
    assert r.returncode == 0 and not (card / "runs" / "clips_index.json").exists()
    fake_depth(monkeypatch)
    modal_depth.run_clips(smoke=True)                                   # the real run still writes it
    assert (card / "runs" / "clips_index.json").exists()


def test_empty_depth_and_track_plans_estimate_zero_dollars(card):
    todo, n, line = modal_depth.plan_clips()
    assert todo == [] and n == 0 and "estimate $0.00" in line
    todo, n, line = modal_depth.plan_tracks()
    assert todo == [] and n == 0 and "estimate $0.00" in line
    assert sg.depth_est_usd(0, 0) == 0.0 and sg.depth_est_usd(121, 1) > 0.1


def _depth_smoke_with_calls(card, local_s):
    """An ok depth smoke of one 121-frame clip: a download, then six 24-frame batches (the first with the load), then
    `local_s` of local decode, encode, median, savez and check."""
    calls = [[30.0, 0], [95.0, 24], [12.0, 24], [12.0, 24], [12.0, 24], [12.0, 24], [1.0, 1]]
    with open(card / "runs" / "modal_spend.jsonl", "a") as fh:
        fh.write(json.dumps({"task": "3.1-depth-smoke", "status": "ok", "n": 121, "usd_upper": 0.0, "gpu": "L40S", "phase": 3,
                             "calls": calls, "wall_s": 60 + sum(c[0] for c in calls) + local_s}) + "\n")


def test_the_full_depth_projection_counts_the_smokes_local_work_per_clip(card):
    _depth_smoke_with_calls(card, local_s=10)
    quick = modal_depth._clip_projection(1210, False, 10)
    _depth_smoke_with_calls(card, local_s=80)
    slow = modal_depth._clip_projection(1210, False, 10)
    assert quick["per_clip_s"] == sg.DEPTH_OVERHEAD_S and slow["per_clip_s"] == pytest.approx(80.0)
    assert slow["projected_usd"] - quick["projected_usd"] == pytest.approx(10 * (80 - 20) * sg.rate_per_s("L40S", 4, 16))
    assert modal_depth._clip_projection(1210, True, 10) is None


def test_the_depth_run_passes_its_clip_count_to_the_projection(card, monkeypatch, capsys):
    for p in "BN":
        make_clip(ClipSpec("air", "gen45", p, 5))
    calls = fake_depth(monkeypatch)
    _depth_smoke_with_calls(card, local_s=1300)      # 1,300 s of local work a clip: two clips add 2,600 s, which passes $1.70
    with pytest.raises(SystemExit) as e:
        modal_depth.run_clips()
    assert "does not fit" in str(e.value.code) and calls == []
    (card / "runs" / "modal_spend.jsonl").unlink()
    _depth_smoke_with_calls(card, local_s=10)        # the same smoke with quick local work fits
    modal_depth.run_clips()
    assert calls


def test_the_dry_run_exits_1_when_the_depth_projection_does_not_fit_and_0_when_it_does(card, monkeypatch, capsys):
    make_clip(ClipSpec("air", "gen45", "D", 5))
    _depth_smoke(card, 40.0)                                           # 40 s a frame: 121 frames are about $3
    with pytest.raises(SystemExit) as e:
        modal_depth._dry_clips(False, "")
    assert e.value.code == 1
    out = capsys.readouterr().out
    assert "re-estimated from the smoke run: 40.00 s a frame" in out and "the full run would be refused" in out
    with open(card / "runs" / "modal_spend.jsonl", "w") as fh:
        fh.write(json.dumps({"task": "3.1-depth-smoke", "status": "ok", "n": 121, "usd_upper": 0.0, "wall_s": 60 + 90 + 121 * 0.3,
                             "phase": 3}) + "\n")
    modal_depth._dry_clips(False, "")                                  # fits: returns, exit 0
    assert "would be refused" not in capsys.readouterr().out
