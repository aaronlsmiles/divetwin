"""Z-buffer rasterisation of the tank mesh from any camera (numba, CPU).

Inverse depth is interpolated linearly in screen space (exact for planar triangles); colour is
perspective-correct. Pixels no triangle covers are unseen: NaN depth, grey colour."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numba import njit

from camera import Pose
from recon import Mesh
from units import Intrinsics

NEAR = 10.0   # su; vertices closer than this to the camera drop their triangles
GREY = 128


@dataclass
class Render:
    inv_depth: np.ndarray  # (H, W) float64, 1/su, NaN where unseen
    color: np.ndarray      # (H, W, 3) uint8, grey where unseen
    seen: np.ndarray       # (H, W) bool

    @property
    def depth(self) -> np.ndarray:
        with np.errstate(divide="ignore"):
            return 1.0 / self.inv_depth


@njit(cache=True)
def _raster(xy, w, faces, H, W):
    wbuf = np.zeros((H, W))
    fid = np.full((H, W), -1, np.int32)
    l0b = np.zeros((H, W), np.float32)
    l1b = np.zeros((H, W), np.float32)
    for f in range(faces.shape[0]):
        i0, i1, i2 = faces[f, 0], faces[f, 1], faces[f, 2]
        w0, w1, w2 = w[i0], w[i1], w[i2]
        if w0 <= 0.0 or w1 <= 0.0 or w2 <= 0.0:
            continue
        x0, y0 = xy[i0, 0], xy[i0, 1]
        x1, y1 = xy[i1, 0], xy[i1, 1]
        x2, y2 = xy[i2, 0], xy[i2, 1]
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-12:
            continue
        xmin = max(0, int(np.ceil(min(x0, x1, x2))))
        xmax = min(W - 1, int(np.floor(max(x0, x1, x2))))
        ymin = max(0, int(np.ceil(min(y0, y1, y2))))
        ymax = min(H - 1, int(np.floor(max(y0, y1, y2))))
        for py in range(ymin, ymax + 1):
            for px in range(xmin, xmax + 1):
                a0 = ((x1 - px) * (y2 - py) - (x2 - px) * (y1 - py)) / area
                a1 = ((x2 - px) * (y0 - py) - (x0 - px) * (y2 - py)) / area
                a2 = 1.0 - a0 - a1
                if a0 < -1e-9 or a1 < -1e-9 or a2 < -1e-9:
                    continue
                wv = a0 * w0 + a1 * w1 + a2 * w2
                if wv > wbuf[py, px]:
                    wbuf[py, px] = wv
                    fid[py, px] = f
                    l0b[py, px] = a0
                    l1b[py, px] = a1
    return wbuf, fid, l0b, l1b


def project(mesh: Mesh, k: Intrinsics, pose: Pose) -> tuple[np.ndarray, np.ndarray]:
    """Vertices -> pixel coordinates and inverse depth in the camera at `pose` (w <= 0: dropped)."""
    # pose.c (ICP's scale) is deliberately not applied: the headline residual uses the frozen (s, t) (call 25)
    Xc = (mesh.verts - pose.C) @ pose.R  # = R^T (X - C) for each row
    z = Xc[:, 2]
    ok = mesh.valid & np.isfinite(z) & (z > NEAR)
    w = np.where(ok, 1.0 / np.where(ok, z, 1.0), -1.0)
    xy = np.stack([k.fx * Xc[:, 0] * w + k.cx, k.fy * Xc[:, 1] * w + k.cy], axis=-1)
    xy[~ok] = 0.0
    return xy, w


def render(mesh: Mesh, k: Intrinsics, pose: Pose) -> Render:
    xy, w = project(mesh, k, pose)
    wbuf, fid, l0, l1 = _raster(xy, w, mesh.faces, k.height, k.width)
    seen = fid >= 0
    inv = np.where(seen, wbuf, np.nan)
    color = np.full((k.height, k.width, 3), GREY, np.uint8)
    if seen.any():
        f = mesh.faces[fid[seen]]
        lam = np.stack([l0[seen], l1[seen], 1.0 - l0[seen] - l1[seen]], axis=-1).astype(np.float64)
        lw = lam * w[f]
        c = np.einsum("nk,nkc->nc", lw, mesh.colors[f].astype(np.float64)) / lw.sum(axis=1, keepdims=True)
        color[seen] = np.clip(np.rint(c), 0, 255).astype(np.uint8)
    return Render(inv, color, seen)
