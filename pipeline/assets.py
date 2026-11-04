"""Task 3.4: everything the page loads, written under runs/assets/ in the exact layout it will have on R2.

    runs/assets/
      clips.json                                  the page's one contract: runs/clips.json + assets + recordings + palette
      media_manifest.json  MEDIA.md               every file with bytes and sha256, and the R2 key it will have
      clips/<id>/gen.mp4                          the generated clip, BYTE-IDENTICAL to the engine's file (no re-encode:
                                                  that would strip a Runway clip's C2PA credentials)
      clips/<id>/heat.mp4                         the generated frame with the signed residual laid over it (heat.py)
      clips/<id>/real.mp4                         the tank rebuilt from stereo, rendered along the recovered path; grey unseen
      clips/<id>/poster.jpg  poster_heat.jpg      the generated frame 40 % in, plain and with the heat
      clips/<id>/relief.png                       aligned generated depth, 160 x 90 cells in 11 columns, PNG16 (see "relief")
      clips/<id>/tank_relief.png                  the real tank's depth over this clip's mapping box, one 160 x 90 PNG16 cell
      clips/<id>/path.json                        the plan-view path
      recordings/<condition>/start.jpg            the real photograph every dream starts from
      recordings/<condition>/tank_relief.png      the measured tank's depth, one 160 x 90 PNG16 cell
      recordings/<condition>/plan.json            the tank seen from above (a profile at mid-height) and its far end
      recordings/<condition>/floor_map.png        DA3's median |relative error| on the real frames, per pixel (display only)
      recordings/<condition>/floor_preview.jpg    the same, coloured (its own violet ramp; hatched where unobserved)

Every PNG16 says how to read it (`encoding`: a 16-bit PNG decoder such as fast-png, not canvas). Every clip block carries
its provenance (`gen` is the engine's own file, byte for byte, with `source_sha256`; the rest is derived), the prompt text
(from prompts.PROMPTS, never retyped) and the seed the clip was made with. The heat's unverified pixels are a hatch and the
real pane's unseen and past-the-cap pixels one flat grey (heat.py).

Task C0 (the page's plan, sub-plan C): each clip's `relief` block also carries the cell's intrinsics (`fx`, `fy`, `cx`, `cy`, from
the calibration through the mapping box), so the relief never assumes the principal point is the centre; heat.palette_json carries
the floor map's ramp and words; and heat.mp4 and real.mp4 are encoded with a keyframe at least every GOP (12) frames so a seek
lands cheaply. gen.mp4 is still the engine's file byte for byte.

Tracked moving objects (call 69): the `moving` mask in a clip's depth npz stays out of the pose and out of D (dive.py is
untouched), but the heat draws the frozen-fit residual over those pixels wherever the render has a surface and the generated
depth is finite, in the same signed palette as verified pixels, with the track's outline round it ("outlined: a tracked
moving object, drawn but not counted in D"; heat.palette_json). Pixels the render never saw stay hatched, track or not. Past
the cap everything is hatched, tracks included. Each clip block flags per frame whether a track is present (`moving_track`:
true or false on the trusted frames, null from the first unverifiable frame on).

Unverifiable frames (call 50): every frame from `unverifiable_from` on, whether the path was lost or a recording's travel
cap was passed (pellets, 100 su), is hatched in heat.mp4, flat grey in real.mp4, empty (0) in relief.png, null in the
path points of path.json and clips.json, and flagged in clips.json with the reason. The clip's `travel` and `wall_frame` are
recomputed from the trusted frames only (the dive entry's own values sit under `untrusted`), and the per-frame `tracks` and
`icp` arrays and `path_disagreement` are null past the cap. Nothing past the cap is shown as measured.

R2: media_manifest.json maps each file clips.json references to `divetwin/v1/<path>` (immutable, `Cache-Control: public,
max-age=31536000, immutable`, sha256 and original/derived in MEDIA.md, the prototype's tools/media.py ported from
onewishdubplate's at publish time, task 6.2); a file under runs/assets that nothing references is warned about and left
out. This module never uploads."""
from __future__ import annotations

import hashlib
import json
import shutil
import warnings
from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np

import clips as clipmod
import heat
from align import AffineFit, rel_residual
from camera import Pose
from clips import parse_clip_id
from dive import TRUSTED_TRAVEL_SU, Tank, frame_products
from prompts import PROMPTS
from recordings import runs_dir

ASSET_VERSION = "v1"
PREFIX = f"divetwin/{ASSET_VERSION}/"
CACHE_CONTROL = "public, max-age=31536000, immutable"
CELL_W, CELL_H, COLS = 160, 90, 11
Z_SCALE = 16.0                      # relief PNG16: stored = round(z_su * 16); 0 = no depth. Reaches 4095 su.
FLOOR_W, FLOOR_H = 640, 360
FLOOR_CLIP = 0.5
MIN_OBS_FLOOR = 5                   # a floor-map pixel needs this many real frames behind its median
POSTER_AT = 0.4
GOP = 12                            # the derived videos get a keyframe at least every 12 frames (half a second): scrubbing and capture seek cheaply
INTRINSIC_KEYS = ("fx", "fy", "cx", "cy")
FLOOR_TOLERANCE = 0.02              # the floor map must reproduce the recording's noise floor to within this share
PNG16_NOTE = "PNG16 grey; decode with a 16-bit PNG decoder (e.g. fast-png), not canvas"
# Everything clip_assets returns: clips.json takes these from the block, and a partial rebuild keeps every one of them for
# the clips it does not rebuild (a shorter list let a capped clip's untrusted travel and path come back), and refuses to
# keep an old block that lacks any of them (`main`: run a full rebuild).
BLOCK_KEYS = ("assets", "relief", "unverifiable_from", "unverifiable_reason", "trusted_frames", "path", "yaw_deg", "travel",
              "wall_frame", "untrusted", "tracks", "icp", "path_disagreement", "path_disagreement_frame", "provenance",
              "prompt_text", "seed", "moving_track")
CONTENT_TYPES = {".mp4": "video/mp4", ".png": "image/png", ".jpg": "image/jpeg", ".json": "application/json"}


def assets_dir() -> Path:
    return runs_dir() / "assets"


def _json(path: Path, obj, indent: int = 1) -> None:
    from dive import _strict
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_strict(obj), indent=indent, allow_nan=False) + "\n")


# ---- video -----------------------------------------------------------------------------------------

class VideoWriter:
    """BGR uint8 frames, one at a time -> H.264 mp4 (yuv420p, even sizes only, +faststart for the web). Nothing is kept:
    a 10 s dive's heat and real frames are never all in memory."""

    def __init__(self, path, fps: float = 24.0, crf: int = 20):
        self.path, self.fps, self.crf, self.n = Path(path), fps, crf, 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._c, self._s = av.open(str(self.path), "w", options={"movflags": "+faststart"}), None

    def write(self, f: np.ndarray) -> None:
        if self._s is None:
            h, w = f.shape[:2]
            self._s = self._c.add_stream("libx264", rate=Fraction(self.fps).limit_denominator(1000))
            self._s.width, self._s.height, self._s.pix_fmt = w, h, "yuv420p"
            self._s.options = {"crf": str(self.crf), "preset": "medium", "g": str(GOP), "keyint_min": "1"}
        for pkt in self._s.encode(av.VideoFrame.from_ndarray(np.ascontiguousarray(f), format="bgr24")):
            self._c.mux(pkt)
        self.n += 1

    def close(self) -> None:
        if self._c is None:
            return
        if self._s is not None:
            for pkt in self._s.encode():
                self._c.mux(pkt)
        self._c.close()
        self._c = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def encode_video(path: Path, frames, fps: float = 24.0, crf: int = 20) -> int:
    """BGR uint8 frames (any iterable) -> H.264 mp4. Returns the count."""
    with VideoWriter(path, fps, crf) as w:
        for f in frames:
            w.write(f)
    return w.n


def iter_video(path):
    """A video's frames as BGR uint8, one at a time (dive.read_video keeps them all)."""
    with av.open(str(path)) as c:
        for f in c.decode(video=0):
            yield f.to_ndarray(format="bgr24")


# ---- relief atlases ----------------------------------------------------------------------------------

def down_masked(a: np.ndarray, ok: np.ndarray, w: int, h: int) -> tuple[np.ndarray, np.ndarray]:
    """Area-average the valid values of `a` onto a w x h grid: (values, valid), NaN/False where under half is valid."""
    v = np.where(ok, a, 0.0).astype(np.float32)
    m = ok.astype(np.float32)
    sv = cv2.resize(v, (w, h), interpolation=cv2.INTER_AREA)
    sm = cv2.resize(m, (w, h), interpolation=cv2.INTER_AREA)
    good = sm > 0.5
    out = np.full((h, w), np.nan, np.float32)
    out[good] = sv[good] / sm[good]
    return out, good


def depth_cell(disp: np.ndarray, fxb: float) -> np.ndarray:
    """Disparity (full-resolution px, any grid, NaN or <= 0 invalid) -> one 160 x 90 uint16 cell of depth in su x 16."""
    ok = np.isfinite(disp) & (disp > 0)
    d, good = down_masked(disp, ok, CELL_W, CELL_H)
    z = np.where(good, fxb / np.where(good, d, 1.0), 0.0)
    return np.clip(np.rint(z * Z_SCALE), 0, 65535).astype(np.uint16)


def pack_atlas(cells: list[np.ndarray]) -> np.ndarray:
    """Cells in frame order, COLS per row, left to right, top to bottom. 121 frames: 11 x 11; 241 frames: 11 x 22."""
    rows = -(-len(cells) // COLS)
    out = np.zeros((rows * CELL_H, COLS * CELL_W), np.uint16)
    for i, c in enumerate(cells):
        r, k = divmod(i, COLS)
        out[r * CELL_H:(r + 1) * CELL_H, k * CELL_W:(k + 1) * CELL_W] = c
    return out


def relief_intrinsics(tank: Tank, box) -> dict:
    """The relief cell's pinhole intrinsics (pixel centres at integer coordinates, as the calibration has them): the real camera's
    through the mapping box onto the 160 x 90 cell. The page reads them, so the principal point (52 px right of the real frame's
    centre) is never taken as the cell's centre."""
    k = tank.k_grid(tuple(box), CELL_W, CELL_H)
    return {"fx": float(k.fx), "fy": float(k.fy), "cx": float(k.cx), "cy": float(k.cy)}


def stale_keys(block: dict) -> list[str]:
    """What a kept clip block lacks that a partial rebuild needs: any BLOCK_KEYS key, and the relief block's intrinsics."""
    return [k for k in BLOCK_KEYS if k not in block] + [f"relief.{k}" for k in INTRINSIC_KEYS if k not in block.get("relief", {})]


def relief_meta(n_frames: int) -> dict:
    return {"cols": COLS, "rows": -(-n_frames // COLS), "cell": [CELL_W, CELL_H], "frames": n_frames,
            "depth_scale": Z_SCALE, "unit": "su", "invalid": 0, "encoding": PNG16_NOTE}


def write_png16(path: Path, img: np.ndarray) -> None:
    assert img.dtype == np.uint16
    path.parent.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(str(path), img)


# ---- the plan view -----------------------------------------------------------------------------------

def fill_box(tank: Tank) -> tuple[float, float, float, float]:
    """The whole real frame as a box (2208 x 1242 for the real tanks): the box over which the map is the tank."""
    return (0.0, 0.0, float(tank.k_real.width), float(tank.k_real.height))


def tank_profile(tank: Tank, band: tuple[float, float] = (0.4, 0.6), step: int = 8) -> list[list[float]]:
    """The measured tank seen from above: for every `step`th column, the median depth over a band of rows around
    mid-height, as [X, Z] in su (X right of the optical axis, Z forward). Columns with under a third valid are skipped."""
    w, h = tank.work
    d, ok = tank.on_grid(fill_box(tank), w, h)
    k = tank.k_grid(fill_box(tank), w, h)
    r0, r1 = int(band[0] * h), int(band[1] * h)
    out = []
    for u in range(0, w, step):
        col, good = d[r0:r1, u], ok[r0:r1, u]
        if good.mean() < 1 / 3:
            continue
        z = float(np.median(tank.fxb / col[good]))
        out.append([round((u - k.cx) * z / k.fx, 1), round(z, 1)])
    return out


def trusted_end(entry: dict) -> tuple[int | None, str | None]:
    """(first unverifiable frame, why): the earlier of the path being lost and the recording's travel cap."""
    cand = [(entry.get("first_capped_frame"), "travel cap"), (entry.get("lost_from"), "path lost")]
    cand = [(f, why) for f, why in cand if f is not None]
    return min(cand, key=lambda c: c[0]) if cand else (None, None)


# ---- one clip ----------------------------------------------------------------------------------------

def _paths(cid: str) -> dict[str, Path]:
    base = assets_dir() / "clips" / cid
    return {n: base / n for n in ("gen.mp4", "heat.mp4", "real.mp4", "poster.jpg", "poster_heat.jpg", "relief.png",
                                  "tank_relief.png", "path.json")}


def real_color(rd) -> np.ndarray:
    """The tank rebuilt from stereo, as the real pane draws it: the renderer's colour, with every pixel no triangle covers
    in the one flat grey (heat.GREY_RGB) that frames past the cap get too, not the renderer's own grey."""
    out = rd.color.copy()
    out[~rd.seen] = heat.GREY_RGB[::-1]
    return out


def drawn_residual(fp: dict, g: np.ndarray, mv: np.ndarray, fit: AffineFit, fxb: float) -> np.ndarray:
    """The residual the heat draws: dive.frame_products' (verified pixels only, NaN on a tracked moving object) plus, over the
    tracked pixels, the same frozen-fit residual wherever the render has a surface and the generated inverse depth `g` is
    finite (call 69). Nothing else changes: a pixel the render never saw stays NaN (hatched), track or not. The track is
    still out of the pose and out of D, because dive.py never sees this."""
    rd = fp["render"]
    r = fp["residual"].copy()
    m = mv & rd.seen & np.isfinite(g)
    r[m] = rel_residual(fit.apply(g), rd.inv_depth * fxb)[m]
    return r


def _rows(path: Path, clip: str) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for t in path.read_text().splitlines():
        try:
            r = json.loads(t)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("clip") == clip:
            rows.append(r)
    return rows


def logged_seed(spec) -> int:
    """The seed the clip's current take was made with, from the logs: Wan's own runs/wan22/seeds.jsonl, else the last logged
    retake (runs/retakes.jsonl), else the clip's first seed (Gen-4.5 takes are sent `seed_for(spec)`, a pure function)."""
    runs = runs_dir()
    rows = _rows(runs / "wan22" / "seeds.jsonl", spec.id) if spec.engine == "wan22" else []
    rows = rows or _rows(clipmod.retakes_path(), spec.id)
    return int(rows[-1]["seed"]) if rows else clipmod.seed_for(spec)


def _null_from(d: dict, T: int, n: int) -> dict:
    """A diagnostics dict with every per-frame list set to null from frame T on (scalars such as lost_from stay)."""
    return {k: (v[:T] + [None] * (n - T) if isinstance(v, list) and len(v) == n else v) for k, v in d.items()}


def clip_assets(cid: str, tank: Tank) -> dict:
    """Write one clip's assets from runs/dive/<cid>.json|npz, its mp4, its depth npz and its mapping box.
    Returns the clip's block (the BLOCK_KEYS: `assets` paths are relative to runs/assets/) for clips.json.

    Streams: the video is decoded, drawn and encoded a frame at a time (heat.mp4 and real.mp4 are written as the frames
    come), and the depth is held as float32 (exact for the float16 file; each frame is widened to float64 for the maths),
    so a 10 s dive never holds every frame of anything."""
    runs = runs_dir()
    spec = parse_clip_id(cid)
    entry = json.loads((runs / "dive" / f"{cid}.json").read_text())
    arr = np.load(runs / "dive" / f"{cid}.npz")
    box = tuple(json.loads((runs / "mapping" / f"{cid}.json").read_text())["box"])
    fit = AffineFit(**entry["fit"])
    n, fps = entry["n_frames"], float(entry["fps"])
    w, h = entry["grid"]
    dz = np.load(clipmod.depth_path(spec))
    g = dz["inv"].astype(np.float32)
    packed = dz["moving"] if "moving" in dz.files else None
    assert len(g) == n, (cid, len(g), n)
    k = tank.k_grid(box, w, h)
    T, why = trusted_end(entry)
    stop = n if T is None else T
    poses = [Pose(arr["R"][i], arr["C"][i], 1.0) for i in range(n)]
    P = _paths(cid)
    grey = np.full((h, w, 3), heat.GREY_RGB[::-1], np.uint8)
    cells, moving_track = [], []
    poster_i = int(POSTER_AT * (n - 1))
    poster = poster_heat = None
    count = 0
    with VideoWriter(P["heat.mp4"], fps) as heat_out, VideoWriter(P["real.mp4"], fps) as real_out:
        for i, frame in enumerate(iter_video(clipmod.video_path(spec))):
            assert i < n and frame.shape[:2] == (h, w), (cid, i, frame.shape)
            if i < stop:
                gi = g[i].astype(np.float64)
                mv = np.unpackbits(packed[i], axis=-1, count=w).astype(bool) if packed is not None else np.zeros((h, w), bool)
                fp = frame_products(tank, k, gi, mv, fit, poses[i])
                hf = heat.heat_overlay(frame, drawn_residual(fp, gi, mv, fit, tank.fxb), track=mv)
                rf = real_color(fp["render"])
                cells.append(depth_cell(fit.apply(gi), tank.fxb))
                moving_track.append(bool(mv.any()))
            else:
                hf, rf = heat.grey_frame(frame), grey
                cells.append(np.zeros((CELL_H, CELL_W), np.uint16))
                moving_track.append(None)
            heat_out.write(hf)
            real_out.write(rf)
            if i == poster_i:
                poster, poster_heat = frame, hf
            count += 1
    assert count == n, (cid, count, n)
    src_sha = sha256_file(clipmod.video_path(spec))
    P["gen.mp4"].parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(clipmod.video_path(spec), P["gen.mp4"])           # the engine's own bytes
    assert sha256_file(P["gen.mp4"]) == src_sha, f"{cid}: gen.mp4 is not a byte copy of the engine's file"
    for name, img in (("poster.jpg", poster), ("poster_heat.jpg", poster_heat)):
        s = 640 / w
        assert cv2.imwrite(str(P[name]), cv2.resize(img, (640, int(round(h * s))), interpolation=cv2.INTER_AREA),
                           [cv2.IMWRITE_JPEG_QUALITY, 82])
    write_png16(P["relief.png"], pack_atlas(cells))
    write_png16(P["tank_relief.png"], depth_cell(tank.on_grid(box, w, h)[0], tank.fxb))
    C = arr["C"]
    # Past the trusted range nothing is a measurement: the points are null, and the clip's travel and wall frame are
    # recomputed from the trusted frames only (the originals are kept under `untrusted`, marked, never as the numbers).
    # The per-frame tracks and icp arrays and the path disagreement describe the untrusted path too: null from there on.
    xs, zs = C[:, 0].round(2).tolist(), C[:, 2].round(2).tolist()
    path, yaw, travel, wall, untrusted = entry["path"], entry["yaw_deg"], entry["travel"], entry["wall_frame"], {}
    tracks, icp = entry["tracks"], entry["icp"]
    pdis, pdis_frame = entry["path_disagreement"], entry["path_disagreement_frame"]
    if T is not None:
        xs[T:], zs[T:] = [None] * (n - T), [None] * (n - T)
        path, yaw = path[:T] + [[None, None, None]] * (n - T), yaw[:T] + [None] * (n - T)
        untrusted = {"travel": travel, "wall_frame": wall}
        travel = float(np.linalg.norm(C[T - 1] - C[0])) if T > 0 else 0.0
        wall = None if wall is not None and wall >= T else wall
        tracks, icp = _null_from(tracks, T, n), _null_from(icp, T, n)
        pdis, pdis_frame = None, None
    _json(P["path.json"], {"clip": cid, "fps": fps, "x": xs, "z": zs, "yaw_deg": yaw, "lost_from": entry["lost_from"],
                           "capped_from": entry.get("first_capped_frame"), "wall_frame": wall, "far_end": entry["far_end"],
                           "far_end_valid": entry["far_end_valid"], "unverifiable_from": T, "trusted_frames": stop,
                           "primary_path": entry["primary_path"], "unit": "su"})
    rel = lambda p: str(p.relative_to(assets_dir()))      # noqa: E731
    provenance = {"gen": "engine original, byte copy", "heat": "derived", "real": "derived", "poster": "derived",
                  "poster_heat": "derived", "relief": "derived", "tank_relief": "derived", "path": "derived",
                  "source_sha256": src_sha}
    block = {"assets": {n_.rsplit(".", 1)[0]: rel(p) for n_, p in P.items()},
             "relief": {**relief_meta(n), "box": [float(x) for x in box], "real_size": [tank.k_real.width, tank.k_real.height],
                        **relief_intrinsics(tank, box)},
             "unverifiable_from": T, "unverifiable_reason": why, "trusted_frames": stop,
             "path": path, "yaw_deg": yaw, "travel": travel, "wall_frame": wall, "untrusted": untrusted,
             "tracks": tracks, "icp": icp, "path_disagreement": pdis, "path_disagreement_frame": pdis_frame,
             "provenance": provenance, "prompt_text": PROMPTS[spec.prompt], "seed": logged_seed(spec),
             "moving_track": moving_track}
    assert set(block) == set(BLOCK_KEYS)
    return block


# ---- one recording -----------------------------------------------------------------------------------

def floor_map(d: np.ndarray, ok: np.ndarray, g: np.ndarray, fits: list[tuple[float, float]],
              excl: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, float]:
    """DA3's median |relative error| per pixel over the real frames: (map, n_obs, floor_check). d is the tank's disparity
    (h, w), g the frames' inverse depth (n, h, w), fits each frame's (s, t) from the noise-floor run, excl (n, h, w) the
    frames' bottle-and-hand masks. A pixel with fewer than MIN_OBS_FLOOR observations is NaN. Display only (call 48).

    `floor_check` is the noise floor's own statistic from the same errors: the median over frames of each frame's mean
    error over its valid pixels. It is not the map's median (the median over pixels of each pixel's own median error,
    a smaller number): the recording's floor is this one, and `recording_assets` holds the two to within 2 %."""
    n = len(g)
    stack = np.full((n, *d.shape), np.nan, np.float32)
    for i in range(n):
        s, t = fits[i]
        M = ok & np.isfinite(g[i]) & (d > 0) & (True if excl is None else ~excl[i])
        r = np.abs(s * g[i] - d + t) / np.where(d > 0, d, 1.0)
        stack[i] = np.where(M, r, np.nan)
    nobs = np.isfinite(stack).sum(axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(stack, axis=0).astype(np.float32)
        per_frame = np.nanmean(stack, axis=(1, 2), dtype=np.float64)
        floor_check = float(np.nanmedian(per_frame)) if np.isfinite(per_frame).any() else float("nan")
    med[nobs < MIN_OBS_FLOOR] = np.nan
    return med, nobs, floor_check


def floor_png(m: np.ndarray) -> np.ndarray:
    """stored = 1 + round(min(v, 0.5) / 0.5 * 65534); 0 = unobserved."""
    ok = np.isfinite(m)
    v = np.where(ok, np.minimum(m, FLOOR_CLIP) / FLOOR_CLIP, 0.0)
    return np.where(ok, 1 + np.rint(v * 65534), 0).astype(np.uint16)


def floor_preview(m: np.ndarray) -> np.ndarray:
    """The map coloured on its own violet ramp (heat.FLOOR_RAMP: it carries no sign, so it must not look like the
    residual's), hatched where unobserved."""
    ok = np.isfinite(m)
    t = np.where(ok, np.minimum(m, FLOOR_CLIP) / FLOOR_CLIP, 0.0)
    rgb = np.where(ok[..., None], heat.ramp(heat.FLOOR_RAMP, t), heat.hatch(*m.shape)[..., None].astype(np.float64))
    return np.clip(np.rint(rgb), 0, 255).astype(np.uint8)[..., ::-1]


def load_floor_inputs(rec, tank: Tank):
    """The real frames' inverse depth, fits and exclusion masks on the 640 x 360 floor-map grid (cli.py floor's inputs)."""
    from mapping import warp_mask
    from realside import exclusion_mask, unpack_masks
    runs = runs_dir()
    z = np.load(runs / "da3" / "floor" / f"{rec.name}.npz")
    fl = json.loads((runs / "floor" / f"{rec.name}.json").read_text())
    m = np.load(runs / "masks" / f"{rec.name}.npz")
    bottle, hand = unpack_masks(m["bottle"], int(m["width"])), unpack_masks(m["hand"], int(m["width"]))
    half = (0.0, 0.0, float(bottle.shape[2]), float(bottle.shape[1]))
    d, ok = tank.on_grid(fill_box(tank), FLOOR_W, FLOOR_H)
    frames = z["frames"].tolist()
    g = np.stack([cv2.resize(x.astype(np.float32), (FLOOR_W, FLOOR_H), interpolation=cv2.INTER_AREA) for x in z["inv"]])
    excl = np.stack([warp_mask(exclusion_mask(bottle[f], hand[f], 0.5), half, FLOOR_W, FLOOR_H) for f in frames])
    return d, ok, g, [(f["s"], f["t"]) for f in fl["fits"]], excl


def _recording_floor(rec) -> float:
    p = runs_dir() / "floor" / f"{rec.name}.json"
    if not p.exists():
        raise RuntimeError(f"{p} is missing: run `uv run python cli.py floor` (task 1.5) first")
    return float(json.loads(p.read_text())["floor"])


def _selftest_numbers(rec) -> dict:
    """The self-test's null-dream numbers for this recording (the page's baseline for D): runs/selftest/report.json."""
    p = runs_dir() / "selftest" / "report.json"
    if not p.exists():
        raise RuntimeError(f"{p} is missing: run `uv run python cli.py selftest` (task 1.7) first")
    rep = json.loads(p.read_text())
    if rec.condition not in rep:
        raise RuntimeError(f"{p} has no entry for '{rec.condition}' (it has: {', '.join(sorted(rep))}): rerun `cli.py selftest`")
    r = rep[rec.condition]
    return {"null_dream_D": r["null_dream_D"], "null_dream_D_float": r["null_dream_D_float"]}


def recording_assets(rec, tank: Tank, floor_inputs=None) -> dict:
    """Write one recording's assets; returns its block for clips.json. Needs the noise floor run (runs/floor/<name>.json)
    and the self-test's report, and refuses a floor map that does not reproduce the recording's floor to within 2 %."""
    floor = _recording_floor(rec)
    null = _selftest_numbers(rec)
    base = assets_dir() / "recordings" / rec.condition
    rel = lambda p: str(p.relative_to(assets_dir()))      # noqa: E731
    base.mkdir(parents=True, exist_ok=True)
    start = cv2.resize(cv2.imread(str(rec.left_path(rec.start_frame))), tank.work, interpolation=cv2.INTER_AREA)
    assert cv2.imwrite(str(base / "start.jpg"), start, [cv2.IMWRITE_JPEG_QUALITY, 88])
    write_png16(base / "tank_relief.png", depth_cell(tank.disp_half * 2.0, tank.fxb))
    fm, nobs, floor_check = floor_map(*(floor_inputs if floor_inputs is not None else load_floor_inputs(rec, tank)))
    if not abs(floor_check - floor) <= FLOOR_TOLERANCE * abs(floor) + 1e-6:     # + 1e-6: float noise when a test's floor is 0
        raise AssertionError(f"{rec.condition}: the floor map's own check, the median over frames of the per-frame mean "
                             f"error, is {floor_check:.4f}, not within {FLOOR_TOLERANCE:.0%} of the recording's floor "
                             f"{floor:.4f} (runs/floor/{rec.name}.json): the map is not the floor's error")
    write_png16(base / "floor_map.png", floor_png(fm))
    assert cv2.imwrite(str(base / "floor_preview.jpg"), floor_preview(fm), [cv2.IMWRITE_JPEG_QUALITY, 88])
    _json(base / "plan.json", {"condition": rec.condition, "far_end": tank.far_end, "profile": tank_profile(tank),
                               "unit": "su", "trusted_travel_su": TRUSTED_TRAVEL_SU.get(rec.condition)})
    obs = np.isfinite(fm)
    return {"floor": tank.floor, "far_end": tank.far_end, "trusted_travel_su": TRUSTED_TRAVEL_SU.get(rec.condition),
            "start": rel(base / "start.jpg"), "plan": rel(base / "plan.json"), **null,
            "tank_relief": {"png": rel(base / "tank_relief.png"), "cell": [CELL_W, CELL_H], "depth_scale": Z_SCALE,
                            "unit": "su", "invalid": 0, "encoding": PNG16_NOTE},
            "floor_map": {"png": rel(base / "floor_map.png"), "preview": rel(base / "floor_preview.jpg"),
                          "grid": [FLOOR_W, FLOOR_H], "clip": FLOOR_CLIP, "min_obs": MIN_OBS_FLOOR,
                          "stored": "1 + round(min(v, 0.5) / 0.5 * 65534); 0 = unobserved", "encoding": PNG16_NOTE,
                          "display_only": True, "observed_share": float(obs.mean()),
                          "pixel_median": float(np.nanmedian(fm)) if obs.any() else None,
                          "pixel_median_note": "the median over pixels of each pixel's own median error: a picture of "
                                               "where DA3 errs, not the floor (the floor is floor_check: the median over "
                                               "frames of the per-frame mean error)",
                          "floor_check": floor_check}}


# ---- clips.json and the manifest ---------------------------------------------------------------------

def build_clips_json(blocks: dict[str, dict], recordings_blocks: dict[str, dict]) -> dict:
    """runs/clips.json (sub-plan A's entries) + each clip's assets block + the recordings + the palette."""
    src = json.loads((runs_dir() / "clips.json").read_text())["clips"]
    out = []
    for e in src:
        b = blocks.get(e["clip"])
        if b is not None:
            out.append({**e, **b, "recording_key": e["condition"]})
    doc = {"version": ASSET_VERSION, "unit": "uncorrected stereo units (su)", "heat": heat.palette_json(),
           "relief": {"cols": COLS, "cell": [CELL_W, CELL_H], "depth_scale": Z_SCALE},
           "recordings": recordings_blocks, "clips": sorted(out, key=lambda e: e["clip"])}
    _json(assets_dir() / "clips.json", doc)
    return doc


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def referenced_files(doc: dict) -> dict[str, str]:
    """{path under runs/assets/: 'original' | 'derived'} for clips.json and every file it names: each clip's assets (the
    `gen` one is the engine's own file when the clip's provenance says so) and each recording's reference files."""
    ref = {"clips.json": "derived"}
    for c in doc["clips"]:
        prov = c.get("provenance") or {}
        for name, rel in c.get("assets", {}).items():
            ref[rel] = "original" if str(prov.get(name, "")).startswith("engine original") else "derived"
    for r in doc["recordings"].values():
        for rel in (r.get("start"), r.get("plan"), (r.get("tank_relief") or {}).get("png"),
                    (r.get("floor_map") or {}).get("png"), (r.get("floor_map") or {}).get("preview")):
            if rel:
                ref[rel] = "derived"
    return ref


def media_manifest() -> dict:
    """media_manifest.json and MEDIA.md for the files runs/assets/clips.json references (and clips.json itself): a
    referenced file that is missing, or an engine original whose bytes no longer match the clip's `source_sha256`, fails;
    a file under runs/assets that nothing references is warned about (and listed under `unreferenced`), not shipped."""
    root = assets_dir()
    if not (root / "clips.json").exists():
        raise FileNotFoundError(f"{root / 'clips.json'} is missing: build the assets first")
    doc = json.loads((root / "clips.json").read_text())
    ref = referenced_files(doc)
    want = {c["assets"]["gen"]: (c.get("provenance") or {}).get("source_sha256") for c in doc["clips"]
            if "gen" in c.get("assets", {})}
    items = []
    for rel in sorted(ref):
        p = root / rel
        if not p.is_file():
            raise FileNotFoundError(f"clips.json references {rel}, which is not under {root}")
        sha = sha256_file(p)
        if want.get(rel) and ref[rel] == "original" and sha != want[rel]:
            raise RuntimeError(f"{rel}: sha256 {sha} is not the clip's source_sha256 {want[rel]}: "
                               "the bare clip must be the engine's file, byte for byte")
        items.append({"path": rel, "key": PREFIX + rel, "bytes": p.stat().st_size, "sha256": sha,
                      "content_type": CONTENT_TYPES.get(p.suffix, "application/octet-stream"), "origin": ref[rel]})
    on_disk = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()} - {"media_manifest.json", "MEDIA.md"}
    unreferenced = sorted(on_disk - set(ref))
    if unreferenced:
        warnings.warn(f"{len(unreferenced)} unreferenced file(s) under {root} are not in the manifest: "
                      + ", ".join(unreferenced), UserWarning, stacklevel=2)
    man = {"prefix": PREFIX, "cache_control": CACHE_CONTROL, "public": "https://media.studionephele.com/", "items": items,
           "unreferenced": unreferenced}
    _json(root / "media_manifest.json", man)
    lines = ["# MEDIA.md: every R2 object under `divetwin/v1/`", "",
             f"Immutable (`{CACHE_CONTROL}`). A changed file goes to a new version prefix. Built by `assets.py`; "
             "uploaded at publish time with `tools/media.py` (task 6.2). `origin`: `original` is the engine's own file, "
             "byte for byte (its sha256 is the clip's `source_sha256`); `derived` is made here.", "",
             "<!-- r2-manifest:begin -->", "| key | bytes | sha256 | origin |", "|---|---|---|---|"]
    lines += [f"| `{i['key']}` | {i['bytes']} | `{i['sha256']}` | {i['origin']} |" for i in items]
    lines += ["<!-- r2-manifest:end -->", ""]
    (root / "MEDIA.md").write_text("\n".join(lines))
    return man


def main(clip_ids: list[str] | None = None, recordings_only: bool = False) -> None:
    """Build assets for the clips in runs/clips.json (or the named ones) and every recording they use. An id that is not in
    runs/clips.json is refused before anything is built. A partial run (named clips, or --recordings-only) keeps the other
    clips' blocks from the clips.json already there, every key of them: an old block that lacks any BLOCK_KEYS key is refused
    (before anything is built), because a missing key would let untrusted arrays through for a capped clip."""
    from dive import load_tank
    from recordings import recordings
    runs = runs_dir()
    entries = json.loads((runs / "clips.json").read_text())["clips"]
    unknown = [c for c in (clip_ids or []) if c not in {e["clip"] for e in entries}]
    if unknown:
        raise SystemExit(f"unknown clip id(s), not in runs/clips.json: {', '.join(unknown)}")
    ids = [e["clip"] for e in entries if not clip_ids or e["clip"] in clip_ids]
    prev = assets_dir() / "clips.json"
    if prev.exists() and (clip_ids or recordings_only):
        stale = {c["clip"]: stale_keys(c) for c in json.loads(prev.read_text())["clips"]
                 if recordings_only or c["clip"] not in ids}       # recordings-only rebuilds no clip: all are kept
        stale = {cid: miss for cid, miss in stale.items() if miss}
        if stale:
            raise SystemExit("a partial rebuild keeps the other clips' blocks as they are, and these lack keys it needs ("
                             + "; ".join(f"{cid}: {', '.join(miss)}" for cid, miss in sorted(stale.items()))
                             + f"): {prev} is from an older build. Run a full rebuild (`cli.py assets` with no clip ids).")
    conds = sorted({e["condition"] for e in entries if e["clip"] in ids})
    tanks, rblocks, cblocks = {}, {}, {}
    for cond in conds:
        rec = recordings()[cond]
        tanks[cond] = load_tank(rec, runs)
        rblocks[cond] = recording_assets(rec, tanks[cond])
        print(f"{cond}: start, tank relief, floor map, plan")
    if not recordings_only:
        for e in entries:
            if e["clip"] in ids:
                cblocks[e["clip"]] = clip_assets(e["clip"], tanks[e["condition"]])
                print(f"{e['clip']}: heat, real, gen, posters, relief, path"
                      + (f"  (unverifiable from frame {cblocks[e['clip']]['unverifiable_from']}: "
                         f"{cblocks[e['clip']]['unverifiable_reason']})" if cblocks[e['clip']]["unverifiable_from"] is not None else ""))
    if prev.exists() and (clip_ids or recordings_only):       # a partial run keeps the clips it did not build, whole
        old = json.loads(prev.read_text())
        for c in old["clips"]:
            if c["clip"] not in cblocks:
                cblocks[c["clip"]] = {k: c[k] for k in BLOCK_KEYS}
        rblocks = {**old["recordings"], **rblocks}
    build_clips_json(cblocks, rblocks)
    man = media_manifest()
    print(f"clips.json: {len(cblocks)} clips, {len(rblocks)} recordings; manifest: {len(man['items'])} files, "
          f"{sum(i['bytes'] for i in man['items']) / 1e6:.1f} MB (nothing uploaded)")
