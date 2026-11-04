"""One clip down the real tank: the frame-0 fit, the dream's path (two estimators), the tank re-seen from
that path, residuals on verified pixels and the clip's numbers. Also the self-test (kill rule 4)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage

from align import AffineFit, huber_affine_fit, rel_residual
from mapping import Box, box_intrinsics, resample
from metrics import (abs_rel, at_seconds, first_sustained, first_wall_frame, lost_from, verified_share)
from camera import Pose, straight_path
from pose import Target, register, track_path
from recon import Mesh, build_mesh, far_end_depth, points_from_depth
from render import render
from units import Intrinsics

WORK = (1280, 720)
ICP_STRIDE = 8         # source pixels for depth registration: every 8th in each direction
TARGET_STRIDE = 2      # tank vertices for depth registration: every 2nd in each direction
PATH_CHOICE = Path(__file__).resolve().parent / "path_choice.json"  # written by task 1.7
SELFTEST_TRAVEL_SU = 200.0  # the self-test path's forward travel, in su (uncorrected stereo units)
# call 50: how far forward (su, from frame 0) each condition's tank map is trusted in a dive. Pellets' map is one
# stereo frame: it holds to +100 su and tears into flaps by +200 su. No entry: no cap. The self-test is never capped.
TRUSTED_TRAVEL_SU = {"saltwater-pellets": 100.0}


@dataclass
class Tank:
    name: str
    k_real: Intrinsics       # the exported frames' intrinsics (P1)
    fxb: float               # fx * baseline: disparity (full-res px) <-> depth (su)
    disp_half: np.ndarray    # static-tank disparity on the half grid, in half-resolution pixels; NaN invalid
    work: tuple[int, int]
    mesh: Mesh
    target: Target
    far_end: float           # su
    floor: float | None

    def on_grid(self, box: Box, w: int, h: int) -> tuple[np.ndarray, np.ndarray]:
        """Tank disparity in full-resolution pixels on an engine grid given by a real-frame box."""
        hb = tuple(v / 2 for v in box)  # half-grid edges are full-grid edges halved
        ok = np.isfinite(self.disp_half)
        return resample(np.where(ok, self.disp_half * 2.0, 0.0), ok, hb, w, h)

    def k_grid(self, box: Box, w: int, h: int) -> Intrinsics:
        return box_intrinsics(self.k_real, box, w, h)


def make_tank(name: str, k_real: Intrinsics, fxb: float, disp_half: np.ndarray, colors_work: np.ndarray | None,
              floor: float | None, work: tuple[int, int] = WORK) -> Tank:
    fill: Box = (0.0, 0.0, float(k_real.width), float(k_real.height))
    t = Tank(name, k_real, fxb, disp_half, work, None, None, float("nan"), floor)  # type: ignore[arg-type]
    d, ok = t.on_grid(fill, *work)
    z = np.where(ok, fxb / np.where(ok, d, 1.0), np.nan)
    k = t.k_grid(fill, *work)
    t.mesh = build_mesh(z, k, colors_work)
    gh, gw = t.mesh.grid
    sel = np.zeros((gh, gw), bool)
    sel[::TARGET_STRIDE, ::TARGET_STRIDE] = True
    sel = sel.ravel() & t.mesh.valid
    t.target = Target(t.mesh.verts[sel], t.mesh.normals[sel])
    t.far_end = far_end_depth(z)
    return t


def load_tank(rec, runs: Path, work: tuple[int, int] = WORK) -> Tank:
    import cv2

    from units import real_intrinsics
    z = np.load(runs / "tank" / f"{rec.name}.npz")
    assert z["tank_disp_half"].shape == (621, 1104), "on_grid assumes the 1104-wide half grid (iscale 2)"
    floor_path = runs / "floor" / f"{rec.name}.json"
    floor = json.loads(floor_path.read_text())["floor"] if floor_path.exists() else None
    start = cv2.resize(cv2.imread(str(rec.left_path(rec.start_frame))), work, interpolation=cv2.INTER_AREA)
    cal = rec.calibration
    return make_tank(rec.name, real_intrinsics(cal), cal.fx * cal.baseline_mm, z["tank_disp_half"], start, floor, work)


def frame_products(tank: Tank, k: Intrinsics, g: np.ndarray, moving: np.ndarray, fit: AffineFit, pose: Pose) -> dict:
    """Everything the page shows for one frame: the tank re-seen from `pose`, the residual of the frozen
    fit on verified pixels, and the floating fit. Deterministic, so assets can re-run it frame by frame."""
    rd = render(tank.mesh, k, pose)
    d_ren = rd.inv_depth * tank.fxb
    S = rd.seen & ~moving & np.isfinite(g)
    r = rel_residual(fit.apply(g), d_ren)
    r[~S] = np.nan
    try:
        ff = huber_affine_fit(g, d_ren, S)
        r_float = rel_residual(ff.apply(g), d_ren)
        r_float[~S] = np.nan
    except ValueError:
        ff, r_float = None, np.full_like(r, np.nan)
    return {"render": rd, "verified": S, "residual": r, "residual_float": r_float, "fit_float": ff}


def _icp_path(tank: Tank, k: Intrinsics, g: np.ndarray, moving: np.ndarray, fit: AffineFit):
    res = [None]
    poses, fitness, n_corr, rmse = [Pose.identity()], [1.0], [10**9], [0.0]
    for i in range(1, len(g)):
        d = fit.apply(g[i])
        ok = np.isfinite(d) & (d > 0) & ~moving[i]
        z = np.where(ok, tank.fxb / np.where(ok, d, 1.0), np.nan)
        P = points_from_depth(z, k)[::ICP_STRIDE, ::ICP_STRIDE][ok[::ICP_STRIDE, ::ICP_STRIDE]]
        r = register(P, tank.target, poses[-1])
        res.append(r)
        poses.append(r.pose)
        fitness.append(r.fitness)
        n_corr.append(r.n_corr)
        rmse.append(r.rmse)
    lost = lost_from(np.array(fitness), np.array(n_corr))
    return poses, np.array(fitness), np.array(rmse), lost


def run_clip(tank: Tank, frames: list[np.ndarray], inv: np.ndarray, moving: np.ndarray | None, box: Box,
             primary: str, fps: float = 24.0, clip_id: str = "", meta: dict | None = None,
             trusted_travel: float | None = None) -> tuple[dict, dict]:
    """frames: the clip's BGR frames; inv: (N, H, W) depth-model inverse depth on the same grid;
    moving: (N, H, W) bool, pixels of anything tracked as moving (None: nothing moves).
    trusted_travel (su, call 50): from the first frame whose recovered camera centre has moved more than this
    along the frame-0 viewing axis, every pixel is unverifiable (V = 0, no AbsRel, no D). None: no cap.
    The entry is strict JSON: every non-finite number in it is null."""
    n, h, w = inv.shape
    assert len(frames) == n, f"{len(frames)} frames but {n} depth maps"
    assert moving is None or moving.shape == inv.shape, f"moving {moving.shape} is not on the depth grid {inv.shape}"
    if tank.floor is None or not np.isfinite(tank.floor) or tank.floor <= 0:
        raise ValueError(f"tank {tank.name}: no noise floor ({tank.floor}); run task 1.5 (cli.py floor) first")
    g = inv.astype(np.float64)
    moving = np.zeros((n, h, w), bool) if moving is None else moving
    k = tank.k_grid(box, w, h)
    d_tank, ok_tank = tank.on_grid(box, w, h)
    fit = huber_affine_fit(g[0], d_tank, ok_tank & ~moving[0])

    tr = track_path(frames, k, np.where(ok_tank, d_tank / tank.fxb, np.nan),
                    render_inv=lambda p: render(tank.mesh, k, p).inv_depth, valid0=ok_tank & ~moving[0],
                    moving=moving)
    tr_lost = next((i for i, o in enumerate(tr) if o["lost"]), None)
    icp_poses, icp_fit, icp_rmse, icp_lost = _icp_path(tank, k, g, moving, fit)
    paths = {"tracks": [o["pose"] for o in tr], "icp": icp_poses}
    lost = {"tracks": tr_lost, "icp": icp_lost}
    P, L = paths[primary], lost[primary]
    C = np.array([p.C for p in P])
    capped = None
    if trusted_travel is not None:
        fwd = (C - C[0]) @ P[0].R[:, 2]           # forward travel along the frame-0 viewing axis, su
        over = np.flatnonzero(fwd[:n if L is None else L] > trusted_travel)
        capped = int(over[0]) if over.size else None

    ar, arf, V = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    for i in range(n if L is None else L):
        if capped is not None and i >= capped:
            V[i] = 0.0                            # past the trusted travel: nothing verifiable, no heat
            continue
        fp = frame_products(tank, k, g[i], moving[i], fit, P[i])
        ar[i] = abs_rel(fp["residual"], fp["verified"])
        arf[i] = abs_rel(fp["residual_float"], fp["verified"])
        V[i] = verified_share(fp["verified"])     # seen and not tracked as moving (call 63): D's own pixels
    D, Df = ar / tank.floor, arf / tank.floor
    far_ok = bool(np.isfinite(tank.far_end))
    lost_mask = np.zeros(n, bool) if L is None else np.arange(n) >= L
    both = min(x for x in (tr_lost, icp_lost, n) if x is not None) - 1
    entry = {
        "clip": clip_id, **(meta or {}), "recording": tank.name, "n_frames": n, "fps": fps, "grid": [w, h],
        "box": list(box), "fit": fit.to_dict(), "floor": tank.floor, "primary_path": primary,
        "path": C.round(2).tolist(), "yaw_deg": [round(p.yaw_deg(), 3) for p in P], "lost_from": L,
        "verified": V.round(4).tolist(), "abs_rel": ar.round(4).tolist(), "D": D.round(3).tolist(),
        "D_float": Df.round(3).tolist(), "D_at": at_seconds(D, fps), "V_at": at_seconds(V, fps),
        "first_D3": first_sustained(D), "far_end": round(tank.far_end, 1) if far_ok else None,
        "far_end_valid": far_ok,
        "wall_frame": first_wall_frame(C[:, 2], tank.far_end, lost_mask) if far_ok else None,
        "travel": float(np.linalg.norm(C[(n if L is None else L) - 1] - C[0])),
        "tracks": {"lost_from": tr_lost, "n_inliers": [o["n_inliers"] for o in tr],
                   "reproj_px": [None if not np.isfinite(o["reproj_px"]) else round(o["reproj_px"], 3) for o in tr]},
        "icp": {"lost_from": icp_lost, "fitness": icp_fit.round(4).tolist(),
                "icp_rmse": [None if not np.isfinite(x) else round(float(x), 5) for x in icp_rmse],
                "scale": [round(p.c, 5) for p in icp_poses]},
        # centre distance (su) between the two paths at the last frame both still hold; None if that is frame 0
        "path_disagreement": float(np.linalg.norm(paths["tracks"][both].C - paths["icp"][both].C)) if both > 0 else None,
        "path_disagreement_frame": both,
        "trusted_travel_su": trusted_travel, "first_capped_frame": capped,
    }
    entry = _strict(entry)
    arrays = {"R": np.array([p.R for p in P]), "C": C, "R_icp": np.array([p.R for p in icp_poses]),
              "C_icp": np.array([p.C for p in icp_poses]), "c_icp": np.array([p.c for p in icp_poses]),
              "R_tracks": np.array([p.R for p in paths["tracks"]]), "C_tracks": np.array([p.C for p in paths["tracks"]])}
    return entry, arrays


def _strict(x):
    """JSON-safe copy: NaN and infinities become None (strict JSON has no NaN), numpy scalars plain."""
    if isinstance(x, dict):
        return {k: _strict(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_strict(v) for v in x]
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return float(x) if np.isfinite(x) else None
    return x


# ---- the self-test (kill rule 4) -------------------------------------------------------------------

def fill_nearest(img: np.ndarray, seen: np.ndarray) -> np.ndarray:
    """Unseen pixels take the value of the nearest seen pixel (said so on the page)."""
    if not seen.any():
        raise ValueError("nothing seen: no pixel to fill from")
    if seen.all():
        return img.copy()
    idx = ndimage.distance_transform_edt(~seen, return_distances=False, return_indices=True)
    return img[idx[0], idx[1]]


def selftest_renders(tank: Tank, n: int = 49, travel: float = SELFTEST_TRAVEL_SU, yaw_deg: float = 3.0):
    """The reconstruction rendered along the known path on the work grid: hole-filled frames,
    hole-filled true inverse depth (1/su) and the true poses."""
    fill: Box = (0.0, 0.0, float(tank.k_real.width), float(tank.k_real.height))
    k = tank.k_grid(fill, *tank.work)
    truth = straight_path(n, travel, yaw_deg)
    frames, inv = [], []
    for p in truth:
        rd = render(tank.mesh, k, p)
        frames.append(fill_nearest(rd.color, rd.seen))
        inv.append(fill_nearest(np.nan_to_num(rd.inv_depth), rd.seen))
    return frames, np.array(inv), truth


def score_path(est: list[Pose], truth: list[Pose], travel: float, lost: int | None) -> dict:
    n = len(truth) if lost is None else lost
    err = [float(np.linalg.norm(e.C - t.C)) for e, t in zip(est[:n], truth[:n])]
    return {"endpoint_err_frac": err[-1] / travel if lost is None else float("inf"),
            "max_drift_frac": max(err) / travel, "lost_from": lost,
            "yaw_err_deg_end": abs(est[n - 1].yaw_deg() - truth[n - 1].yaw_deg()),
            "yaw_err_deg_max": max(abs(e.yaw_deg() - t.yaw_deg()) for e, t in zip(est[:n], truth[:n]))}


def choose_primary(scores: dict[str, dict[str, dict]], tie: float = 0.02) -> str:
    """Frozen rule (sub-plan A): the estimator with the lower median endpoint error over the recordings;
    within `tie` (2 % of travel) section 7's depth registration ('icp') keeps the job."""
    med = {e: float(np.median([s[e]["endpoint_err_frac"] for s in scores.values()])) for e in ("tracks", "icp")}
    return "tracks" if med["tracks"] < med["icp"] - tie else "icp"


def primary_path() -> str:
    if not PATH_CHOICE.exists():
        raise RuntimeError("path_choice.json missing: run task 1.7 (python cli.py selftest) first")
    return json.loads(PATH_CHOICE.read_text())["primary"]


def read_video(path) -> list[np.ndarray]:
    import av
    with av.open(str(path)) as c:
        return [f.to_ndarray(format="bgr24") for f in c.decode(video=0)]
