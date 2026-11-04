"""Depth for generated clips (task 3.1): the local half. The GPU half is modal_depth.py (clips, tracks).

Contract with sub-plan A (section 5): runs/da3/clips/<clip_id>.npz holds
    inv     (N, H, W) float16   DA3 Mono-Large inverse depth 1 / z on the clip's own grid, after the 5-frame median
    moving  (N, H, W) bool, packed with np.packbits along the last axis   (only when a clip has tracked objects)
and nothing else; N and (H, W) equal the mp4's. What produced it goes in a sidecar <clip_id>.json.

The pipeline: DA3 on every decoded frame (as JPEG q95, at its own processing size, float16) -> 5-frame temporal
median on inverse depth (edge frames replicate, so frame 0, the fit frame, keeps its own value) -> bilinear
resize to the clip's grid -> float16. The median runs at DA3's own resolution, which is 4.7 times cheaper
to send and to filter than the clip grid; the resize after it is the same cv2 call the floor used."""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

import clips
from clips import ClipSpec
from recordings import runs_dir

MEDIAN_WINDOW = 5
PROCESS_RES = 504            # modal_depth.PROCESS_RES: recorded in the sidecar


def temporal_median(inv: np.ndarray, k: int = MEDIAN_WINDOW) -> np.ndarray:
    """Median over a window of k frames centred on each frame, indices clamped at the ends (edge replicate)."""
    assert k % 2 == 1 and inv.ndim == 3
    n, half = len(inv), k // 2
    x = np.asarray(inv, np.float32)
    out = np.empty_like(x)
    for i in range(n):
        out[i] = np.median(x[np.clip(np.arange(i - half, i + half + 1), 0, n - 1)], axis=0)
    return out


def resize_inv(inv: np.ndarray, w: int, h: int) -> np.ndarray:
    """(N, h0, w0) float -> (N, h, w) float16, bilinear, as modal_depth resizes a single frame."""
    return np.stack([cv2.resize(f.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR) for f in inv]).astype(np.float16)


def process(native: np.ndarray, w: int, h: int) -> np.ndarray:
    return resize_inv(temporal_median(native), w, h)


def depth_dir() -> Path:
    return runs_dir() / "da3" / "clips"


def write_depth_npz(spec: ClipSpec, inv: np.ndarray, moving: np.ndarray | None = None, meta: dict | None = None) -> Path:
    path = clips.depth_path(spec)
    path.parent.mkdir(parents=True, exist_ok=True)
    arrs = {"inv": np.asarray(inv, np.float16)}
    if moving is not None:
        arrs["moving"] = np.packbits(np.asarray(moving, bool), axis=-1)
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, **arrs)
    tmp.replace(path)
    side = {"clip": spec.id, "median_window": MEDIAN_WINDOW, "process_res": PROCESS_RES, "frames": int(inv.shape[0]),
            "grid": [int(inv.shape[2]), int(inv.shape[1])], "tracked": moving is not None, **(meta or {})}
    path.with_suffix(".json").write_text(json.dumps(side, indent=1, allow_nan=False) + "\n")
    return path


def check_depth(spec: ClipSpec) -> dict:
    """{'ok', 'reason', 'frames', 'grid'}: the npz exists, holds exactly the contract's arrays, is finite and positive,
    and matches the mp4's frame count and the engine's grid."""
    p = clips.depth_path(spec)
    out = {"ok": False, "reason": None, "frames": 0, "grid": None}
    if not p.exists():
        out["reason"] = "no depth file"
        return out
    mp4 = clips.check_clip(spec)
    if not mp4["ok"]:
        out["reason"] = f"the mp4 is not valid: {mp4['reason']}"
        return out
    with np.load(p) as z:
        keys = set(z.files)
        if keys not in ({"inv"}, {"inv", "moving"}):
            out["reason"] = f"arrays {sorted(keys)}, expected inv (and moving)"
            return out
        inv = z["inv"]
        moving = z["moving"] if "moving" in keys else None
    n, h, w = inv.shape
    out.update(frames=n, grid=[w, h])
    gw, gh = clips.GRID[spec.engine]
    if inv.dtype != np.float16:
        out["reason"] = f"inv is {inv.dtype}, expected float16"
    elif n != mp4["frames"]:
        out["reason"] = f"{n} depth maps for {mp4['frames']} video frames"
    elif (w, h) != (gw, gh):
        out["reason"] = f"depth grid {w}x{h}, expected {gw}x{gh}"
    elif not np.isfinite(inv).all() or not (inv > 0).all():
        out["reason"] = "inv is not finite and positive everywhere"
    elif moving is not None and (moving.shape[:2] != (n, h) or moving.shape[2] != -(-w // 8)):
        out["reason"] = f"moving packs to {moving.shape}, expected {(n, h, -(-w // 8))}"
    else:
        out["ok"] = True
    return out


def clip_seeds_path() -> Path:
    return runs_dir() / "clip_seeds.json"


def load_clip_seeds() -> dict[str, list[dict]]:
    """runs/clip_seeds.json: {clip_id: [{"frame": int, "obj": str, "box": [x0, y0, x1, y1]}]} in the clip's own
    pixels, written by hand after a clip's reading names something that moves. Absent file: no tracks (the default)."""
    p = clip_seeds_path()
    if not p.exists():
        return {}
    seeds = json.loads(p.read_text())
    for cid, items in seeds.items():
        spec = clips.parse_clip_id(cid)
        gw, gh = clips.GRID[spec.engine]
        for it in items:
            x0, y0, x1, y1 = it["box"]
            if not (0 <= x0 < x1 <= gw and 0 <= y0 < y1 <= gh) or not (0 <= int(it["frame"]) < clips.expected_frames(spec)) \
                    or not str(it["obj"]):
                raise ValueError(f"{cid}: bad seed {it}: box inside {gw}x{gh}, frame inside the clip, a name")
    return seeds


def union_masks(per_obj: dict[str, np.ndarray]) -> np.ndarray:
    """Packed (N, H, ceil(W / 8)) masks of several objects -> one packed mask (a bitwise OR of packed bits is the OR)."""
    arrs = list(per_obj.values())
    out = arrs[0].copy()
    for a in arrs[1:]:
        out |= a
    return out
