"""The numbers: AbsRel on verified pixels, the noise floor, the divergence index D, the verified share V,
the report times, the first sustained departure and the far-end test."""
from __future__ import annotations

import numpy as np

REPORT_SECONDS = (0.0, 1.0, 2.5, 5.0, 10.0)
D_THRESHOLD = 3.0
D_RUN = 12  # frames, not seconds: half a second only at 24 fps (a clip at another rate gets another duration)


def abs_rel(r: np.ndarray, mask: np.ndarray) -> float:
    v = np.abs(r[mask & np.isfinite(r)])
    return float(np.mean(v)) if v.size else float("nan")


def noise_floor(abs_rels: list[float]) -> float:
    v = np.asarray([a for a in abs_rels if np.isfinite(a)])
    return float(np.median(v)) if v.size else float("nan")


def divergence(abs_rel_k: np.ndarray, floor: float) -> np.ndarray:
    return np.asarray(abs_rel_k, dtype=np.float64) / floor


def verified_share(seen: np.ndarray) -> float:
    return float(np.count_nonzero(seen) / seen.size)


def at_seconds(series: np.ndarray, fps: float = 24.0, seconds=REPORT_SECONDS) -> dict[str, float | None]:
    """D (or V) at 0, 1, 2.5, 5 and 10 s; the last frame stands in for a time just past the end."""
    out: dict[str, float | None] = {}
    n = len(series)
    for s in seconds:
        k = int(round(s * fps))
        if k >= n and k - (n - 1) <= 1:
            k = n - 1
        out[f"{s:g}"] = None if k >= n or not np.isfinite(series[k]) else float(series[k])
    return out


def first_sustained(D: np.ndarray, thr: float = D_THRESHOLD, run: int = D_RUN) -> int | None:
    """First frame k with D > thr for `run` consecutive frames (NaN breaks a run)."""
    count = 0
    for k, d in enumerate(D):
        count = count + 1 if np.isfinite(d) and d > thr else 0
        if count == run:
            return k - run + 1
    return None


def first_wall_frame(forward: np.ndarray, far_end: float, lost: np.ndarray) -> int | None:
    """First frame whose recovered forward travel reaches the far end as measured, while the path holds."""
    for k, (z, lo) in enumerate(zip(forward, lost)):
        if lo:
            return None
        if z >= far_end:
            return k
    return None


def lost_from(fitness: np.ndarray, n_ok: np.ndarray, min_n: int = 200, ratio: float = 0.5) -> int | None:
    """Depth registration is lost from the first frame whose fitness falls below half the median of
    frames 1-5 (or whose correspondences run out); it is never resumed."""
    ref = float(np.median(fitness[1:6])) if len(fitness) > 1 else 1.0
    for k in range(1, len(fitness)):
        if fitness[k] < ratio * ref or n_ok[k] < min_n:
            return k
    return None
