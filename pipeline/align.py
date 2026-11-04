"""One scale and one shift: s * g + t ~ tank disparity, fitted with a Huber loss in inverse-depth space.

g is the depth model's inverse depth (1 / z_g); the target is disparity in full-resolution pixels
(the MiDaS convention: inverse depth is affine in disparity)."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


@dataclass(frozen=True)
class AffineFit:
    s: float
    t: float
    delta: float
    c_tukey: float
    n: int
    n_inliers: int
    iters: int

    def apply(self, g: np.ndarray) -> np.ndarray:
        return self.s * np.asarray(g, dtype=np.float64) + self.t

    def to_dict(self) -> dict:
        return asdict(self)


def _irls(A, y, s, t, weight, max_iter, tol, yscale):
    it = 0
    for it in range(1, max_iter + 1):
        w = weight(A[:, 0] * s + t - y)
        if np.count_nonzero(w) < 3:
            break
        sw = np.sqrt(w)
        s_new, t_new = np.linalg.lstsq(A * sw[:, None], y * sw, rcond=None)[0]
        done = abs(s_new - s) <= tol * max(abs(s), 1e-12) and abs(t_new - t) <= tol * max(abs(t), yscale)
        s, t = s_new, t_new
        if done:
            break
    return s, t, it


def _ransac_start(x, y, delta, n_hyp=300, seed=0):
    rng = np.random.default_rng(seed)
    best, best_n = None, -1
    for _ in range(n_hyp):
        i, j = rng.integers(0, x.size, 2)
        if abs(x[i] - x[j]) < 1e-9 * max(abs(x[i]), 1e-12):
            continue
        s = (y[i] - y[j]) / (x[i] - x[j])
        t = y[i] - s * x[i]
        n = int(np.count_nonzero(np.abs(s * x + t - y) < delta))
        if n > best_n:
            best, best_n = (s, t), n
    return best, best_n


def huber_affine_fit(g: np.ndarray, d: np.ndarray, mask: np.ndarray, delta: float | None = None,
                     max_iter: int = 100, tol: float = 1e-12) -> AffineFit:
    """s * g + t ~ d on the mask. Huber (delta = 0.05 * median(d)) by IRLS from the least-squares start,
    as section 7 specifies; then Tukey's biweight from the better of the Huber solution and a 2-point
    RANSAC start (more pixels within delta). Huber alone is not enough: a near object is a high-leverage
    point (large g) and biases a Huber fit by ~6 % in the planted-object test."""
    m = mask & np.isfinite(g) & np.isfinite(d)
    x = np.asarray(g, dtype=np.float64)[m]
    y = np.asarray(d, dtype=np.float64)[m]
    if x.size < 100:
        raise ValueError(f"fit mask has {x.size} pixels; need at least 100")
    if np.ptp(x) <= 1e-9 * np.abs(x).max():
        raise ValueError("degenerate g: the depth model's inverse depth is constant on the fit mask")
    if delta is None:
        delta = 0.05 * float(np.median(y))
    A = np.c_[x, np.ones_like(x)]
    yscale = float(np.median(np.abs(y)))
    s, t = np.linalg.lstsq(A, y, rcond=None)[0]
    huber = lambda r: np.where(np.abs(r) <= delta, 1.0, delta / np.maximum(np.abs(r), 1e-300))  # noqa: E731
    s, t, it1 = _irls(A, y, s, t, huber, max_iter, tol, yscale)
    n_huber = int(np.count_nonzero(np.abs(s * x + t - y) < delta))
    start, n_ransac = _ransac_start(x, y, delta)
    if start is not None and n_ransac > n_huber:
        s, t = start
    r = s * x + t - y
    c = max(delta, 4.685 * 1.4826 * float(np.median(np.abs(r - np.median(r)))))
    tukey = lambda r: np.where(np.abs(r) < c, (1 - (r / c) ** 2) ** 2, 0.0)  # noqa: E731
    s, t, it2 = _irls(A, y, s, t, tukey, max_iter, tol, yscale)
    n_in = int(np.count_nonzero(np.abs(s * x + t - y) < c))
    return AffineFit(float(s), float(t), float(delta), float(c), int(x.size), n_in, it1 + it2)


def rel_residual(pred_disp: np.ndarray, ref_disp: np.ndarray) -> np.ndarray:
    """(pred - ref) / ref, signed: positive means the prediction reads nearer than the reference."""
    pred = np.asarray(pred_disp, dtype=np.float64)
    ref = np.asarray(ref_disp, dtype=np.float64)
    out = np.full(ref.shape, np.nan)
    ok = np.isfinite(pred) & np.isfinite(ref) & (ref > 0)
    out[ok] = (pred[ok] - ref[ok]) / ref[ok]
    return out
