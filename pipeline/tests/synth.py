"""A synthetic tank: an axis-aligned box corridor seen from inside, with an optional cube in it.
Camera convention: OpenCV (x right, y down, z forward); world = the real camera at frame 0."""
from __future__ import annotations

import numpy as np

from camera import Pose
from units import Intrinsics

TANK = {"x": (-300.0, 300.0), "y": (-200.0, 250.0), "z_far": 1300.0}  # su
K_SMALL = Intrinsics(fx=330.0, fy=330.0, cx=159.5, cy=89.5, width=320, height=180)


def _rays(k: Intrinsics, pose: Pose):
    u, v = np.meshgrid(np.arange(k.width, dtype=np.float64), np.arange(k.height, dtype=np.float64))
    d_cam = np.stack([(u - k.cx) / k.fx, (v - k.cy) / k.fy, np.ones_like(u)], axis=-1)  # z = 1
    return d_cam @ pose.R.T  # world directions; the ray parameter is the camera z-depth


def corridor_depth(k: Intrinsics, pose: Pose, cube: tuple | None = None) -> np.ndarray:
    """Camera z-depth of the corridor (and an optional cube ((x0,x1),(y0,y1),(z0,z1))) from `pose`."""
    r = _rays(k, pose)
    C = pose.C
    t = np.full(r.shape[:2], np.inf)
    planes = [(0, TANK["x"][0]), (0, TANK["x"][1]), (1, TANK["y"][0]), (1, TANK["y"][1]), (2, TANK["z_far"])]
    with np.errstate(divide="ignore", invalid="ignore"):
        for axis, val in planes:
            ti = (val - C[axis]) / r[..., axis]
            t = np.where((ti > 1e-6) & (ti < t), ti, t)
        if cube is not None:
            tmin = np.full(t.shape, -np.inf)
            tmax = np.full(t.shape, np.inf)
            for axis in range(3):
                lo, hi = cube[axis]
                t1 = (lo - C[axis]) / r[..., axis]
                t2 = (hi - C[axis]) / r[..., axis]
                tmin = np.maximum(tmin, np.minimum(t1, t2))
                tmax = np.minimum(tmax, np.maximum(t1, t2))
            hit = (tmax >= tmin) & (tmin > 1e-6) & (tmin < t)
            t = np.where(hit, tmin, t)
    t[~np.isfinite(t)] = np.nan
    return t


def corridor_colors(k: Intrinsics, pose: Pose, z: np.ndarray) -> np.ndarray:
    """A checker texture in world coordinates, so a render can be compared to the truth."""
    P = pose.C + _rays(k, pose) * z[..., None]
    chk = (np.floor(P[..., 0] / 50) + np.floor(P[..., 1] / 50) + np.floor(P[..., 2] / 50)) % 2
    g = np.where(np.isfinite(chk), 60 + 140 * chk, 0).astype(np.uint8)
    return np.repeat(g[..., None], 3, axis=-1)
