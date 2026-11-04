import json

import cv2
import numpy as np
import pytest

import clips
import probes
from clips import ClipSpec
from recordings import RECORDING_NAMES
from synth_video import write_mp4

W, H = 640, 360


def texture(seed=0, w=W * 2, h=H * 2):
    """A smooth multi-scale texture: SIFT and flow both have something to hold on to."""
    rng = np.random.default_rng(seed)
    img = np.zeros((h, w), np.float32)
    for s in (3, 7, 15):
        img += cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), s) * s
    img = (img - img.min()) / (np.ptp(img) + 1e-9)
    return cv2.cvtColor((img * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


def zoomed(base, s, dx=0.0, dy=0.0):
    """The centre WxH window of `base`, magnified by s about the frame centre, shifted by (dx, dy) px."""
    M = np.array([[s, 0, (1 - s) * W / 2 + dx + (base.shape[1] - W) / 2 * 0],
                  [0, s, (1 - s) * H / 2 + dy]])
    big = cv2.resize(base, (W, H), interpolation=cv2.INTER_AREA)
    return cv2.warpAffine(big, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def zoom_clip(total, n=49, base=None, **kw):
    base = texture() if base is None else base
    return [zoomed(base, total ** (i / (n - 1)), **kw) for i in range(n)]


def test_sift_recovers_a_known_zoom_and_shift():
    fr = zoom_clip(1.20, dx=6.0)
    r = probes.sift_similarity(fr[0], fr[-1])
    assert r["inliers"] >= 30 and r["scale"] == pytest.approx(1.20, abs=0.02)
    # both ends carry the 6 px shift, but magnification moves the shifted centre: the net centre move is (s - 1) * 6 px
    assert abs(r["rotation_deg"]) < 0.5 and r["shift_frac"] == pytest.approx(0.20 * 6.0 / W, abs=0.001)


def test_sift_reports_nothing_rather_than_guess_on_a_blank_pair():
    flat = np.full((H, W, 3), 90, np.uint8)
    r = probes.sift_similarity(flat, flat)
    assert r["scale"] is None and probes.reading(r["scale"]) == "unmeasured"


def test_flow_zoom_accumulates_along_the_clip():
    s = probes.flow_zoom(zoom_clip(1.20))
    assert s["scale"] == pytest.approx(1.20, abs=0.04) and s["steps"] == 48
    assert probes.flow_zoom(zoom_clip(0.85))["scale"] == pytest.approx(0.85, abs=0.04)
    hold = probes.flow_zoom([zoomed(texture(), 1.0)] * 10)
    assert hold["scale"] == pytest.approx(1.0, abs=0.002)


def test_mean_change_is_zero_for_a_held_clip_and_grows_with_motion():
    still = [zoomed(texture(), 1.0)] * 6
    assert probes.mean_change(still) == {"frame_to_frame": 0.0, "first_to_last": 0.0}
    assert probes.mean_change(zoom_clip(1.3, n=6))["frame_to_frame"] > 1.0


def test_reading_bands():
    assert [probes.reading(x) for x in (1.2, 1.0, 0.9, None)] == ["forward", "hold", "back", "unmeasured"]


@pytest.fixture
def probe_round(tmp_path, monkeypatch):
    """Two recordings' probes: D glides forward, B holds, N glides a little; the third recording is missing."""
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path))
    monkeypatch.setitem(clips.GRID, "gen45", (W, H))
    for i, cond in enumerate(list(RECORDING_NAMES)[:2]):
        for p, total in (("D", 1.25), ("B", 1.0), ("N", 1.06)):
            spec = ClipSpec(cond, "gen45", p, 2, "probe")
            write_mp4(clips.video_path(spec), zoom_clip(total + 0.01 * i if total != 1.0 else 1.0, base=texture(i)))
    return tmp_path


def test_the_report_counts_forward_probes_per_prompt_and_only_reports(probe_round):
    rep = probes.build_report()
    assert rep["summary"]["D"] == {"probes": 2, "forward_sift": 2, "forward_flow": 2, "unmeasured_sift": 0,
                                   "unmeasured_flow": 0, "moved": 2, "unmeasured": 0}
    assert rep["summary"]["B"]["forward_sift"] == 0 and rep["summary"]["B"]["forward_flow"] == 0 and rep["summary"]["B"]["moved"] == 0
    assert rep["summary"]["N"]["forward_sift"] == 2 and rep["summary"]["N"]["moved"] == 2        # kill rule 2's own direction
    d = rep["probes"]["air__gen45__D__probe2s"]
    assert d["sift"]["scale"] == pytest.approx(1.25, abs=0.03) and d["flow"]["scale"] == pytest.approx(1.25, abs=0.05)
    assert d["frames"] == 49 and d["seed"] == clips.seed_for(ClipSpec("air", "gen45", "D", 2, "probe"))
    on_disk = json.loads((probe_round / "probes.json").read_text())
    assert on_disk == rep
    assert not (probe_round / "clips_index.json").exists()           # reporting never touches the finals index


def test_the_sheet_has_a_row_per_recording_and_a_column_per_prompt(probe_round):
    rep = probes.build_report()
    p = probes.make_sheet(rep, w=160)
    img = cv2.imread(str(p))
    assert p.name == "probes.jpg" and p.parent.name == "sheets"
    h = int(round(H * 160 / W))
    assert img.shape[:2] == (28 + 5 * h, 6 * 160)
    cell = lambda r, c: img[28 + r * h: 28 + (r + 1) * h, c * 320:(c + 1) * 320]
    assert cell(2, 0).std() < 40 and cell(0, 0).std() > 10          # recording 3 is missing: a flat, labelled blank
    first, last = cell(0, 0)[:, :160].astype(float), cell(0, 0)[:, 160:].astype(float)
    assert np.abs(first - last).mean() > 3                           # a glide: the two halves differ


def test_a_sheet_with_no_probes_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path))
    with pytest.raises(SystemExit, match="no probes"):
        probes.make_sheet({"probes": {}})


def test_the_module_never_touches_a_prompt():
    import inspect
    src = inspect.getsource(probes)
    assert "PROMPTS" not in src and "prompts import" not in src


# ---- the reviewer's findings: turbid water must not read as "hold", and B and N are read for any movement --------

def low_contrast(frames, contrast, sigma, seed=1):
    rng = np.random.default_rng(seed)
    out = []
    for f in frames:
        g = 128 + (f.astype(np.float32) - 128) * contrast + rng.normal(0, sigma, f.shape)
        out.append(np.clip(g, 0, 255).astype(np.uint8))
    return out


def test_a_zoom_at_5_percent_contrast_with_noise_is_unmeasured_not_hold():
    fr = low_contrast(zoom_clip(1.25), 0.05, 2.0)
    s = probes.flow_zoom(fr)
    assert s["scale"] is None and s["texture"] < probes.MIN_TEXTURE
    r = probes.probe_numbers(fr)
    assert r["flow_reading"] == "unmeasured" and r["sift_reading"] == "unmeasured" and r["moved"] is None


def test_pure_noise_is_unmeasured_and_a_real_hold_is_still_a_hold():
    rng = np.random.default_rng(4)
    noise = [rng.integers(0, 255, (H, W, 3), dtype=np.uint8) for _ in range(8)]
    assert probes.flow_zoom(noise)["scale"] is None                      # textured everywhere, but the fit leaves a large residual
    hold = probes.flow_zoom([zoomed(texture(), 1.0)] * 8)
    assert hold["scale"] == pytest.approx(1.0, abs=0.002) and probes.reading(hold["scale"]) == "hold"


def test_a_zoom_at_moderate_contrast_is_still_measured():
    s = probes.flow_zoom(low_contrast(zoom_clip(1.25), 0.2, 1.0))
    assert s["scale"] == pytest.approx(1.25, abs=0.05) and probes.MIN_TEXTURE < s["texture"] < 0.9


def test_moved_counts_any_reading_or_a_sideways_shift():
    base = {"sift": {"shift_frac": 0.0}, "sift_reading": "hold", "flow_reading": "hold"}
    assert probes.moved(base) is False
    assert probes.moved({**base, "flow_reading": "forward"}) and probes.moved({**base, "sift_reading": "back"})
    assert probes.moved({**base, "sift": {"shift_frac": 0.05}}) and not probes.moved({**base, "sift": {"shift_frac": 0.01}})
    # one reading that says "hold" is a measurement: held. Nothing measured at all is not "held" but unknown.
    assert probes.moved({**base, "sift": {"shift_frac": None}, "flow_reading": "unmeasured"}) is False
    nothing = {"sift": {"shift_frac": None}, "sift_reading": "unmeasured", "flow_reading": "unmeasured"}
    assert probes.moved(nothing) is None
    assert probes.moved({**nothing, "flow_reading": "forward"}) is True


def test_the_summary_counts_unmeasured_probes_apart_from_held_ones(probe_round, monkeypatch):
    real = probes.probe_numbers
    def fake(frames):
        r = real(frames)
        if r["sift_reading"] == "hold" and r["flow_reading"] == "hold":      # B: pretend nothing could be measured
            r.update(sift={**r["sift"], "scale": None, "shift_frac": None}, flow={**r["flow"], "scale": None},
                     sift_reading="unmeasured", flow_reading="unmeasured", moved=None)
        return r
    monkeypatch.setattr(probes, "probe_numbers", fake)
    b = probes.build_report()["summary"]["B"]
    assert b["moved"] == 0 and b["unmeasured"] == 2 and b["unmeasured_sift"] == 2 and b["unmeasured_flow"] == 2


def test_the_sheet_never_rewrites_the_checked_probes_index(probe_round):
    rep = probes.build_report()
    before = (probe_round / "probes_index.json").read_text()
    write_mp4(clips.video_path(ClipSpec(list(RECORDING_NAMES)[2], "gen45", "D", 2, "probe")), zoom_clip(1.1, n=20))   # a bad one: wrong length
    probes.make_sheet(rep, w=160)
    assert (probe_round / "probes_index.json").read_text() == before


def test_an_unreadable_mp4_is_drawn_as_an_unreadable_cell_not_a_crash(probe_round):
    rep = probes.build_report()
    clips.video_path(ClipSpec("air", "gen45", "D", 2, "probe")).write_bytes(b"not a video at all")
    img = cv2.imread(str(probes.make_sheet(rep, w=160)))
    assert img is not None and img.shape[1] == 6 * 160


def test_a_sheet_of_nothing_but_unreadable_probes_still_draws_the_cells(probe_round):
    rep = probes.build_report()
    for cond in RECORDING_NAMES:
        for p in "DBN":
            clips.video_path(ClipSpec(cond, "gen45", p, 2, "probe")).write_bytes(b"not a video at all")
    img = cv2.imread(str(probes.make_sheet(rep, w=160)))
    assert img is not None and img.shape[1] == 6 * 160 and img.shape[0] == 28 + len(RECORDING_NAMES) * round(720 * 160 / 1280)
    for f in clips.video_path(ClipSpec("air", "gen45", "D", 2, "probe")).parent.glob("*probe2s.mp4"):
        f.unlink()
    with pytest.raises(SystemExit, match="no probes on disk"):            # truly nothing on disk is still an error
        probes.make_sheet(rep, w=160)


def test_the_readings_sit_on_the_last_half_only_and_the_font_is_small(probe_round):
    import inspect
    src = inspect.getsource(probes._label)
    assert "0.45" in src and "0.5," not in src
    mk = inspect.getsource(probes.make_sheet)
    assert "_label(cell[:, w:]" in mk and "_label(cell, f\"sift" not in mk
