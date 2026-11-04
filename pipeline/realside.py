"""The real side: frame states from fresh SAM 2 masks, start frames, the static-tank disparity map.

All maps here live on the half-resolution grid (1104 x 621) the stereo network and SAM 2 ran on;
disparity values are in half-resolution pixels until units.half_to_full turns them into full ones."""
from __future__ import annotations

import warnings

import cv2
import numpy as np

HALF_W, HALF_H = 1104, 621
UP_PX_FULL = 60       # section 7: the hand holds the bottle from above
DILATE_PX_FULL = 15
MIN_AREA_FRAC = 5e-4  # a mask smaller than this share of the frame counts as absent
STATIC_IOU = 0.9      # a bottle whose mask overlaps a neighbouring frame's (either side) this much is standing still
MIN_OBS = 10          # section 7: a tank pixel needs at least 10 valid observations


def unpack_masks(packed: np.ndarray, width: int = HALF_W) -> np.ndarray:
    return np.unpackbits(packed, axis=-1, count=width).astype(bool)


def up_extend(mask: np.ndarray, length: int) -> np.ndarray:
    """Every masked pixel also masks the `length` pixels above it (toward the top edge)."""
    cs = np.cumsum(mask[::-1].astype(np.int32), axis=0)[::-1]  # masked count from row y to the bottom
    below = np.zeros_like(cs)
    if length + 1 < mask.shape[0]:
        below[: mask.shape[0] - length - 1] = cs[length + 1:]
    return (cs - below) > 0


def exclusion_mask(bottle: np.ndarray, hand: np.ndarray, grid_scale: float = 0.5) -> np.ndarray:
    """Bottle and hand, extended upward 60 px and dilated 15 px (full-resolution pixels, scaled to the grid)."""
    m = up_extend(bottle | hand, int(round(UP_PX_FULL * grid_scale)))
    r = int(round(DILATE_PX_FULL * grid_scale))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    return cv2.dilate(m.astype(np.uint8), k) > 0


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    u = np.count_nonzero(a | b)
    return 1.0 if u == 0 else np.count_nonzero(a & b) / u


def classify_with_ious(bottle: np.ndarray, hand: np.ndarray) -> tuple[list[str], list[float | None]]:
    """Per frame: 'hand' (a hand is in view), 'moving' (no hand, bottle moving), 'quiet' (no hand,
    bottle overlapping either neighbouring frame's by IoU >= 0.9) or 'empty' (no hand, no bottle).
    Masks are (N, h, w) bool. Also returns each frame's best-neighbour bottle IoU (the number the
    'quiet' test compares with 0.9, so a reader can see the margin); None for 'hand' and 'empty'
    frames and for a lone frame, which have no bottle pair to compare."""
    n, h, w = bottle.shape
    thr = MIN_AREA_FRAC * h * w
    states: list[str] = []
    ious: list[float | None] = []
    for k in range(n):
        if np.count_nonzero(hand[k]) >= thr:
            states.append("hand")
            ious.append(None)
        elif np.count_nonzero(bottle[k]) < thr:
            states.append("empty")
            ious.append(None)
        else:
            nbrs = [_iou(bottle[k], bottle[j]) for j in (k - 1, k + 1) if 0 <= j < n]
            best = max(nbrs) if nbrs else None
            states.append("quiet" if best is None or best >= STATIC_IOU else "moving")
            ious.append(best)
    return states, ious


def classify_frames(bottle: np.ndarray, hand: np.ndarray) -> list[str]:
    """The frame states alone; see classify_with_ious."""
    return classify_with_ious(bottle, hand)[0]


def start_and_tail(states: list[str]) -> dict:
    """The dive's start frame and the tail that builds the static-tank map.

    The hand-free run is the trailing run of 'empty'/'quiet' frames: the scene after the hand has left.
    The start lies inside it only: its last 'empty' frame, else its last 'quiet' frame. The tail is the run
    of frames of the start's own kind (all 'empty' or all 'quiet') counted back from the start, so it never
    mixes frames with and without the bottle. An 'empty' tail builds the map by the 'tail' recipe (a plain
    median) at any length >= 1 (Aaron's call 45); a 'quiet' tail (a still bottle in every frame) needs
    >= MIN_OBS of them, else the recipe is 'masked'.

    If there is no hand-free run (the recording ends in a hand or a moving bottle) nothing says "after the
    hand leaves"; the Gate S behaviour stays: start = the last 'empty' frame anywhere, else the last 'quiet'
    one, else None, with tail None and recipe 'masked'.

    Returns start, kind ('empty'/'quiet'/None), tail ([first, last] frame indices, inclusive, or None),
    tail_len, empty_tail_len (trailing 'empty' frames at the very end) and recipe."""
    n = len(states)
    tail_start = n
    while tail_start > 0 and states[tail_start - 1] in ("empty", "quiet"):
        tail_start -= 1
    lo = tail_start if tail_start < n else 0  # no hand-free run: the Gate S search spans the whole recording
    start = kind = None
    for kind_try in ("empty", "quiet"):
        hits = [k for k in range(lo, n) if states[k] == kind_try]
        if hits:
            start, kind = hits[-1], kind_try
            break
    tail, tail_len = None, 0
    if start is not None and tail_start < n:
        a = start
        while a > tail_start and states[a - 1] == kind:
            a -= 1
        tail, tail_len = [a, start], start - a + 1
    n_empty_tail = 0
    while n_empty_tail < n and states[n - 1 - n_empty_tail] == "empty":
        n_empty_tail += 1
    recipe = "tail" if tail_len >= (1 if kind == "empty" else MIN_OBS) else "masked"
    return {"start": start, "kind": kind, "tail": tail, "tail_len": tail_len,
            "empty_tail_len": n_empty_tail, "recipe": recipe}


def region_mad(gray: np.ndarray, region: np.ndarray) -> np.ndarray:
    """Cross-check for the start frame (the master plan's test): mean absolute difference of each frame
    against the per-pixel median plate inside `region`, after a gain/offset match to the plate."""
    plate = np.median(gray, axis=0)
    p = plate[region].astype(np.float64)
    out = np.empty(gray.shape[0])
    for k in range(gray.shape[0]):
        x = gray[k][region].astype(np.float64)
        A = np.c_[x, np.ones_like(x)]
        coef = np.linalg.lstsq(A, p, rcond=None)[0]
        out[k] = float(np.mean(np.abs(A @ coef - p)))
    return out


def tank_median(disps: np.ndarray, excl: np.ndarray | None = None, min_obs: int = MIN_OBS,
                chunk_rows: int = 64) -> dict:
    """Per-pixel median disparity over frames, ignoring excluded or non-positive pixels.
    disps (N, h, w) float; excl (N, h, w) bool or None (the tail recipe needs no masks)."""
    n, h, w = disps.shape
    med = np.full((h, w), np.nan, np.float32)
    nobs = np.zeros((h, w), np.int16)
    spread = np.full((h, w), np.nan, np.float32)
    for r0 in range(0, h, chunk_rows):
        blk = disps[:, r0:r0 + chunk_rows].astype(np.float32).copy()
        bad = ~np.isfinite(blk) | (blk <= 0)
        if excl is not None:
            bad |= excl[:, r0:r0 + chunk_rows]
        blk[bad] = np.nan
        cnt = np.count_nonzero(~bad, axis=0)
        nobs[r0:r0 + chunk_rows] = cnt
        ok = cnt >= min_obs
        if ok.any():
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN columns are the invalid pixels
                m = np.nanmedian(blk, axis=0)
                q1, q3 = np.nanpercentile(blk, [25, 75], axis=0)
            med[r0:r0 + chunk_rows][ok] = m[ok]
            ok2 = ok & (cnt >= 2)  # a spread needs two observations; a single frame has none
            spread[r0:r0 + chunk_rows][ok2] = ((q3 - q1) / m)[ok2]
    return {"tank_disp_half": med, "n_obs": nobs, "rel_iqr": spread, "valid": np.isfinite(med)}


def tail_min_obs(n_frames: int) -> int:
    """Valid observations a tail-recipe pixel needs: MIN_OBS, or every frame of a tail shorter than that."""
    return min(MIN_OBS, n_frames)


def xcheck(tail_map: np.ndarray, masked_map: np.ndarray, excl_any: np.ndarray) -> dict:
    """Cross-check only, never an input to the map: |masked - tail| / tail over the pixels valid in both maps
    and outside every mask (excl_any, the union of the masked recipe's exclusions). n, med, p90."""
    ok = np.isfinite(tail_map) & np.isfinite(masked_map) & (tail_map > 0) & ~excl_any
    if not ok.any():
        return {"n": 0, "med": None, "p90": None}
    r = np.abs(masked_map[ok].astype(np.float64) - tail_map[ok]) / tail_map[ok]
    return {"n": int(ok.sum()), "med": float(np.median(r)), "p90": float(np.percentile(r, 90))}


def progress(frames: list[int]) -> list[float]:
    a, b = frames[0], frames[-1]
    return [0.0 if b == a else (j - a) / (b - a) for j in frames]


def write_png16(path, disp_full: np.ndarray, max_disp: float = 1024.0) -> None:
    """tank_disp as PNG16 for eyeballing: value = disp / max_disp * 65535, 0 = invalid."""
    v = np.where(np.isfinite(disp_full), np.clip(disp_full / max_disp, 0, 1) * 65535, 0)
    cv2.imwrite(str(path), v.astype(np.uint16))
