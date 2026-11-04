"""Tiny mp4 writers for tests (PyAV, libx264)."""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import av
import numpy as np


def write_mp4(path, frames: list[np.ndarray], fps: int = 24) -> Path:
    """BGR uint8 frames -> an H.264 mp4 (even sizes only)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    h, w = frames[0].shape[:2]
    with av.open(str(path), "w") as c:
        s = c.add_stream("libx264", rate=Fraction(fps, 1))
        s.width, s.height, s.pix_fmt = w, h, "yuv420p"
        s.options = {"crf": "10", "preset": "ultrafast"}
        for f in frames:
            for pkt in s.encode(av.VideoFrame.from_ndarray(np.ascontiguousarray(f), format="bgr24")):
                c.mux(pkt)
        for pkt in s.encode():
            c.mux(pkt)
    return path


def noise_frames(n: int, w: int = 64, h: int = 48, seed: int = 0) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
    return [np.roll(base, i, axis=1) for i in range(n)]
