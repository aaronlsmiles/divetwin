import numpy as np
import pytest

import pose as pose_mod

from camera import Pose, straight_path
from pose import Target, register, track_path
from recon import build_mesh, points_from_depth
from render import render
from synth import K_SMALL, corridor_colors, corridor_depth
from units import Intrinsics


@pytest.fixture(scope="module")
def target():
    z = corridor_depth(K_SMALL, Pose.identity())
    mesh = build_mesh(z, K_SMALL)
    return Target(mesh.verts[mesh.valid], mesh.normals[mesh.valid])


def _source(pose, scale=1.0, noise=0.0, fish=False, seed=0, stride=4):
    z = corridor_depth(K_SMALL, pose)
    if noise:
        rng = np.random.default_rng(seed)
        z = z * (1 + noise * rng.standard_normal(z.shape))
    if fish:
        z[60:110, 120:200] = 250.0  # a near object the tank does not have, about 7 % of the frame
    P = points_from_depth(z, K_SMALL)[::stride, ::stride].reshape(-1, 3) * scale
    return P[np.all(np.isfinite(P), axis=1)]


def _track(target, path, **kw):
    est = [Pose.identity()]
    for k in range(1, len(path)):
        est.append(register(_source(path[k], seed=k, **kw), target, est[-1]).pose)
    return est


def test_identity_is_a_fixed_point(target):
    res = register(_source(Pose.identity()), target, Pose.identity())
    assert np.linalg.norm(res.pose.C) < 0.5 and abs(res.pose.c - 1) < 1e-3 and res.fitness > 0.95


def test_known_path_recovered_within_one_percent(target):
    path = straight_path()
    est = _track(target, path)
    err = np.linalg.norm(est[-1].C - path[-1].C)
    assert err < 0.01 * 200.0
    assert abs(est[-1].yaw_deg() - path[-1].yaw_deg()) < 0.2


def test_scale_drift_is_absorbed(target):
    path = straight_path()
    pose = path[30]
    res = register(_source(pose, scale=1.15), target, path[29])
    assert res.pose.c == pytest.approx(1 / 1.15, rel=5e-3)
    assert np.linalg.norm(res.pose.C - pose.C) < 2.0


def test_white_depth_noise_stays_inside_kill_rule(target):
    path = straight_path()
    est = _track(target, path, noise=0.03)
    assert np.linalg.norm(est[-1].C - path[-1].C) < 0.15 * 200.0


def test_planted_fish_does_not_move_the_pose(target):
    path = straight_path()
    pose = path[24]
    clean = register(_source(pose), target, path[23]).pose
    fishy = register(_source(pose, fish=True), target, path[23]).pose
    assert np.linalg.norm(fishy.C - clean.C) < 0.01 * 200.0
    assert abs(fishy.c - clean.c) < 2e-3


# ---- the image-track estimator --------------------------------------------------------------------
K_MID = Intrinsics(fx=415.0, fy=415.0, cx=319.5, cy=179.5, width=640, height=360)


@pytest.fixture(scope="module")
def textured():
    z = corridor_depth(K_MID, Pose.identity())
    mesh = build_mesh(z, K_MID, corridor_colors(K_MID, Pose.identity(), z))
    path = straight_path()
    frames = [render(mesh, K_MID, p).color for p in path]
    return z, mesh, path, frames


def test_tracks_recover_known_path(textured):
    z, mesh, path, frames = textured
    out = track_path(frames, K_MID, 1.0 / z, render_inv=lambda p: render(mesh, K_MID, p).inv_depth)
    assert not out[-1]["lost"]
    assert np.linalg.norm(out[-1]["pose"].C - path[-1].C) < 0.01 * 200.0
    # every frame, not only the end: the path's yaw returns to zero at the last frame, so an endpoint
    # check alone would pass a transposed rotation
    yaw_err = [abs(o["pose"].yaw_deg() - p.yaw_deg()) for o, p in zip(out, path)]
    drift = [np.linalg.norm(o["pose"].C - p.C) for o, p in zip(out, path)]
    assert max(yaw_err) < 0.2
    assert max(drift) < 0.01 * 200.0


def test_tracks_survive_image_noise(textured):
    z, mesh, path, frames = textured
    rng = np.random.default_rng(0)
    noisy = [np.clip(f + rng.normal(0, 4, f.shape), 0, 255).astype(np.uint8) for f in frames]
    out = track_path(noisy, K_MID, 1.0 / z, render_inv=lambda p: render(mesh, K_MID, p).inv_depth)
    assert np.linalg.norm(out[-1]["pose"].C - path[-1].C) < 0.02 * 200.0


def test_tracks_lost_stay_lost(textured):
    z, mesh, path, frames = textured
    blank = [f if i < 20 else np.full_like(f, 128) for i, f in enumerate(frames)]
    out = track_path(blank, K_MID, 1.0 / z, render_inv=lambda p: render(mesh, K_MID, p).inv_depth)
    first = next(i for i, o in enumerate(out) if o["lost"])
    assert first == 20 and all(o["lost"] for o in out[first:])
    assert all(np.allclose(o["pose"].C, out[first - 1]["pose"].C) for o in out[first:])  # held, never extrapolated


def _moving_square(frames, start=5, size=(90, 120), y0=130, x0=120, step=4, pad=4, seed=3):
    """A textured square sliding across the clip from `start`, and its (padded) moving mask."""
    rng = np.random.default_rng(seed)
    tex = (rng.random(size) > 0.5).astype(np.uint8) * 255
    h, w = frames[0].shape[:2]
    moving = np.zeros((len(frames), h, w), bool)
    out = []
    for i, f in enumerate(frames):
        f = f.copy()
        if i >= start:
            x = x0 + step * (i - start)
            f[y0:y0 + size[0], x:x + size[1]] = tex[..., None]
            moving[i, max(y0 - pad, 0):y0 + size[0] + pad, max(x - pad, 0):x + size[1] + pad] = True
        out.append(f)
    return out, moving


def test_reseeding_never_seeds_on_the_moving_mask(textured, monkeypatch):
    z, mesh, path, frames = textured
    frames, moving = _moving_square(frames)
    monkeypatch.setattr(pose_mod, "RESEED_BELOW", 390)  # so reseeding actually happens
    grays = [f[..., 0] for f in frames]  # grey checker and binary texture: B = G = R = grey
    seeds = []
    orig = pose_mod._seed

    def spy(gray, ok, existing, n=400):
        pts = orig(gray, ok, existing, n)
        i = next(j for j, g in enumerate(grays) if np.array_equal(g, gray))
        seeds.append((i, pts))
        return pts

    monkeypatch.setattr(pose_mod, "_seed", spy)
    out = track_path(frames, K_MID, 1.0 / z, render_inv=lambda p: render(mesh, K_MID, p).inv_depth, moving=moving)
    assert len(seeds) >= 3  # frame 0 plus reseeds
    for i, pts in seeds:
        u = np.rint(pts[:, 0]).astype(int)
        v = np.rint(pts[:, 1]).astype(int)
        assert not moving[i, v, u].any(), f"frame {i}: {int(moving[i, v, u].sum())} seeds on the moving mask"
    assert not out[-1]["lost"]
    assert np.linalg.norm(out[-1]["pose"].C - path[-1].C) < 0.01 * 200.0


def test_default_reseed_never_keeps_a_track_inside_moving(textured, monkeypatch):
    """With the default RESEED_BELOW, the tracks handed to PnP on each frame (the ones kept for that
    frame's pose) are all outside that frame's moving mask."""
    z, mesh, path, frames = textured
    frames, moving = _moving_square(frames)
    seen = []
    orig = pose_mod.cv2.solvePnPRansac

    def spy(X, pts, *a, **kw):
        seen.append(np.asarray(pts).reshape(-1, 2).copy())
        return orig(X, pts, *a, **kw)

    monkeypatch.setattr(pose_mod.cv2, "solvePnPRansac", spy)
    out = track_path(frames, K_MID, 1.0 / z, render_inv=lambda p: render(mesh, K_MID, p).inv_depth, moving=moving)
    assert not out[-1]["lost"] and len(seen) == len(frames) - 1
    for i, pts in enumerate(seen, start=1):
        assert not pose_mod._on_mask(pts, moving[i]).any(), f"frame {i}: a track sits inside the moving mask"


def test_on_mask_ignores_untracked_points_without_a_cast_warning():
    import warnings
    mask = np.zeros((10, 10), bool)
    mask[2:5, 2:5] = True
    pts = np.array([[3.0, 3.0], [np.nan, np.nan], [50.0, 50.0], [8.0, 8.0]], np.float32)
    st = np.array([1, 0, 1, 1], np.uint8)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        got = pose_mod._on_mask(pts, mask, tracked=st == 1)
    assert got.tolist() == [True, False, False, False]


def test_target_skips_nan_normals():
    pts = np.array([[0.0, 0, 100], [1.0, 0, 100], [2.0, 0, 100]])
    nrm = np.array([[0.0, 0, -1], [np.nan, np.nan, np.nan], [0.0, 0, -1]])
    t = Target(pts, nrm)
    assert len(t.pts) == 2 and np.all(np.isfinite(t.nrm))
