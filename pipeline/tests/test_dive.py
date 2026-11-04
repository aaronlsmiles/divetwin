import dataclasses
import json

import numpy as np
import pytest

import dive as dive_mod
from dive import (SELFTEST_TRAVEL_SU, TRUSTED_TRAVEL_SU, choose_primary, fill_nearest, frame_products, make_tank,
                  run_clip, score_path, selftest_renders)
from mapping import box_intrinsics, candidate_boxes
from camera import Pose, straight_path
from pose import track_path
from render import render
from synth import TANK, corridor_colors, corridor_depth
from units import Intrinsics

K_REAL = Intrinsics(fx=830.0, fy=830.0, cx=639.5, cy=359.5, width=1280, height=720)  # a small "real" camera
FXB = 830.0 * 63.0
WORK = (640, 360)
FILL = (0.0, 0.0, 1280.0, 720.0)


@pytest.fixture(scope="module")
def tank():
    k_half = box_intrinsics(K_REAL, FILL, 640, 360)
    z = corridor_depth(k_half, Pose.identity())
    disp_half = (FXB / z) / 2.0  # stored in half-resolution pixels
    colors = corridor_colors(k_half, Pose.identity(), z)
    t = make_tank("synthetic", K_REAL, FXB, disp_half.astype(np.float32), colors, floor=0.05, work=WORK)
    assert t.far_end == pytest.approx(TANK["z_far"], rel=1e-3)  # pins the half-to-full disparity x2
    return t


def _clip(tank, path, fish_from=None, box=FILL, grid=WORK):
    k = tank.k_grid(box, *grid)
    frames, inv = [], []
    for p in path:
        rd = render(tank.mesh, k, p)
        frames.append(fill_nearest(rd.color, rd.seen))
        inv.append(fill_nearest(np.nan_to_num(rd.inv_depth), rd.seen))
    inv = np.array(inv)
    if fish_from is not None:
        inv[fish_from:, 120:240, 220:420] *= 3.0  # about 10 % of the frame: something near the camera the tank does not have
    return frames, inv


def test_faithful_clip_scores_zero(tank):
    path = straight_path()
    frames, inv = _clip(tank, path)
    entry, arrays = run_clip(tank, frames, inv, None, FILL, primary="tracks", clip_id="faithful")
    assert entry["fit"]["s"] == pytest.approx(FXB, rel=1e-3)
    assert np.linalg.norm(arrays["C"][-1] - path[-1].C) < 0.01 * 200
    assert np.nanmax(entry["abs_rel"]) < 0.01 and entry["first_D3"] is None
    assert entry["verified"][0] > 0.99
    assert entry["lost_from"] is None and entry["tracks"]["lost_from"] is None
    assert entry["path_disagreement"] < 0.05 * 200 and entry["path_disagreement_frame"] == 48
    assert entry["far_end_valid"] is True and entry["far_end"] == pytest.approx(TANK["z_far"], rel=1e-3)
    json.dumps(entry, allow_nan=False)


def test_planted_fish_shows_as_heat_and_never_moves_the_path(tank):
    path = straight_path()
    frames, inv = _clip(tank, path, fish_from=10)
    entry, arrays = run_clip(tank, frames, inv, None, FILL, primary="icp", clip_id="fish")
    clean, _ = run_clip(tank, *_clip(tank, path), None, FILL, primary="icp", clip_id="clean")
    assert np.linalg.norm(np.array(entry["path"][-1]) - np.array(clean["path"][-1])) < 0.01 * 200
    assert entry["abs_rel"][20] > 5 * clean["abs_rel"][20]
    assert entry["first_D3"] is not None and entry["first_D3"] >= 10


def test_moving_mask_takes_the_fish_out(tank):
    path = straight_path()
    frames, inv = _clip(tank, path, fish_from=10)
    moving = np.zeros(inv.shape, bool)
    moving[10:, 115:245, 215:425] = True
    entry, _ = run_clip(tank, frames, inv, moving, FILL, primary="icp", clip_id="masked")
    assert np.nanmax(entry["abs_rel"]) < 0.01


def test_tracked_moving_pixels_are_not_verified(tank):
    """Call 63: tracked moving pixels are taken out of the verified set, so V(k) counts the same pixels D is read on
    (seen by the render and not tracked), not every pixel the render sees behind a tracked object (task 3.3)."""
    path = straight_path()
    frames, inv = _clip(tank, path, fish_from=10)
    moving = np.zeros(inv.shape, bool)
    moving[10:, 115:245, 215:425] = True
    share = moving[10].mean()                                   # about 12 % of the frame
    masked, _ = run_clip(tank, frames, inv, moving, FILL, primary="icp", clip_id="masked")
    free, _ = run_clip(tank, frames, inv, None, FILL, primary="icp", clip_id="free")
    assert masked["verified"][5] == pytest.approx(free["verified"][5], abs=1e-6)   # before the track: unchanged
    for i in (10, 20, 40):
        assert masked["verified"][i] == pytest.approx(free["verified"][i] - share, abs=0.01)


def test_selftest_on_perfect_depth(tank):
    frames, inv, truth = selftest_renders(tank)
    assert len(frames) == 49 and inv.shape == (49, 360, 640)
    k = tank.k_grid(FILL, *WORK)
    d0, ok0 = tank.on_grid(FILL, *WORK)
    tr = track_path(frames, k, np.where(ok0, d0 / FXB, np.nan), render_inv=lambda p: render(tank.mesh, k, p).inv_depth)
    s = score_path([o["pose"] for o in tr], truth, SELFTEST_TRAVEL_SU, None)
    assert s["endpoint_err_frac"] < 0.01


def test_choose_primary_rule():
    def sc(t, i):
        return {"tracks": {"endpoint_err_frac": t}, "icp": {"endpoint_err_frac": i}}
    assert choose_primary({"a": sc(0.01, 0.30), "b": sc(0.02, 0.25), "c": sc(0.01, 0.4)}) == "tracks"
    assert choose_primary({"a": sc(0.05, 0.06), "b": sc(0.05, 0.06)}) == "icp"  # within 2 %: section 7 keeps it


def test_cover_box_clip_scores_zero(tank):
    """The 704-row case: a cover crop (here 640 x 352 out of the 16:9 real frame)."""
    box = candidate_boxes(1280, 720, 640, 352)["cover"]
    assert box[3] == pytest.approx(704.0)
    path = straight_path()
    frames, inv = _clip(tank, path, box=box, grid=(640, 352))
    for primary in ("tracks", "icp"):
        entry, arrays = run_clip(tank, frames, inv, None, box, primary=primary, clip_id="cover")
        assert entry["grid"] == [640, 352]
        assert entry["fit"]["s"] == pytest.approx(FXB, rel=1e-3)
        assert np.linalg.norm(arrays["C"][-1] - path[-1].C) < 0.01 * 200
        assert np.nanmax(entry["abs_rel"]) < 0.01 and entry["verified"][0] > 0.99


def _blank_from(frames, k):
    return [f if i < k else np.full_like(f, 128) for i, f in enumerate(frames)]


def test_entry_is_strict_json_when_lost(tank):
    path = straight_path()
    frames, inv = _clip(tank, path)
    entry, _ = run_clip(tank, _blank_from(frames, 20), inv, None, FILL, primary="tracks", clip_id="lost20")
    assert entry["lost_from"] == 20
    json.dumps(entry, allow_nan=False)
    assert entry["abs_rel"][20] is None and entry["D"][25] is None and entry["verified"][30] is None
    assert entry["abs_rel"][19] is not None


def test_path_disagreement_when_lost_at_frame_one(tank):
    path = straight_path()
    frames, inv = _clip(tank, path)
    entry, _ = run_clip(tank, _blank_from(frames, 1), inv, None, FILL, primary="icp", clip_id="lost1")
    assert entry["tracks"]["lost_from"] == 1
    assert entry["path_disagreement"] is None and entry["path_disagreement_frame"] == 0
    json.dumps(entry, allow_nan=False)


@pytest.mark.parametrize("floor", [None, float("nan"), float("inf")])
def test_run_clip_needs_a_finite_floor(tank, floor):
    frames, inv = _clip(tank, straight_path(n=3, travel=10.0))
    with pytest.raises(ValueError, match="floor"):
        run_clip(dataclasses.replace(tank, floor=floor), frames, inv, None, FILL, primary="icp")


def test_unmeasured_far_end_is_null(tank):
    path = straight_path()
    frames, inv = _clip(tank, path)
    entry, _ = run_clip(dataclasses.replace(tank, far_end=float("nan")), frames, inv, None, FILL, primary="icp")
    assert entry["far_end"] is None and entry["wall_frame"] is None and entry["far_end_valid"] is False
    json.dumps(entry, allow_nan=False)


def test_run_clip_checks_its_inputs(tank):
    frames, inv = _clip(tank, straight_path(n=3, travel=10.0))
    with pytest.raises(AssertionError):
        run_clip(tank, frames[:2], inv, None, FILL, primary="icp")
    with pytest.raises(AssertionError):
        run_clip(tank, frames, inv, np.zeros((3, 360, 641), bool), FILL, primary="icp")


def test_fill_nearest_refuses_an_unseen_frame():
    with pytest.raises(ValueError):
        fill_nearest(np.arange(12.0).reshape(3, 4), np.zeros((3, 4), bool))


def test_floating_fit_on_degenerate_depth_is_null(tank):
    k = tank.k_grid(FILL, *WORK)
    d0, ok0 = tank.on_grid(FILL, *WORK)
    from align import huber_affine_fit
    fit = huber_affine_fit(d0 / FXB, d0, ok0)
    fp = frame_products(tank, k, np.full((360, 640), 1e-3), np.zeros((360, 640), bool), fit, Pose.identity())
    assert fp["fit_float"] is None and np.all(np.isnan(fp["residual_float"]))


def test_score_path_reports_the_worst_yaw():
    truth = straight_path()
    est = [p.copy() for p in truth]
    est[12] = Pose(np.eye(3), truth[12].C.copy())  # yaw 0 where the truth is at +3 degrees
    s = score_path(est, truth, SELFTEST_TRAVEL_SU, None)
    assert s["yaw_err_deg_end"] == pytest.approx(0.0, abs=1e-9)
    assert s["yaw_err_deg_max"] == pytest.approx(3.0, abs=1e-6)


def test_run_clip_hands_moving_to_track_path(tank, monkeypatch):
    frames, inv = _clip(tank, straight_path(n=4, travel=10.0))
    moving = np.zeros(inv.shape, bool)
    moving[1:, 100:140, 100:160] = True
    calls = []
    orig = dive_mod.track_path

    def spy(*a, **kw):
        calls.append(kw)
        return orig(*a, **kw)

    monkeypatch.setattr(dive_mod, "track_path", spy)
    run_clip(tank, frames, inv, moving, FILL, primary="tracks", clip_id="spy")
    assert len(calls) == 1 and calls[0].get("moving") is not None
    assert np.array_equal(calls[0]["moving"], moving)


def test_selftest_travel_is_one_constant(tank):
    assert SELFTEST_TRAVEL_SU == 200.0
    _, _, truth = selftest_renders(tank)
    assert truth[-1].C[2] == pytest.approx(SELFTEST_TRAVEL_SU)
    assert straight_path()[-1].C[2] == pytest.approx(SELFTEST_TRAVEL_SU)  # camera.py's default agrees


# ---- call 50: pellets' dives are trusted to 100 su of forward travel ------------------------------------------

def test_only_pellets_has_a_trusted_travel():
    assert TRUSTED_TRAVEL_SU == {"saltwater-pellets": 100.0}
    for cond in ("air", "freshwater", "freshwater-basicEnhance", "saltwater"):
        assert TRUSTED_TRAVEL_SU.get(cond) is None


@pytest.fixture(scope="module")
def straight_clip(tank):
    path = straight_path()                      # 200 su forward over 49 frames: frame 24 sits at 100 su
    frames, inv = _clip(tank, path)
    free, _ = run_clip(tank, frames, inv, None, FILL, primary="tracks", clip_id="free")
    capped, arrays = run_clip(tank, frames, inv, None, FILL, primary="tracks", clip_id="capped", trusted_travel=100.0)
    return free, capped, arrays


def test_frames_past_the_trusted_travel_are_unverifiable_and_earlier_frames_untouched(straight_clip):
    free, capped, arrays = straight_clip
    C, R0 = arrays["C"], arrays["R"][0]
    fwd = (C - C[0]) @ R0[:, 2]                 # forward travel along the frame-0 viewing axis, su
    first = int(np.argmax(fwd > 100.0))
    assert fwd[first] > 100.0 and fwd[first - 1] <= 100.0 and 23 <= first <= 26
    assert capped["trusted_travel_su"] == 100.0 and capped["first_capped_frame"] == first
    for key in ("verified", "abs_rel", "D", "D_float"):
        assert capped[key][:first] == free[key][:first], key
    assert all(v == 0.0 for v in capped["verified"][first:])
    for key in ("abs_rel", "D", "D_float"):            # no heat past the cap
        assert all(v is None for v in capped[key][first:]), key
    assert capped["path"] == free["path"] and capped["lost_from"] == free["lost_from"]   # the path itself is not capped
    json.dumps(capped, allow_nan=False)


def test_a_clip_without_a_cap_is_untouched(straight_clip):
    free, _, _ = straight_clip
    assert free["trusted_travel_su"] is None and free["first_capped_frame"] is None
    assert all(v is not None and v > 0.9 for v in free["verified"])
    assert all(v is not None for v in free["D"])
    json.dumps(free, allow_nan=False)


def test_a_cap_the_path_never_reaches_caps_nothing(tank):
    frames, inv = _clip(tank, straight_path(n=9, travel=50.0))
    free, _ = run_clip(tank, frames, inv, None, FILL, primary="tracks")
    capped, _ = run_clip(tank, frames, inv, None, FILL, primary="tracks", trusted_travel=100.0)
    assert capped["first_capped_frame"] is None and capped["trusted_travel_su"] == 100.0
    assert capped["verified"] == free["verified"] and capped["D"] == free["D"]
