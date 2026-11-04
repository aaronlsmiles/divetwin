"""Disparity, depth and intrinsics in uncorrected stereo units (su).

z = fx * B / d, with fx the focal length of the exported rectified frames (calibration.json P1,
1433.347 px), B the baseline from calibration.json (62.975) and d the disparity in full-resolution
pixels. Nothing here corrects for the flat port: every distance is in uncorrected stereo units.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

REAL_W, REAL_H = 2208, 1242


@dataclass(frozen=True)
class Intrinsics:
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int

    def K(self) -> np.ndarray:
        return np.array([[self.fx, 0.0, self.cx], [0.0, self.fy, self.cy], [0.0, 0.0, 1.0]])


def real_intrinsics(cal) -> Intrinsics:
    """The exported frames' intrinsics (P1). `cal` is recordings.Calibration."""
    return Intrinsics(cal.fx, cal.fx, cal.cx, cal.cy, cal.width, cal.height)


def disp_to_depth(d: np.ndarray, fx: float, baseline: float) -> np.ndarray:
    d = np.asarray(d, dtype=np.float64)
    z = np.full(d.shape, np.nan)
    ok = np.isfinite(d) & (d > 0)
    z[ok] = fx * baseline / d[ok]
    return z


def depth_to_disp(z: np.ndarray, fx: float, baseline: float) -> np.ndarray:
    return disp_to_depth(z, fx, baseline)  # the map is its own inverse


def half_to_full(disp_half: np.ndarray, iscale: float = 2.0, size: tuple[int, int] = (REAL_W, REAL_H)) -> np.ndarray:
    """Network disparity at 1/iscale resolution, in that resolution's pixels -> full-resolution pixels.
    Holes must be NaN, never 0 or negative: linear interpolation blends a hole's value into its neighbours,
    which turns a 0 or a negative into plausible-looking wrong disparities (NaN stays NaN)."""
    up = cv2.resize(disp_half.astype(np.float32), size, interpolation=cv2.INTER_LINEAR)
    return up * np.float32(iscale)


def load_disp(path) -> np.ndarray:
    """runs/disp/<recording>/<frame>.npz -> full-resolution disparity in full-resolution pixels."""
    with np.load(path) as z:
        return half_to_full(z["disp_half"], float(z["iscale"]))


def bottle_depth(disp_full: np.ndarray, mask_full: np.ndarray, fx: float, baseline: float, erode_px: int = 5) -> float:
    """Median stereo depth (su) inside an eroded bottle mask; NaN if the mask is too small."""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * erode_px + 1, 2 * erode_px + 1))
    m = cv2.erode(mask_full.astype(np.uint8), k) > 0
    vals = disp_full[m & np.isfinite(disp_full) & (disp_full > 0)]
    if vals.size < 50:
        return float("nan")
    return float(fx * baseline / np.median(vals))


def ratio_summary(z_stereo: dict[int, float], center: dict[int, float]) -> dict:
    """Private units cross-check: stereo depth over the published Center_Distance, per matched frame."""
    r = np.array([z_stereo[k] / center[k] for k in z_stereo if k in center and np.isfinite(z_stereo[k]) and center[k] > 0])
    if r.size == 0:
        return {"n": 0}
    return {"n": int(r.size), "median": float(np.median(r)), "p25": float(np.percentile(r, 25)), "p75": float(np.percentile(r, 75))}


def epipolar_dy(left_gray: np.ndarray, right_gray: np.ndarray, n_features: int = 6000) -> dict:
    """SIFT matches on a rectified pair: vertical residual (left y - right y) and disparity sign."""
    sift = cv2.SIFT_create(n_features)
    kl, dl = sift.detectAndCompute(left_gray, None)
    kr, dr = sift.detectAndCompute(right_gray, None)
    if dl is None or dr is None or len(kl) < 10 or len(kr) < 10:
        return {"n": 0}
    pairs = cv2.BFMatcher().knnMatch(dl, dr, k=2)
    good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < 0.7 * p[1].distance]
    if len(good) < 5:
        return {"n": len(good)}
    pl = np.array([kl[m.queryIdx].pt for m in good])
    pr = np.array([kr[m.trainIdx].pt for m in good])
    dy, dx = pl[:, 1] - pr[:, 1], pl[:, 0] - pr[:, 0]
    keep = np.abs(dy) < 6
    if np.count_nonzero(keep) < 5:
        return {"n": int(np.count_nonzero(keep))}
    return {
        "n": int(keep.sum()),
        "median_dy": float(np.median(dy[keep])),
        "p25_dy": float(np.percentile(dy[keep], 25)),
        "p75_dy": float(np.percentile(dy[keep], 75)),
        "frac_dx_pos": float(np.mean(dx[keep] > 0)),
    }
