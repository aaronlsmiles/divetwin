"""The heat palette and the overlay: the signed residual drawn over the generated frame.

|r| is clipped at CLIP (0.5) and picks a place on one sequential ramp, laid over the frame at a CONSTANT alpha (0.8) on a
dimmed greyscale of the frame, so the blended lightness follows |r| on any frame, dark or light (the frame under the heat
only dims the lightness, it never reorders it), and r = 0 is the dark end of a ramp, never the grey of "unverified". The sign
picks the ramp: POSITIVE (the generated tank reads nearer than the real one) runs through warm oranges, NEGATIVE (reads
farther) through blues. Both ramps are monotone in luminance and share the same lightness steps, so a reader sees how much
from the lightness and which way from the hue, and a colour-blind reader still gets the amount.

Pixels nothing verifies are a 45 degree hatch of two greys (stripes 4 px across, 96 and 128), opaque, so they can never be
mistaken for the frame's own texture or for any residual. The real pane's unseen and past-the-cap pixels are one flat grey,
the hatch's mean (GREY_RGB). No rainbow; gold is kept for the page's own D > 3 moment.

A tracked moving object (call 69) is not unverified: the caller gives its residual over the pixels the render saw, drawn in
the same signed palette, and its mask as `track`, which gets a 2 px outline (OUTLINE_RGB). The object stays out of the pose
and out of D (dive.py); the page says so ("outlined: a tracked moving object, drawn but not counted in D"). A pixel the
render never saw stays hatched, inside the outline too."""
from __future__ import annotations

import numpy as np

CLIP = 0.5
ALPHA = 0.8                       # constant over every verified pixel
DIM = 0.5                         # the frame under the heat: its luminance, at this fraction
HATCH_GREYS = (96, 128)           # unverified: two greys in 45 degree stripes ...
HATCH_STRIPE_PX = 4               # ... this wide, measured across the stripe (perpendicular to the 45 degree line)
OUTLINE_RGB = (255, 255, 255)     # a tracked moving object's outline: neither a ramp stop nor a hatch grey
OUTLINE_PX = 2                    # a band this wide, straddling the mask's edge
GREY_RGB = (112, 112, 112)        # the real pane's flat grey (no real camera saw it, or past the trusted range): the hatch's mean
POSITIVE = ((0.0, (74, 28, 12)), (0.5, (214, 112, 32)), (1.0, (255, 236, 170)))   # generated reads nearer than the tank
NEGATIVE = ((0.0, (12, 30, 74)), (0.5, (36, 124, 206)), (1.0, (186, 232, 255)))   # generated reads farther
FLOOR_RAMP = ((0.0, (30, 12, 52)), (0.5, (124, 64, 184)), (1.0, (236, 200, 255)))  # the floor map's own violet: no sign, no meaning
FLOOR_MEANS = "where mono depth already errs on the real tank; display only, the same for every frame"   # the page's caption (call 85)
UNVERIFIED_REASONS = ("no real camera saw it",
                      "the generated tank is past the trusted range (the recording's travel cap, or the path was lost)")
OUTLINED = "outlined: a tracked moving object, drawn but not counted in D"


def ramp(stops, t: np.ndarray) -> np.ndarray:
    """(…,) in [0, 1] -> (…, 3) float RGB by piecewise-linear interpolation of the stops."""
    xs = [s[0] for s in stops]
    return np.stack([np.interp(t, xs, [s[1][c] for s in stops]) for c in range(3)], axis=-1)


def luminance(rgb: np.ndarray) -> np.ndarray:
    rgb = np.asarray(rgb, np.float64)
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def hatch(h: int, w: int) -> np.ndarray:
    """(h, w) uint8: the unverified hatch. Constant along x + y (a 45 degree line), two greys, HATCH_STRIPE_PX across the
    stripe: x + y changes by sqrt(2) per px of distance across a 45 degree line, so a stripe spans 4 * sqrt(2) of x + y."""
    s = np.floor(np.add.outer(np.arange(h), np.arange(w)) / (HATCH_STRIPE_PX * np.sqrt(2.0))).astype(np.int64) % 2
    return np.where(s == 0, HATCH_GREYS[0], HATCH_GREYS[1]).astype(np.uint8)


def outline_band(mask: np.ndarray) -> np.ndarray:
    """(h, w) bool: the 2 px band round a mask's edge (its dilation by one pixel minus its erosion by one, 3 x 3). The frame's
    own edge is not an outline: the padding repeats the edge pixels."""
    m = np.pad(np.asarray(mask, bool), 1, mode="edge")
    h, w = mask.shape
    shifts = [m[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
    return np.logical_or.reduce(shifts) & ~np.logical_and.reduce(shifts)


def heat_overlay(frame_bgr: np.ndarray, r: np.ndarray, track: np.ndarray | None = None) -> np.ndarray:
    """frame (H, W, 3) uint8 BGR and the signed residual r (H, W; NaN where unverified) -> BGR uint8. `track` (H, W bool, the
    tracked moving objects' pixels, call 69) is outlined in OUTLINE_RGB; what is drawn inside it is r, as everywhere."""
    assert frame_bgr.shape[:2] == r.shape, (frame_bgr.shape, r.shape)
    assert track is None or track.shape == r.shape, (track.shape, r.shape)
    f = frame_bgr[..., ::-1].astype(np.float64)                      # RGB
    ok = np.isfinite(r)
    t = np.where(ok, np.minimum(np.abs(np.where(ok, r, 0.0)), CLIP) / CLIP, 0.0)
    col = np.where((r > 0)[..., None], ramp(POSITIVE, t), ramp(NEGATIVE, t))
    base = (DIM * luminance(f))[..., None]
    out = base * (1 - ALPHA) + col * ALPHA
    out = np.where(ok[..., None], out, hatch(*r.shape)[..., None].astype(np.float64))
    if track is not None and track.any():
        out = np.where(outline_band(track)[..., None], np.array(OUTLINE_RGB, np.float64), out)
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)[..., ::-1]


def grey_frame(frame_bgr: np.ndarray) -> np.ndarray:
    """A whole frame marked unverifiable: the hatch, as heat_overlay draws one pixel (the generated frame does not show)."""
    return heat_overlay(frame_bgr, np.full(frame_bgr.shape[:2], np.nan))


def palette_json() -> dict:
    """What the page needs to draw its legend from the same numbers."""
    return {"clip": CLIP, "alpha": ALPHA, "dim": DIM,
            "unverified": "hatched = unverified",
            "unverified_hatch": {"angle_deg": 45, "stripe_px": HATCH_STRIPE_PX, "greys": list(HATCH_GREYS)},
            "unverified_reasons": list(UNVERIFIED_REASONS),
            "outlined": OUTLINED, "outline": {"rgb": list(OUTLINE_RGB), "width_px": OUTLINE_PX},
            "unseen_rgb": list(GREY_RGB),
            "positive": [[t, list(c)] for t, c in POSITIVE], "negative": [[t, list(c)] for t, c in NEGATIVE],
            "positive_means": "the generated tank reads nearer than the real one",
            "negative_means": "the generated tank reads farther than the real one",
            "floor_ramp": [[t, list(c)] for t, c in FLOOR_RAMP], "floor_means": FLOOR_MEANS}
