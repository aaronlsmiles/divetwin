import hashlib
import json
import tracemalloc
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

import assets
import cli
import clipdepth
import clips
import dive
import heat
import recordings
from align import AffineFit
from camera import straight_path
from cli import _dump
from dive import read_video, run_clip
from prompts import PROMPTS
from synth_video import write_mp4
from test_dive import FILL, FXB, WORK, _clip, tank  # noqa: F401,F811  (the module-scoped synthetic tank fixture)
from test_modal_helpers import PIPELINE

CID = "air__gen45__D__5s"
N = 25                                  # frames in the synthetic clips (a real 5 s clip has 121)


@pytest.fixture
def runs(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path))
    monkeypatch.setitem(clips.GRID, "gen45", WORK)
    return tmp_path


def fish_track(from_frame):
    """The tracked mask of the planted near object (test_dive._clip's fish): rows 120:240, columns 220:420, from a frame on."""
    m = np.zeros((N, WORK[1], WORK[0]), bool)
    m[from_frame:, 120:240, 220:420] = True
    return m


def make_dive(runs, tank, cid=CID, fish_from=None, trusted=None, lost=None, wall=None, moving=None):
    """A synthetic clip run through sub-plan A's run_clip and stored where cli.py dive stores it. `moving`: the SAM 2 track
    (N, H, W bool), written into the clip's depth npz as clipdepth does and kept out of the pose and out of D by run_clip."""
    spec = clips.parse_clip_id(cid)
    path = straight_path(N)
    frames, inv = _clip(tank, path, fish_from=fish_from)
    write_mp4(clips.video_path(spec), frames)
    clipdepth.write_depth_npz(spec, inv.astype(np.float16), moving)
    entry, arrays = run_clip(tank, frames, inv.astype(np.float16).astype(np.float64), moving, FILL, primary="tracks",
                             clip_id=cid, meta={"condition": spec.condition, "engine": "gen45", "prompt": spec.prompt,
                                                "seconds": 5, "take": None}, trusted_travel=trusted)
    if lost is not None:
        entry["lost_from"] = lost
    if wall is not None:
        entry["wall_frame"] = wall
    d = runs / "dive"
    d.mkdir(parents=True, exist_ok=True)
    _dump(d / f"{cid}.json", entry, indent=1)
    np.savez_compressed(d / f"{cid}.npz", fit=np.array([entry["fit"]["s"], entry["fit"]["t"]]), **arrays)
    _dump(runs / "mapping" / f"{cid}.json", {"box": list(FILL), "name": "fill", "ok": True})
    prior = json.loads((runs / "clips.json").read_text())["clips"] if (runs / "clips.json").exists() else []
    _dump(runs / "clips.json", {"clips": [e for e in prior if e["clip"] != cid] + [entry]})
    return entry


def frames_of(p):
    return read_video(p)


# ---- atlases ----------------------------------------------------------------------------------------

def test_a_121_frame_clip_packs_into_11_by_11_and_a_241_frame_clip_into_11_by_22():
    cells = [np.full((90, 160), i + 1, np.uint16) for i in range(241)]
    a121, a241 = assets.pack_atlas(cells[:121]), assets.pack_atlas(cells)
    assert a121.shape == (11 * 90, 11 * 160) and a241.shape == (22 * 90, 11 * 160)
    assert a241[0, 0] == 1 and a241[0, 160] == 2 and a241[90, 0] == 12
    assert a241[21 * 90, 160 * 9] == 241 and a241[21 * 90 + 89, 160 * 9 + 159] == 241      # frame 240: row 21, column 9
    assert (a241[21 * 90:, 160 * 10:] == 0).all()                                         # the unused cells stay empty
    assert a121[10 * 90, 160 * 10] == 121
    assert assets.relief_meta(121)["rows"] == 11 and assets.relief_meta(241)["rows"] == 22
    assert assets.relief_meta(241) == {"cols": 11, "rows": 22, "cell": [160, 90], "frames": 241, "depth_scale": 16.0,
                                       "unit": "su", "invalid": 0, "encoding": assets.PNG16_NOTE}
    assert "PNG16" in assets.PNG16_NOTE and "fast-png" in assets.PNG16_NOTE and "not canvas" in assets.PNG16_NOTE


def test_a_depth_cell_stores_su_times_16_and_zero_for_nothing():
    d = np.full((360, 640), FXB / 1000.0)                  # a flat wall at 1000 su
    d[:, :64] = np.nan
    c = assets.depth_cell(d, FXB)
    assert c.shape == (90, 160) and c.dtype == np.uint16
    assert c[45, 100] == 16000 and c[45, 2] == 0
    assert assets.depth_cell(np.zeros((8, 8)), FXB).max() == 0


def test_the_plan_profile_finds_the_walls_and_the_far_end(tank):
    prof = np.array(assets.tank_profile(tank))
    assert prof.shape[1] == 2 and len(prof) > 60
    assert np.median(prof[len(prof) // 2 - 5:len(prof) // 2 + 5, 1]) == pytest.approx(1300, rel=0.02)    # the far wall
    assert prof[:, 0].min() < -250 and prof[:, 0].max() > 250                                              # the side walls at +-300


# ---- one clip ----------------------------------------------------------------------------------------

def test_a_faithful_clip_gets_every_asset_and_the_bare_clip_is_byte_identical(runs, tank):
    make_dive(runs, tank)
    blk = assets.clip_assets(CID, tank)
    a = assets.assets_dir() / "clips" / CID
    assert set(blk["assets"]) == {"gen", "heat", "real", "poster", "poster_heat", "relief", "tank_relief", "path"}
    assert set(blk) == set(assets.BLOCK_KEYS)                  # one list of what a clip block is, kept whole by a partial rebuild
    assert all((assets.assets_dir() / p).exists() for p in blk["assets"].values())
    assert hashlib.sha256((a / "gen.mp4").read_bytes()).hexdigest() == hashlib.sha256(clips.video_path(clips.parse_clip_id(CID)).read_bytes()).hexdigest()
    for name in ("heat.mp4", "real.mp4"):
        r = clips.check_mp4(a / name, N, WORK)
        assert r["ok"], (name, r)
    assert blk["unverifiable_from"] is None and blk["unverifiable_reason"] is None
    assert blk["relief"]["rows"] == 3 and cv2.imread(str(a / "relief.png"), cv2.IMREAD_UNCHANGED).shape == (270, 1760)
    p = json.loads((a / "path.json").read_text())
    assert len(p["x"]) == len(p["z"]) == N and p["z"][-1] == pytest.approx(200, abs=3) and p["unit"] == "su"
    img = cv2.imread(str(a / "poster.jpg"))
    assert img.shape == (360, 640, 3)


def test_the_heat_is_quiet_on_a_faithful_clip_and_loud_on_a_planted_object(runs, tank):
    """Quiet is the dark end of the ramp everywhere (constant alpha over a dimmed frame: r = 0 is not the frame, and not grey);
    a planted near object is a light patch the size of the object."""
    make_dive(runs, tank)
    assets.clip_assets(CID, tank)
    lum = lambda f: heat.luminance(f[..., ::-1].astype(float))      # noqa: E731
    quiet = lum(frames_of(assets.assets_dir() / "clips" / CID / "heat.mp4")[12])
    assert np.percentile(quiet, 99) < 70 and np.median(quiet) < 50
    make_dive(runs, tank, fish_from=4)
    assets.clip_assets(CID, tank)
    loud = lum(frames_of(assets.assets_dir() / "clips" / CID / "heat.mp4")[12])
    box = loud[130:230, 230:410]                                    # where the near object sits
    assert box.mean() > 100 and box.mean() > quiet[130:230, 230:410].mean() + 60
    assert np.median(loud) < 60                                     # the rest of the frame stays quiet


def _luma(f):
    return heat.luminance(f[..., ::-1].astype(float))


def test_a_tracked_moving_object_is_drawn_with_the_signed_palette_and_outlined_not_hatched(runs, tank):
    """Call 69: the invention that swims is tracked, so it is out of the pose and out of D, but the heat still shows its
    frozen-fit residual over it, outlined (it used to be hatched as 'unverified')."""
    entry = make_dive(runs, tank, fish_from=4, moving=fish_track(4))
    assets.clip_assets(CID, tank)
    f = frames_of(assets.assets_dir() / "clips" / CID / "heat.mp4")[12].astype(float)
    inside = f[150:210, 260:380]                                          # well inside the track
    assert np.abs(inside[..., 2] - inside[..., 0]).mean() > 30           # a warm or cool ramp colour, not a neutral hatch grey
    assert _luma(inside).mean() > 150                                     # the planted object is loud (|r| clipped at 0.5)
    ring = _luma(f[119:121, 250:390]).mean()                              # the 2 px band round the track's top edge
    assert ring > _luma(inside).mean() + 25 and ring > 235
    assert np.median(_luma(f[:100])) < 60                                 # the rest of the frame stays quiet
    assert entry["abs_rel"][12] < 0.05                                    # and D never saw the object (dive.py, untouched)


def test_the_drawn_residual_adds_the_frozen_fit_residual_over_moving_pixels_the_render_saw_only():
    h, w = 6, 8
    fit = AffineFit(s=2.0, t=0.0, delta=0.0, c_tukey=0.0, n=0, n_inliers=0, iters=0)
    g = np.full((h, w), 0.5)                                              # fit.apply(g) = 1.0
    rd = SimpleNamespace(inv_depth=np.full((h, w), 1.0 / FXB * 0.8), seen=np.ones((h, w), bool))   # d_ren = 0.8
    rd.seen[:, 6:] = False                                                # the render never saw columns 6 and 7
    mv = np.zeros((h, w), bool)
    mv[1:5, 3:8] = True
    g[1, 4] = np.nan                                                      # one moving pixel with no generated depth
    verified = np.full((h, w), 0.07)
    verified[mv] = np.nan                                                 # what dive.frame_products leaves: NaN on the track
    verified[:, 6:] = np.nan
    r = assets.drawn_residual({"render": rd, "residual": verified}, g, mv, fit, FXB)
    assert np.allclose(r[1:5, 3:6][~np.isnan(r[1:5, 3:6])], 0.25)         # (1.0 - 0.8) / 0.8, the same signed formula
    assert np.isnan(r[1, 4])                                              # no generated depth: stays hatched
    assert np.isnan(r[:, 6:]).all()                                       # never seen: hatched, track or not
    assert np.isnan(r[0, 6]) and r[0, 0] == 0.07 and r[5, 3] == 0.07       # outside the track: dive's own residual, untouched
    assert (np.isfinite(r[2:5, 3:6])).all()


def test_a_clip_with_no_track_is_drawn_as_before_and_flags_no_moving_frame(runs, tank):
    make_dive(runs, tank, fish_from=4)
    blk = assets.clip_assets(CID, tank)
    assert blk["moving_track"] == [False] * N


def test_clips_json_marks_per_frame_whether_a_moving_track_is_present(runs, tank):
    make_dive(runs, tank, fish_from=4, moving=fish_track(10))
    blk = assets.clip_assets(CID, tank)
    assert blk["moving_track"] == [False] * 10 + [True] * (N - 10)
    assert "moving_track" in assets.BLOCK_KEYS


def test_past_the_cap_a_track_changes_nothing_everything_stays_hatched_and_the_flag_is_null(runs, tank):
    entry = make_dive(runs, tank, fish_from=4, trusted=100.0, moving=fish_track(4))
    cap = entry["first_capped_frame"]
    blk = assets.clip_assets(CID, tank)
    assert blk["moving_track"] == [i >= 4 for i in range(cap)] + [None] * (N - cap)
    heat_f = np.stack(frames_of(assets.assets_dir() / "clips" / CID / "heat.mp4"))
    gen = frames_of(clips.video_path(clips.parse_clip_id(CID)))
    want = np.stack([heat.grey_frame(g) for g in gen[cap:cap + 3]])
    assert np.abs(heat_f[cap:cap + 3].astype(float) - want).mean() < 4       # no ramp colour, no outline: all hatch
    assert np.abs(_luma(heat_f[cap + 1][119:121, 250:390]).mean() - _luma(want[1][119:121, 250:390]).mean()) < 12


def test_the_real_pane_is_the_tank_from_the_recovered_camera_and_grey_where_unseen(runs, tank):
    make_dive(runs, tank)
    assets.clip_assets(CID, tank)
    real = frames_of(assets.assets_dir() / "clips" / CID / "real.mp4")
    gen = frames_of(clips.video_path(clips.parse_clip_id(CID)))
    assert np.abs(real[0].astype(float) - gen[0]).mean() < 8                          # frame 0: the real camera's view
    assert len(real) == N and real[N - 1].std() > 5                                      # forward 200 su: still the tank


def test_pellets_style_cap_greys_every_asset_from_the_first_capped_frame(runs, tank):
    entry = make_dive(runs, tank, trusted=100.0)
    cap = entry["first_capped_frame"]
    assert cap is not None and 8 <= cap <= 16
    blk = assets.clip_assets(CID, tank)
    assert (blk["unverifiable_from"], blk["unverifiable_reason"]) == (cap, "travel cap")
    a = assets.assets_dir() / "clips" / CID
    heat_f, real_f = np.stack(frames_of(a / "heat.mp4")), np.stack(frames_of(a / "real.mp4"))
    gen = frames_of(clips.video_path(clips.parse_clip_id(CID)))
    want_grey = np.stack([heat.grey_frame(g) for g in gen[cap:cap + 3]])
    assert np.abs(heat_f[cap:cap + 3].astype(float) - want_grey).mean() < 4          # heat: the frame under grey, no residual
    assert np.abs(real_f[cap:].astype(float) - np.array(heat.GREY_RGB[::-1], float)).mean() < 3     # real pane: flat grey
    assert real_f[cap - 1].std() > 5                                                    # the last trusted frame is the tank
    atlas = cv2.imread(str(a / "relief.png"), cv2.IMREAD_UNCHANGED)
    cell = lambda i: atlas[(i // 11) * 90:(i // 11 + 1) * 90, (i % 11) * 160:(i % 11 + 1) * 160]
    assert cell(cap).max() == 0 and cell(N - 1).max() == 0 and cell(cap - 1).max() > 0
    assert json.loads((a / "path.json").read_text())["capped_from"] == cap


def test_a_lost_path_greys_the_same_way_and_says_so(runs, tank):
    make_dive(runs, tank, lost=15)
    blk = assets.clip_assets(CID, tank)
    assert (blk["unverifiable_from"], blk["unverifiable_reason"]) == (15, "path lost")
    atlas = cv2.imread(str(assets.assets_dir() / blk["assets"]["relief"]), cv2.IMREAD_UNCHANGED)
    assert atlas[(15 // 11) * 90:(15 // 11 + 1) * 90, (15 % 11) * 160:(15 % 11 + 1) * 160].max() == 0


def test_the_earlier_of_cap_and_lost_wins():
    assert assets.trusted_end({"first_capped_frame": 24, "lost_from": 30}) == (24, "travel cap")
    assert assets.trusted_end({"first_capped_frame": 40, "lost_from": 30}) == (30, "path lost")
    assert assets.trusted_end({}) == (None, None)


# ---- the per-pixel noise-floor map (call 48) ---------------------------------------------------------

def test_the_floor_map_is_the_median_relative_error_per_pixel():
    h, w, n = 20, 30, 9
    d = np.full((h, w), 100.0)
    ok = np.ones((h, w), bool)
    g = np.ones((n, h, w))
    g[:, :, :15] = 1.10                                     # the left half reads 10 % too near in every frame
    g[:, 5:8, 20:22] = 2.0                                  # one spot 100 % wrong in every frame
    fm, nobs, floor_check = assets.floor_map(d, ok, g, [(100.0, 0.0)] * n)
    assert fm[0, 0] == pytest.approx(0.10, abs=1e-6) and fm[0, 25] == pytest.approx(0.0, abs=1e-6)
    assert fm[6, 21] == pytest.approx(1.0, abs=1e-6) and (nobs == n).all()
    assert floor_check == pytest.approx((0.10 * 15 * 20 + 1.0 * 3 * 2) / (h * w), abs=1e-6)       # the floor's own statistic
    g2 = g.copy()
    g2[2] = 9.0                                              # one wild frame does not move a median
    fm2, _, fc2 = assets.floor_map(d, ok, g2, [(100.0, 0.0)] * n)
    assert np.allclose(fm2, fm, atol=1e-6, equal_nan=True) and fc2 == pytest.approx(floor_check)


def test_floor_check_is_the_median_over_frames_of_the_per_frame_mean_not_the_median_of_pixels():
    h, w, n = 10, 10, 5
    d, ok = np.full((h, w), 100.0), np.ones((h, w), bool)
    g = np.ones((n, h, w))
    for i, e in enumerate([0.1, 0.1, 0.1, 0.4, 0.4]):               # frame i reads e too near everywhere ...
        g[i] *= 1 + e
    g[:, :2, :] = 1.0                                             # ... except the top fifth, which is exact
    fm, _, floor_check = assets.floor_map(d, ok, g, [(100.0, 0.0)] * n)
    assert floor_check == pytest.approx(0.1 * 0.8)                # frame medians: 0.08, 0.08, 0.08, 0.32, 0.32
    assert np.nanmedian(fm) == pytest.approx(0.1)                 # the pixels' own medians: a different number


def test_excluded_and_unobserved_pixels_are_nan_not_zero():
    h, w, n = 10, 10, 9
    d, ok, g = np.full((h, w), 50.0), np.ones((h, w), bool), np.ones((n, h, w)) * 1.2
    ok[:, 0] = False
    excl = np.zeros((n, h, w), bool)
    excl[:6, 3, 3] = True                                    # excluded in 6 of 9 frames: 3 observations left
    excl[:, 5, 5] = True
    fm, nobs, _ = assets.floor_map(d, ok, g, [(50.0, 0.0)] * n, excl)
    assert np.isnan(fm[:, 0]).all() and np.isnan(fm[3, 3]) and np.isnan(fm[5, 5]) and nobs[3, 3] == 3
    assert fm[1, 1] == pytest.approx(0.2) and nobs[4, 4] == 9


def test_floor_png_and_preview_encode_unobserved_as_zero_and_grey():
    m = np.array([[np.nan, 0.0, 0.25, 0.5, 3.0]], np.float32)
    p = assets.floor_png(m)
    assert p[0].tolist() == [0, 1, 1 + round(0.5 * 65534), 65535, 65535]
    prev = assets.floor_preview(m)
    assert prev[0, 0, 0] == heat.hatch(1, 5)[0, 0] and (prev[0, 0, 0] == prev[0, 0]).all()      # unobserved: the hatch, no data
    assert tuple(prev[0, 4][::-1]) == heat.FLOOR_RAMP[-1][1] and tuple(prev[0, 1][::-1]) == heat.FLOOR_RAMP[0][1]
    lum = heat.luminance(prev[0, 1:4, ::-1])
    assert lum[0] < lum[1] < lum[2]
    pos = [c for _, c in heat.POSITIVE] + [c for _, c in heat.NEGATIVE]
    assert all(tuple(prev[0, i][::-1]) not in pos for i in range(5))                     # not the residual's ramps


# ---- recordings, clips.json, the manifest ------------------------------------------------------------

NULL_D = {"median": 0.012, "p90": 0.03, "n": 49}


def make_recording(runs, tank, floor=0.0, report=True):
    """A recording whose floor inputs are an exact fit (every error 0, so floor_check = 0) and the files recording_assets
    reads beside them: runs/floor/<name>.json and runs/selftest/report.json."""
    cv2.imwrite(str(runs / "left.png"), np.random.default_rng(3).integers(0, 255, (360, 640, 3), dtype=np.uint8))
    rec = SimpleNamespace(condition="air", name="air_rec", start_frame=0, left_path=lambda f: runs / "left.png")
    h, w, n = 36, 64, 9
    d, ok = tank.on_grid(assets.fill_box(tank), w, h)
    fi = (d, ok, np.where(ok, (d + 3.0) / FXB, 0.01)[None].repeat(n, 0), [(FXB, -3.0)] * n, np.zeros((n, h, w), bool))
    _dump(runs / "floor" / "air_rec.json", {"floor": floor})
    if report:
        _dump(runs / "selftest" / "report.json", {"air": {"null_dream_D": NULL_D, "null_dream_D_float": 0.011}})
    return rec, fi


def error_inputs(tank, e):
    """Floor inputs where every observed pixel of every frame is `e` too near: floor_check = e."""
    h, w, n = 36, 64, 9
    d, ok = tank.on_grid(assets.fill_box(tank), w, h)
    return (d, ok, np.where(ok, (1 + e) * d / FXB, 0.01)[None].repeat(n, 0), [(FXB, 0.0)] * n, np.zeros((n, h, w), bool))


def test_recording_assets_write_start_relief_floor_and_plan(runs, tank):
    rec, fi = make_recording(runs, tank)
    blk = assets.recording_assets(rec, tank, floor_inputs=fi)
    base = assets.assets_dir() / "recordings" / "air"
    for n in ("start.jpg", "tank_relief.png", "plan.json", "floor_map.png", "floor_preview.jpg"):
        assert (base / n).exists(), n
    tr = cv2.imread(str(base / "tank_relief.png"), cv2.IMREAD_UNCHANGED)
    assert tr.shape == (90, 160) and tr.dtype == np.uint16 and abs(int(np.median(tr[40:50, 70:90])) - 1300 * 16) < 0.03 * 1300 * 16
    assert blk["floor_map"]["display_only"] is True and blk["tank_relief"]["depth_scale"] == 16.0
    assert blk["floor_map"]["pixel_median"] == pytest.approx(0.0, abs=1e-3) and blk["trusted_travel_su"] is None
    plan = json.loads((base / "plan.json").read_text())
    assert plan["far_end"] == pytest.approx(1300, rel=0.01) and len(plan["profile"]) > 60


def test_the_floor_map_block_says_what_its_median_is_and_carries_the_floors_own_check(runs, tank):
    rec, _ = make_recording(runs, tank, floor=0.1)
    blk = assets.recording_assets(rec, tank, floor_inputs=error_inputs(tank, 0.1))
    fm = blk["floor_map"]
    assert "median" not in fm and fm["pixel_median"] == pytest.approx(0.1, abs=1e-3) and fm["floor_check"] == pytest.approx(0.1, abs=1e-3)
    assert "median over pixels" in fm["pixel_median_note"] and "not the floor" in fm["pixel_median_note"]
    json.dumps(blk, allow_nan=False)


def test_the_floor_map_must_reproduce_the_recordings_floor_within_two_percent(runs, tank):
    rec, _ = make_recording(runs, tank, floor=0.1019)                     # 1.9 % away: fine
    assets.recording_assets(rec, tank, floor_inputs=error_inputs(tank, 0.1))
    rec, _ = make_recording(runs, tank, floor=0.1025)                     # 2.4 % away: the map is not the floor's
    with pytest.raises(AssertionError, match="floor"):
        assets.recording_assets(rec, tank, floor_inputs=error_inputs(tank, 0.1))


def test_the_self_test_null_dream_numbers_ride_on_the_recording_block(runs, tank):
    rec, fi = make_recording(runs, tank)
    blk = assets.recording_assets(rec, tank, floor_inputs=fi)
    assert blk["null_dream_D"] == NULL_D and blk["null_dream_D_float"] == 0.011


def test_a_missing_self_test_report_fails_loudly(runs, tank):
    rec, fi = make_recording(runs, tank, report=False)
    with pytest.raises(RuntimeError, match="selftest"):
        assets.recording_assets(rec, tank, floor_inputs=fi)
    _dump(runs / "selftest" / "report.json", {"saltwater": {}})
    with pytest.raises(RuntimeError, match="air"):
        assets.recording_assets(rec, tank, floor_inputs=fi)


def test_every_png16_block_says_how_to_decode_it(runs, tank):
    rec, fi = make_recording(runs, tank)
    blk = assets.recording_assets(rec, tank, floor_inputs=fi)
    assert blk["tank_relief"]["encoding"] == blk["floor_map"]["encoding"] == assets.PNG16_NOTE
    make_dive(runs, tank)
    assert assets.clip_assets(CID, tank)["relief"]["encoding"] == assets.PNG16_NOTE


def test_the_pellets_block_carries_its_100_su_cap(runs, tank):
    rec, fi = make_recording(runs, tank)
    rec.condition = "saltwater-pellets"
    _dump(runs / "selftest" / "report.json", {"saltwater-pellets": {"null_dream_D": NULL_D, "null_dream_D_float": 0.011}})
    assert assets.recording_assets(rec, tank, floor_inputs=fi)["trusted_travel_su"] == 100.0


def test_clips_json_merges_the_dive_entries_with_assets_and_the_palette(runs, tank):
    entry = make_dive(runs, tank, trusted=100.0)
    rec, fi = make_recording(runs, tank)
    blk = assets.clip_assets(CID, tank)
    doc = assets.build_clips_json({CID: blk}, {"air": assets.recording_assets(rec, tank, floor_inputs=fi)})
    on_disk = json.loads((assets.assets_dir() / "clips.json").read_text())
    assert on_disk == doc and doc["unit"].startswith("uncorrected stereo units") and doc["heat"]["clip"] == 0.5
    (c,) = doc["clips"]
    assert c["D"] == entry["D"] and c["assets"]["heat"].endswith("heat.mp4") and c["unverifiable_reason"] == "travel cap"
    assert c["first_capped_frame"] == entry["first_capped_frame"] and c["relief"]["frames"] == N
    assert "NaN" not in (assets.assets_dir() / "clips.json").read_text()


def test_the_manifest_lists_every_file_with_its_hash_and_key_and_writes_media_md(runs, tank):
    make_dive(runs, tank)
    blk = assets.clip_assets(CID, tank)
    assets.build_clips_json({CID: blk}, {})
    man = assets.media_manifest()
    root = assets.assets_dir()
    names = {i["path"] for i in man["items"]}
    assert f"clips/{CID}/gen.mp4" in names and "clips.json" in names and "media_manifest.json" not in names
    assert f"clips/{CID}/tank_relief.png" in names
    for i in man["items"]:
        assert i["key"] == "divetwin/v1/" + i["path"] and i["sha256"] == hashlib.sha256((root / i["path"]).read_bytes()).hexdigest()
        assert i["bytes"] == (root / i["path"]).stat().st_size
    ct = {i["path"].rsplit(".", 1)[-1]: i["content_type"] for i in man["items"]}
    assert ct["mp4"] == "video/mp4" and ct["png"] == "image/png" and ct["jpg"] == "image/jpeg"
    md = (root / "MEDIA.md").read_text()
    assert "<!-- r2-manifest:begin -->" in md and "<!-- r2-manifest:end -->" in md and f"divetwin/v1/clips/{CID}/gen.mp4" in md
    assert man["cache_control"] == "public, max-age=31536000, immutable"
    assert assets.media_manifest() == man                       # deterministic: same files, same manifest


def test_the_manifest_marks_what_is_the_engines_own_file_and_what_is_derived(runs, tank):
    make_dive(runs, tank)
    blk = assets.clip_assets(CID, tank)
    assets.build_clips_json({CID: blk}, {})
    man = assets.media_manifest()
    origin = {i["path"]: i["origin"] for i in man["items"]}
    assert origin[f"clips/{CID}/gen.mp4"] == "original"
    assert {v for k, v in origin.items() if not k.endswith("gen.mp4")} == {"derived"}
    md = (assets.assets_dir() / "MEDIA.md").read_text()
    assert "| key | bytes | sha256 | origin |" in md and f"divetwin/v1/clips/{CID}/gen.mp4` | " in md
    row = [t for t in md.splitlines() if t.startswith(f"| `divetwin/v1/clips/{CID}/gen.mp4`")][0]
    assert row.rstrip().endswith("| original |")


def test_the_manifest_comes_from_the_files_clips_json_references_and_warns_about_the_rest(runs, tank):
    make_dive(runs, tank)
    blk = assets.clip_assets(CID, tank)
    assets.build_clips_json({CID: blk}, {})
    stray = assets.assets_dir() / "clips" / CID / "heat_old.mp4"
    stray.write_bytes(b"left over from an earlier build")
    (assets.assets_dir() / "notes.txt").write_text("not a page asset")
    with pytest.warns(UserWarning, match="unreferenced") as w:
        man = assets.media_manifest()
    names = {i["path"] for i in man["items"]}
    assert f"clips/{CID}/heat_old.mp4" not in names and "notes.txt" not in names
    assert man["unreferenced"] == [f"clips/{CID}/heat_old.mp4", "notes.txt"]
    assert f"clips/{CID}/heat_old.mp4" in str(w[0].message) and "notes.txt" in str(w[0].message)
    assert "heat_old" not in (assets.assets_dir() / "MEDIA.md").read_text()


def test_a_referenced_file_that_is_missing_fails_the_manifest(runs, tank):
    make_dive(runs, tank)
    blk = assets.clip_assets(CID, tank)
    assets.build_clips_json({CID: blk}, {})
    (assets.assets_dir() / "clips" / CID / "poster.jpg").unlink()
    with pytest.raises(FileNotFoundError, match="poster.jpg"):
        assets.media_manifest()


def test_a_bare_clip_that_no_longer_matches_its_source_hash_fails_the_manifest(runs, tank):
    make_dive(runs, tank)
    blk = assets.clip_assets(CID, tank)
    assets.build_clips_json({CID: blk}, {})
    with open(assets.assets_dir() / "clips" / CID / "gen.mp4", "ab") as fh:
        fh.write(b"\0")                                                        # a re-encode, a trim, anything
    with pytest.raises(RuntimeError, match="source_sha256"):
        assets.media_manifest()


def test_nothing_in_assets_uploads_anything():
    src = (PIPELINE / "assets.py").read_text()
    for word in ("boto3", "requests", "urllib", "upload(", "put_object", "subprocess"):
        assert word not in src.replace("never uploads", "")


def test_assets_command_hands_its_arguments_to_assets_main(monkeypatch):
    import assets
    seen = []
    monkeypatch.setattr(assets, "main", lambda ids, rec_only: seen.append((ids, rec_only)))
    cli.main(["assets"])
    cli.main(["assets", "air__gen45__D__5s", "--recordings-only"])
    assert seen == [(None, False), (["air__gen45__D__5s"], True)]


def test_past_the_cap_the_path_points_are_null_and_travel_and_wall_come_from_trusted_frames_only(runs, tank):
    entry = make_dive(runs, tank, trusted=100.0, wall=20)              # a "wall frame" past the cap, as an untrusted path would give
    cap = entry["first_capped_frame"]
    assert cap < 20 and entry["travel"] > 150
    blk = assets.clip_assets(CID, tank)
    a = assets.assets_dir() / "clips" / CID
    p = json.loads((a / "path.json").read_text())
    assert p["x"][cap - 1] is not None and p["z"][cap - 1] is not None and p["trusted_frames"] == cap
    assert all(v is None for v in p["x"][cap:] + p["z"][cap:] + p["yaw_deg"][cap:]) and p["wall_frame"] is None
    assert blk["path"][cap - 1][2] is not None and blk["path"][cap] == [None, None, None] and len(blk["path"]) == N
    assert blk["yaw_deg"][cap] is None and blk["trusted_frames"] == cap and blk["wall_frame"] is None
    assert 90 < blk["travel"] < 130 and blk["travel"] < entry["travel"] - 40          # to the trusted frame, not to the end
    assert blk["untrusted"] == {"travel": entry["travel"], "wall_frame": 20}
    doc = assets.build_clips_json({CID: blk}, {})
    c = doc["clips"][0]
    assert c["path"][cap] == [None, None, None] and c["travel"] == blk["travel"] and c["wall_frame"] is None
    assert c["untrusted"]["wall_frame"] == 20 and "NaN" not in (assets.assets_dir() / "clips.json").read_text()


def test_a_clip_with_nothing_unverifiable_keeps_its_own_numbers(runs, tank):
    entry = make_dive(runs, tank)
    blk = assets.clip_assets(CID, tank)
    assert blk["untrusted"] == {} and blk["travel"] == entry["travel"] and blk["wall_frame"] == entry["wall_frame"]
    assert blk["path"] == entry["path"] and blk["trusted_frames"] == N


# ---- batch 3 review fixes ----------------------------------------------------------------------------------------

OTHER = "air__gen45__N__5s"


@pytest.fixture
def build_env(runs, tank, monkeypatch):
    """assets.main() with the real recordings stubbed out: one recording, 'air', whose assets are a stub block."""
    monkeypatch.setattr(dive, "load_tank", lambda rec, r: tank)
    monkeypatch.setattr(recordings, "recordings", lambda: {"air": object()})
    monkeypatch.setattr(assets, "recording_assets", lambda rec, t: {"stub": True})
    return runs


def clips_in_doc():
    return {c["clip"]: c for c in json.loads((assets.assets_dir() / "clips.json").read_text())["clips"]}


def test_a_partial_rebuild_keeps_every_key_of_the_other_clips_blocks(build_env, tank):
    entry = make_dive(build_env, tank, trusted=100.0, wall=20)            # pellets-style: capped
    make_dive(build_env, tank, cid=OTHER)
    assets.main()
    full = clips_in_doc()
    assert full[CID]["travel"] < entry["travel"] and full[CID]["wall_frame"] is None and full[CID]["untrusted"]["wall_frame"] == 20
    assets.main([OTHER])                                                    # rebuild one other clip only
    part = clips_in_doc()
    assert part[CID] == full[CID]                                           # the capped clip's block is unchanged, every key
    assert part[CID]["travel"] != entry["travel"] and part[CID]["path"][-1] == [None, None, None]
    assert all(k in part[CID] for k in assets.BLOCK_KEYS)


def _strip_key_from_clip(clip_id, key):
    p = assets.assets_dir() / "clips.json"
    doc = json.loads(p.read_text())
    for c in doc["clips"]:
        if c["clip"] == clip_id:
            c.pop(key)
    p.write_text(json.dumps(doc))
    return p.read_bytes()


@pytest.mark.parametrize("key", ["provenance", "seed", "moving_track", "untrusted"])
def test_a_partial_rebuild_refuses_an_old_block_missing_a_key_and_says_to_run_a_full_rebuild(build_env, tank, key):
    """An old block without a BLOCK_KEYS key would let untrusted arrays through for a capped clip (call 69 review)."""
    make_dive(build_env, tank)
    make_dive(build_env, tank, cid=OTHER)
    assets.main()
    before = _strip_key_from_clip(CID, key)
    with pytest.raises(SystemExit, match=rf"(?s)full rebuild.*{key}|{key}.*full rebuild") as e:
        assets.main([OTHER])
    assert CID in str(e.value)
    assert (assets.assets_dir() / "clips.json").read_bytes() == before            # nothing was rewritten
    with pytest.raises(SystemExit, match="full rebuild"):
        assets.main(recordings_only=True)
    assets.main()                                                                  # a full rebuild repairs it
    assert all(k in clips_in_doc()[CID] for k in assets.BLOCK_KEYS)
    assets.main([OTHER])                                                           # and a partial one is allowed again


def test_a_partial_rebuild_only_checks_the_blocks_it_keeps(build_env, tank):
    make_dive(build_env, tank)
    make_dive(build_env, tank, cid=OTHER)
    assets.main()
    _strip_key_from_clip(OTHER, "seed")
    assets.main([OTHER])                                                           # OTHER is rebuilt, so its old block is not kept
    assert "seed" in clips_in_doc()[OTHER]


def test_recordings_only_never_empties_the_clips(build_env, tank):
    make_dive(build_env, tank)
    make_dive(build_env, tank, cid=OTHER)
    assets.main()
    before = clips_in_doc()
    assets.main(recordings_only=True)
    assert clips_in_doc() == before and len(before) == 2
    assets.main([], True)                                                   # what `cli.py assets --recordings-only` passes
    assert clips_in_doc() == before


def test_an_unknown_clip_id_is_refused_before_anything_is_built(build_env, tank):
    make_dive(build_env, tank)
    with pytest.raises(SystemExit, match="air__gen45__B__5s"):
        assets.main([CID, "air__gen45__B__5s"])
    assert not assets.assets_dir().exists() or not (assets.assets_dir() / "clips.json").exists()


def test_every_clip_block_carries_its_provenance_prompt_and_seed(runs, tank):
    entry = make_dive(runs, tank)
    blk = assets.clip_assets(CID, tank)
    src = hashlib.sha256(clips.video_path(clips.parse_clip_id(CID)).read_bytes()).hexdigest()
    prov = blk["provenance"]
    assert prov["gen"] == "engine original, byte copy" and prov["source_sha256"] == src
    assert {prov[k] for k in ("heat", "real", "poster", "poster_heat", "relief")} == {"derived"}
    assert blk["prompt_text"] == PROMPTS["D"] and blk["seed"] == clips.seed_for(clips.parse_clip_id(CID))
    assert hashlib.sha256((assets.assets_dir() / blk["assets"]["gen"]).read_bytes()).hexdigest() == src
    doc = assets.build_clips_json({CID: blk}, {})
    assert doc["clips"][0]["prompt_text"] == PROMPTS["D"] and entry["clip"] == CID


def test_no_prompt_text_is_retyped_in_assets():
    src = (PIPELINE / "assets.py").read_text()
    assert all(t not in src for t in PROMPTS.values())


def test_the_logged_seed_is_the_one_actually_sent(runs):
    spec = clips.parse_clip_id(CID)
    assert assets.logged_seed(spec) == clips.seed_for(spec)
    clips.log_retake(spec, 1, "a still", clips.seed_for(spec, 1), None)
    clips.log_retake(spec, 2, "again", clips.seed_for(spec, 2), None)
    assert assets.logged_seed(spec) == clips.seed_for(spec, 2) != clips.seed_for(spec)
    wan = clips.parse_clip_id("air__wan22__B__5s")
    (runs / "wan22").mkdir()
    (runs / "wan22" / "seeds.jsonl").write_text(json.dumps({"clip": wan.id, "seed": 111, "retake": 0}) + "\n"
                                                + json.dumps({"clip": "other", "seed": 5}) + "\n"
                                                + json.dumps({"clip": wan.id, "seed": 222, "retake": 1}) + "\n")
    assert assets.logged_seed(wan) == 222                                    # the seed Wan logged for its latest take
    assert assets.logged_seed(clips.parse_clip_id("air__wan22__N__5s")) == clips.seed_for(clips.parse_clip_id("air__wan22__N__5s"))


def test_the_relief_metadata_names_the_mapping_box_and_the_real_frame_size_and_the_real_cell_is_written(runs, tank):
    make_dive(runs, tank)
    blk = assets.clip_assets(CID, tank)
    assert blk["relief"]["box"] == list(FILL) and blk["relief"]["real_size"] == [tank.k_real.width, tank.k_real.height]
    cell = cv2.imread(str(assets.assets_dir() / blk["assets"]["tank_relief"]), cv2.IMREAD_UNCHANGED)
    d, _ = tank.on_grid(FILL, *WORK)
    assert cell.shape == (90, 160) and cell.dtype == np.uint16 and np.array_equal(cell, assets.depth_cell(d, tank.fxb))
    assert abs(int(np.median(cell[40:50, 70:90])) - 1300 * 16) < 0.03 * 1300 * 16


def test_the_real_pane_draws_unseen_pixels_with_the_same_grey_as_past_the_cap():
    from render import GREY, Render
    color = np.full((4, 4, 3), GREY, np.uint8)
    color[0, 0] = (10, 20, 30)
    seen = np.zeros((4, 4), bool)
    seen[0, 0] = True
    out = assets.real_color(Render(np.zeros((4, 4)), color, seen))
    assert tuple(out[0, 0]) == (10, 20, 30)
    assert (out[seen == False] == np.array(heat.GREY_RGB[::-1], np.uint8)).all()      # noqa: E712
    assert heat.GREY_RGB[0] != GREY                                                    # the renderer's own grey is not used


def test_the_per_frame_tracks_and_icp_arrays_and_the_path_disagreement_are_null_past_the_cap(runs, tank):
    entry = make_dive(runs, tank, trusted=100.0)
    cap = entry["first_capped_frame"]
    assert entry["path_disagreement"] is not None and entry["path_disagreement_frame"] >= cap     # computed past the cap
    blk = assets.clip_assets(CID, tank)
    for key, arrs in (("tracks", ("n_inliers", "reproj_px")), ("icp", ("fitness", "icp_rmse", "scale"))):
        for a in arrs:
            v = blk[key][a]
            assert len(v) == N and all(x is None for x in v[cap:]) and v[:cap] == entry[key][a][:cap]
        assert blk[key]["lost_from"] == entry[key]["lost_from"]
    assert blk["path_disagreement"] is None and blk["path_disagreement_frame"] is None
    doc = assets.build_clips_json({CID: blk}, {})
    assert doc["clips"][0]["tracks"]["n_inliers"][cap] is None and doc["clips"][0]["path_disagreement"] is None
    json.dumps(doc, allow_nan=False)


def test_a_clip_with_nothing_unverifiable_keeps_its_diagnostics(runs, tank):
    entry = make_dive(runs, tank)
    blk = assets.clip_assets(CID, tank)
    assert blk["tracks"] == entry["tracks"] and blk["icp"] == entry["icp"]
    assert blk["path_disagreement"] == entry["path_disagreement"] and blk["path_disagreement_frame"] == entry["path_disagreement_frame"]


def test_the_encoders_are_streamed_so_memory_does_not_grow_with_the_frames(runs, tank, monkeypatch):
    make_dive(runs, tank)
    seen_mb = []
    real = assets.frame_products

    def spy(*a, **k):
        seen_mb.append(tracemalloc.get_traced_memory()[0])
        return real(*a, **k)
    monkeypatch.setattr(assets, "frame_products", spy)
    tracemalloc.start()
    try:
        assets.clip_assets(CID, tank)
    finally:
        tracemalloc.stop()
    frame_bytes = WORK[0] * WORK[1] * 3
    assert len(seen_mb) == N
    # a list of every heat frame and every real frame would add 2 frames per step: about 40 MB over these 24 steps
    assert seen_mb[-1] - seen_mb[2] < 8 * frame_bytes, (seen_mb[2], seen_mb[-1])


# ---- task C0: the page's floor-map words, the cell intrinsics and a short GOP ---------------------------------------------

def keyframes(path) -> list[int]:
    """Frame indices of the keyframes of an mp4, in presentation order."""
    import av
    with av.open(str(path)) as c:
        s = c.streams.video[0]
        return [i for i, p in enumerate(p for p in c.demux(s) if p.size) if p.is_keyframe]


def test_the_relief_block_carries_the_cells_intrinsics_through_the_mapping_box(runs, tank):
    make_dive(runs, tank)
    blk = assets.clip_assets(CID, tank)
    k = tank.k_grid(FILL, assets.CELL_W, assets.CELL_H)
    got = {key: blk["relief"][key] for key in ("fx", "fy", "cx", "cy")}
    assert got == pytest.approx({"fx": k.fx, "fy": k.fy, "cx": k.cx, "cy": k.cy})
    assert got["fx"] == pytest.approx(tank.k_real.fx * assets.CELL_W / FILL[2])
    # a box that is not the whole frame (cover or contain) moves the principal point and the vertical scale
    cover = (0.0, 20.0, FILL[2], FILL[3] - 20.0)            # 20 px off the top of the synthetic frame: a box that is not the whole frame
    c2 = assets.relief_intrinsics(tank, cover)
    assert c2["fy"] > got["fy"] and c2["cy"] != pytest.approx(got["cy"], abs=0.01)
    assert set(c2) == {"fx", "fy", "cx", "cy"} and all(isinstance(v, float) for v in c2.values())


def test_a_partial_rebuild_refuses_an_older_clips_json_whose_relief_blocks_lack_the_intrinsics(runs, tank, monkeypatch):
    make_dive(runs, tank)
    blk = assets.clip_assets(CID, tank)
    old = {k: v for k, v in blk["relief"].items() if k not in ("fx", "fy", "cx", "cy")}
    assert assets.stale_keys({**blk, "relief": old}) == ["relief.fx", "relief.fy", "relief.cx", "relief.cy"]
    assert assets.stale_keys(blk) == []


def test_the_derived_videos_have_a_keyframe_at_least_every_12_frames_and_the_bare_clip_is_still_the_engines_own_bytes(runs, tank):
    make_dive(runs, tank)
    blk = assets.clip_assets(CID, tank)
    a = assets.assets_dir() / "clips" / CID
    assert assets.GOP == 12
    for name in ("heat.mp4", "real.mp4"):
        kf = keyframes(a / name)
        assert kf[0] == 0, name
        gaps = [b - x for x, b in zip(kf, kf[1:] + [N])]
        assert max(gaps) <= assets.GOP, (name, kf)
    assert len(keyframes(a / "heat.mp4")) >= 3                                   # 25 frames: 0, 12, 24 at the least
    src = clips.video_path(clips.parse_clip_id(CID))
    assert hashlib.sha256((a / "gen.mp4").read_bytes()).hexdigest() == hashlib.sha256(src.read_bytes()).hexdigest()
    assert blk["provenance"]["gen"] == "engine original, byte copy" and blk["provenance"]["source_sha256"] == hashlib.sha256(src.read_bytes()).hexdigest()


def test_the_video_writer_forces_a_keyframe_every_12_frames_on_a_long_still_clip(tmp_path):
    """Content that never changes would otherwise get one keyframe in 250: the GOP is a ceiling, not a hope."""
    still = np.full((64, 96, 3), 90, np.uint8)
    out = tmp_path / "still.mp4"
    assets.encode_video(out, (still for _ in range(60)))
    gaps = [b - x for x, b in zip(keyframes(out), keyframes(out)[1:] + [60])]
    assert max(gaps) <= 12
