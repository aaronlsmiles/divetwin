"""The real tank as a surface: the static-tank depth back-projected through the frame's intrinsics into
a grid mesh, cut where neighbouring depths jump by more than 5 %, coloured from the start frame.
Points are in the real camera's frame (the world), in uncorrected stereo units."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from units import Intrinsics

JUMP = 0.05


@dataclass
class Mesh:
    verts: np.ndarray    # (V, 3) float64, world = real camera frame
    faces: np.ndarray    # (F, 3) int32
    colors: np.ndarray   # (V, 3) uint8, BGR
    normals: np.ndarray  # (V, 3) float64, NaN where undefined
    valid: np.ndarray    # (V,) bool
    grid: tuple[int, int]

    def save(self, path) -> None:
        np.savez_compressed(path, verts=self.verts.astype(np.float32), faces=self.faces, colors=self.colors,
                            normals=self.normals.astype(np.float32), valid=self.valid, grid=np.array(self.grid))

    @classmethod
    def load(cls, path) -> "Mesh":
        with np.load(path) as z:
            return cls(z["verts"].astype(np.float64), z["faces"], z["colors"], z["normals"].astype(np.float64),
                       z["valid"], tuple(int(v) for v in z["grid"]))


def points_from_depth(z: np.ndarray, k: Intrinsics) -> np.ndarray:
    """(h, w) camera z-depth -> (h, w, 3) camera-frame points (equal to Q-reprojection up to Q's sign)."""
    h, w = z.shape
    u, v = np.meshgrid(np.arange(w, dtype=np.float64), np.arange(h, dtype=np.float64))
    return np.stack([(u - k.cx) * z / k.fx, (v - k.cy) * z / k.fy, z.astype(np.float64)], axis=-1)


def _cut(z0: np.ndarray, z1: np.ndarray, jump: float) -> np.ndarray:
    """Neighbouring depths that jump by more than `jump` (relative), as build_mesh cuts them; NaN cuts."""
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.maximum(z0, z1) / np.minimum(z0, z1) - 1
    return ~(r <= jump)


def grid_normals(P: np.ndarray, jump: float = JUMP) -> np.ndarray:
    """Unit normals from central differences on the point grid, turned to face the camera. NaN where the
    stencil crosses a cut (a depth jump > `jump` between neighbours), so no normal straddles two surfaces."""
    du = np.full_like(P, np.nan)
    dv = np.full_like(P, np.nan)
    du[:, 1:-1] = P[:, 2:] - P[:, :-2]
    dv[1:-1, :] = P[2:, :] - P[:-2, :]
    z = P[..., 2]
    cu = _cut(z[:, :-1], z[:, 1:], jump)   # between columns j and j + 1
    cv = _cut(z[:-1, :], z[1:, :], jump)   # between rows i and i + 1
    du[:, 1:-1][cu[:, :-1] | cu[:, 1:]] = np.nan
    dv[1:-1, :][cv[:-1, :] | cv[1:, :]] = np.nan
    n = np.cross(du, dv)
    norm = np.linalg.norm(n, axis=-1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        n = n / norm
    flip = np.sum(n * P, axis=-1) > 0
    n[flip] *= -1
    return n


def build_mesh(z: np.ndarray, k: Intrinsics, colors: np.ndarray | None = None, jump: float = JUMP) -> Mesh:
    h, w = z.shape
    assert colors is None or colors.shape[:2] == z.shape, f"colours {colors.shape[:2]} are not on the depth grid {z.shape}"
    valid = np.isfinite(z) & (z > 0)
    P = points_from_depth(np.where(valid, z, np.nan), k)
    idx = np.arange(h * w).reshape(h, w)
    a, b, c, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, :-1], idx[1:, 1:]
    tris = np.concatenate([np.stack([a, c, b], -1).reshape(-1, 3), np.stack([b, c, d], -1).reshape(-1, 3)])
    zf = np.where(valid, z, np.nan).ravel()
    zt = zf[tris]
    keep = np.all(np.isfinite(zt), axis=1)
    zk = zt[keep]
    keep[keep] = zk.max(axis=1) / zk.min(axis=1) - 1 <= jump
    nrm = grid_normals(P, jump).reshape(-1, 3)
    cols = np.full((h * w, 3), 128, np.uint8) if colors is None else colors.reshape(-1, 3).astype(np.uint8)
    return Mesh(P.reshape(-1, 3), tris[keep].astype(np.int32), cols, nrm, valid.ravel(), (h, w))


def far_end_depth(z: np.ndarray, frac: float = 0.2, pct: float = 80.0, min_valid: float = 0.1) -> float:
    """The farthest measured surface along the optical axis: the 80th percentile of depth in the central
    20 % x 20 % window (a percentile, so an object standing in front of the far end does not decide it).
    NaN (not measured) unless at least `min_valid` of the window has a valid depth."""
    h, w = z.shape
    win = z[int(h * (0.5 - frac / 2)):int(h * (0.5 + frac / 2)), int(w * (0.5 - frac / 2)):int(w * (0.5 + frac / 2))]
    v = win[np.isfinite(win) & (win > 0)]
    if v.size == 0 or v.size < min_valid * win.size:
        return float("nan")
    return float(np.percentile(v, pct))
