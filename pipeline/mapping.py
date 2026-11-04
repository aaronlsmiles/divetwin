"""Engine frame <-> real frame. A box (x0, y0, w, h) in real-pixel edge coordinates is the part of the
real frame that fills the engine frame; it is measured on frame 0, never assumed."""
from __future__ import annotations

import cv2
import numpy as np

from units import Intrinsics

Box = tuple[float, float, float, float]

ENGINE_SIZES = {"gen45": (1280, 720), "wan22": (1280, 704)}
FILL_1280x720: Box = (0.0, 0.0, 2208.0, 1242.0)  # the work grid: Gen-4.5's frame, a pure resize of 16:9


def box_affine(box: Box, out_w: int, out_h: int) -> np.ndarray:
    """2x3 affine taking real pixel centres to engine pixel centres."""
    x0, y0, w, h = box
    sx, sy = out_w / w, out_h / h
    return np.array([[sx, 0.0, (0.5 - x0) * sx - 0.5], [0.0, sy, (0.5 - y0) * sy - 0.5]])


def box_intrinsics(k: Intrinsics, box: Box, out_w: int, out_h: int) -> Intrinsics:
    a = box_affine(box, out_w, out_h)
    return Intrinsics(k.fx * a[0, 0], k.fy * a[1, 1], k.cx * a[0, 0] + a[0, 2], k.cy * a[1, 1] + a[1, 2], out_w, out_h)


def candidate_boxes(real_w: int, real_h: int, out_w: int, out_h: int) -> dict[str, Box]:
    """fill (stretch), cover (scale up, centre crop), contain (scale down, letterbox); duplicates dropped."""
    cands: dict[str, Box] = {"fill": (0.0, 0.0, float(real_w), float(real_h))}
    for name, s in (("cover", max(out_w / real_w, out_h / real_h)), ("contain", min(out_w / real_w, out_h / real_h))):
        w, h = out_w / s, out_h / s
        cands[name] = ((real_w - w) / 2, (real_h - h) / 2, w, h)
    out: dict[str, Box] = {}
    for name, b in cands.items():
        if not any(np.allclose(b, o, atol=1e-6) for o in out.values()):
            out[name] = b
    return out


def _prefilter(img: np.ndarray, box: Box, out_w: int, out_h: int) -> np.ndarray:
    sx, sy = out_w / box[2], out_h / box[3]
    sig_x, sig_y = max(0.0, (1 / sx - 1) / 2), max(0.0, (1 / sy - 1) / 2)
    if sig_x < 1e-3 and sig_y < 1e-3:
        return img
    return cv2.GaussianBlur(img, (0, 0), sigmaX=max(sig_x, 1e-3), sigmaY=max(sig_y, 1e-3))


def warp_image(img: np.ndarray, box: Box, out_w: int, out_h: int) -> np.ndarray:
    """Real image (any dtype, 2D or 3-channel) -> engine grid, antialiased, edges replicated."""
    src = _prefilter(img.astype(np.float32), box, out_w, out_h)
    out = cv2.warpAffine(src, box_affine(box, out_w, out_h), (out_w, out_h), flags=cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_REPLICATE)
    return np.clip(np.rint(out), 0, 255).astype(np.uint8) if img.dtype == np.uint8 else out


def resample(arr: np.ndarray, valid: np.ndarray, box: Box, out_w: int, out_h: int) -> tuple[np.ndarray, np.ndarray]:
    """Float map with a validity mask -> engine grid by normalised convolution; NaN where < half valid."""
    v = valid.astype(np.float32)
    a = np.where(valid, arr, 0).astype(np.float32)
    A = box_affine(box, out_w, out_h)
    aw = cv2.warpAffine(_prefilter(a, box, out_w, out_h), A, (out_w, out_h), flags=cv2.INTER_LINEAR, borderValue=0)
    vw = cv2.warpAffine(_prefilter(v, box, out_w, out_h), A, (out_w, out_h), flags=cv2.INTER_LINEAR, borderValue=0)
    ok = vw > 0.5
    out = np.full((out_h, out_w), np.nan, np.float32)
    out[ok] = aw[ok] / vw[ok]
    return out, ok


def warp_mask(mask: np.ndarray, box: Box, out_w: int, out_h: int) -> np.ndarray:
    """Real mask -> engine grid; an engine pixel is masked if any real pixel under it is.
    Conservative when enlarging (the pipeline's use: masks on the half-resolution grid, 1104 px wide, onto the 1280 px engine grid). When shrinking,
    the bilinear footprint plus the small prefilter can miss a corner overlap of under about 3.5 % of an
    engine pixel, so do not rely on it to be conservative there."""
    m = cv2.warpAffine(_prefilter(mask.astype(np.float32), box, out_w, out_h), box_affine(box, out_w, out_h),
                       (out_w, out_h), flags=cv2.INTER_LINEAR, borderValue=0)
    return m > 1e-3


def _norm_gray(img: np.ndarray) -> np.ndarray:
    g = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(g.astype(np.float32), (0, 0), 2.0)


def _gain_mse(a: np.ndarray, b: np.ndarray, valid: np.ndarray) -> float:
    x, y = a[valid].ravel(), b[valid].ravel()
    A = np.c_[x, np.ones_like(x)]
    coef = np.linalg.lstsq(A, y, rcond=None)[0]
    return float(np.mean((A @ coef - y) ** 2))


def measure_box(real_img: np.ndarray, engine0: np.ndarray, shifts=(1, 2, 4)) -> dict:
    """Pick the box by MSE on frame 0 (gain and offset removed); the winner must beat the runner-up
    (MSE ratio < 0.9) and must beat its own +-1, 2, 4 px shifts."""
    out_h, out_w = engine0.shape[:2]
    real_h, real_w = real_img.shape[:2]
    ge = _norm_gray(engine0)
    mse: dict[str, float] = {}
    boxes = candidate_boxes(real_w, real_h, out_w, out_h)
    ones = np.ones((real_h, real_w), bool)
    for name, b in boxes.items():
        valid = resample(ones.astype(np.float32), ones, b, out_w, out_h)[1]  # engine pixels inside the real frame
        mse[name] = _gain_mse(_norm_gray(warp_image(real_img, b, out_w, out_h)), ge, valid)
    order = sorted(mse, key=mse.get)
    best = order[0]
    ratio = mse[best] / mse[order[1]] if len(order) > 1 else 0.0  # best over runner-up; one candidate passes
    b = boxes[best]
    sx, sy = out_w / b[2], out_h / b[3]
    shift_mse = {}
    for s in shifts:
        for dx, dy in ((s, 0), (-s, 0), (0, s), (0, -s)):
            bb = (b[0] + dx / sx, b[1] + dy / sy, b[2], b[3])
            valid = resample(ones.astype(np.float32), ones, bb, out_w, out_h)[1]
            shift_mse[f"{dx:+d},{dy:+d}"] = _gain_mse(_norm_gray(warp_image(real_img, bb, out_w, out_h)), ge, valid)
    shift_ok = mse[best] <= min(shift_mse.values())
    return {"name": best, "box": list(b), "mse": mse, "ratio": ratio, "shift_mse": shift_mse,
            "ok": bool(ratio < 0.9 and shift_ok)}
