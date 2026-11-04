"""Round 1 (the probes): a contact sheet for the eye and a free, local cross-check of camera motion.

The eye decides. The numbers are a logged cross-check, and this module never rewrites a prompt: it reports
what each probe did and how many recordings moved forward per prompt. Kill rule 2 is read in reverse for
prompt D: if D's probes don't move the camera forward on 3 of 5 recordings, Aaron rewrites D once (house
wording); that is a decision for Gate P, never for this code.

Two independent readings of "did the view magnify (the camera moved forward)", both about the frame centre:
  * sift  - SIFT matches between the first and the last frame, a similarity transform fitted by RANSAC;
            scale > 1 means the last frame is the first one magnified. Null when fewer than MIN_INLIERS agree.
  * flow  - dense Farneback flow between consecutive frames, a zoom plus shift fitted to each step, the
            zooms multiplied along the clip (robust where SIFT finds nothing, such as turbid water).
plus the mean frame-to-frame change (grey levels), and the first-to-last change."""
from __future__ import annotations

import json
from pathlib import Path

import av
import cv2
import numpy as np

import clips
from clips import ClipSpec
from recordings import RECORDING_NAMES, runs_dir

SCALE_FORWARD, SCALE_BACK = 1.03, 0.97   # reading bands for the report only; a rule is not built on them
SHIFT_MOVED = 0.02        # a centre shift of this fraction of the frame width also counts as "moved" (B and N, kill rule 2)
MIN_INLIERS = 15
SIFT_W = 640                              # SIFT runs on frames shrunk to this width
FLOW_W = 320
GRAD_MIN = 3.0             # grey levels a pixel (320 px wide, 8 bit): below it a pixel carries no texture to track
MIN_TEXTURE = 0.10         # the flow reading needs this mean share of textured pixels
MAX_RMS_PX = 0.6           # ... and a zoom-plus-shift fit that leaves no more than this residual (px at 320 wide)


def read_frames(path) -> list[np.ndarray]:
    with av.open(str(path)) as c:
        return [f.to_ndarray(format="bgr24") for f in c.decode(video=0)]


def _gray(img: np.ndarray, width: int) -> np.ndarray:
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    h, w = g.shape
    return cv2.resize(g, (width, int(round(h * width / w))), interpolation=cv2.INTER_AREA)


def sift_similarity(first: np.ndarray, last: np.ndarray) -> dict:
    """{'scale', 'rotation_deg', 'shift_frac', 'inliers', 'matches'}: the similarity transform first -> last,
    scale and rotation about the frame centre, shift of the centre as a fraction of the frame width."""
    a, b = _gray(first, SIFT_W), _gray(last, SIFT_W)
    out = {"scale": None, "rotation_deg": None, "shift_frac": None, "inliers": 0, "matches": 0}
    sift = cv2.SIFT_create(nfeatures=3000)
    ka, da = sift.detectAndCompute(a, None)
    kb, db = sift.detectAndCompute(b, None)
    if da is None or db is None or len(ka) < 8 or len(kb) < 8:
        return out
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(da, db, k=2)
    good = [m for m, n in (p for p in pairs if len(p) == 2) if m.distance < 0.75 * n.distance]
    out["matches"] = len(good)
    if len(good) < MIN_INLIERS:
        return out
    pa = np.float32([ka[m.queryIdx].pt for m in good])
    pb = np.float32([kb[m.trainIdx].pt for m in good])
    M, inl = cv2.estimateAffinePartial2D(pa, pb, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    if M is None or inl is None:
        return out
    n_in = int(inl.sum())
    out["inliers"] = n_in
    if n_in < MIN_INLIERS:
        return out
    h, w = a.shape
    c = np.array([w / 2, h / 2])
    c2 = M[:, :2] @ c + M[:, 2]
    out.update(scale=float(np.hypot(M[0, 0], M[1, 0])), rotation_deg=float(np.degrees(np.arctan2(M[1, 0], M[0, 0]))),
               shift_frac=float(np.linalg.norm(c2 - c) / w))
    return out


def flow_zoom(frames: list[np.ndarray]) -> dict:
    """Cumulative zoom about the centre from consecutive-frame Farneback flow: {'scale', 'steps', 'rms_px', 'texture'}.

    The fit uses only textured pixels (gradient above GRAD_MIN grey levels a pixel), and the answer is None (unmeasured,
    never "hold") when too few pixels are textured (`texture`, their mean share, under MIN_TEXTURE) or the fit leaves
    a residual above MAX_RMS_PX: turbid or low-contrast water gives flow that is noise, and noise reads as no motion."""
    g = [_gray(f, FLOW_W) for f in frames]
    h, w = g[0].shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    dx_all, dy_all = (xx - (w - 1) / 2).ravel(), (yy - (h - 1) / 2).ravel()
    scale, rms, tex = 1.0, [], []
    for p, q in zip(g[:-1], g[1:]):
        pf = p.astype(np.float32)
        gm = np.hypot(cv2.Sobel(pf, cv2.CV_32F, 1, 0), cv2.Sobel(pf, cv2.CV_32F, 0, 1)).ravel() / 8.0
        m = gm > GRAD_MIN
        tex.append(float(m.mean()))
        if m.sum() < 200:
            continue
        fl = cv2.calcOpticalFlowFarneback(p, q, None, 0.5, 3, 21, 3, 5, 1.1, 0)
        u, v = fl[..., 0].ravel()[m], fl[..., 1].ravel()[m]
        dx, dy, n = dx_all[m], dy_all[m], int(m.sum())
        A = np.zeros((2 * n, 3))
        A[:n, 0], A[:n, 1] = dx, 1.0
        A[n:, 0], A[n:, 2] = dy, 1.0
        y = np.concatenate([u, v])
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        scale *= 1.0 + float(coef[0])
        rms.append(float(np.sqrt(np.mean((A @ coef - y) ** 2))))
    texture = float(np.mean(tex)) if tex else 0.0
    rms_px = float(np.mean(rms)) if rms else None
    ok = texture >= MIN_TEXTURE and rms_px is not None and rms_px <= MAX_RMS_PX
    return {"scale": float(scale) if ok else None, "steps": len(g) - 1, "rms_px": rms_px, "texture": texture}


def mean_change(frames: list[np.ndarray]) -> dict:
    g = [_gray(f, FLOW_W).astype(np.float32) for f in frames]
    step = [float(np.abs(b - a).mean()) for a, b in zip(g[:-1], g[1:])]
    return {"frame_to_frame": float(np.mean(step)) if step else 0.0, "first_to_last": float(np.abs(g[-1] - g[0]).mean())}


def reading(scale: float | None) -> str:
    if scale is None:
        return "unmeasured"
    return "forward" if scale > SCALE_FORWARD else "back" if scale < SCALE_BACK else "hold"


def moved(r: dict) -> bool | None:
    """Did the camera move at all (forward, back or sideways) by either reading? Kill rule 2's own direction for B and N.
    None when nothing could be measured (both readings unmeasured and no SIFT shift): that is not "held"."""
    if (r["sift_reading"] in ("forward", "back") or r["flow_reading"] in ("forward", "back")
            or (r["sift"]["shift_frac"] or 0.0) > SHIFT_MOVED):
        return True
    if r["sift_reading"] == "unmeasured" and r["flow_reading"] == "unmeasured" and r["sift"]["shift_frac"] is None:
        return None
    return False


def probe_numbers(frames: list[np.ndarray]) -> dict:
    s, f = sift_similarity(frames[0], frames[-1]), flow_zoom(frames)
    r = {"frames": len(frames), "sift": s, "flow": f, "change": mean_change(frames),
         "sift_reading": reading(s["scale"]), "flow_reading": reading(f["scale"])}
    r["moved"] = moved(r)
    return r


def build_report(check: bool = True) -> dict:
    """runs/probes.json: per-probe numbers and, per prompt, how many recordings read forward. Reports only."""
    idx = clips.rebuild_probes_index(check)["index"]
    per = {}
    for cid, e in idx.items():
        per[cid] = {"condition": e["condition"], "prompt": e["prompt"], "seed": e["seed"],
                    **probe_numbers(read_frames(e["video"]))}
    summary = {}
    for p in "DBN":
        rows = [v for v in per.values() if v["prompt"] == p]
        summary[p] = {"probes": len(rows),
                      "forward_sift": sum(r["sift_reading"] == "forward" for r in rows),
                      "forward_flow": sum(r["flow_reading"] == "forward" for r in rows),
                      "unmeasured_sift": sum(r["sift_reading"] == "unmeasured" for r in rows),
                      "unmeasured_flow": sum(r["flow_reading"] == "unmeasured" for r in rows),
                      "moved": sum(r["moved"] is True for r in rows),
                      "unmeasured": sum(r["moved"] is None for r in rows)}
    rep = {"bands": {"forward_above": SCALE_FORWARD, "back_below": SCALE_BACK, "min_inliers": MIN_INLIERS},
           "note": "A cross-check for the eye; the contact sheet decides. Kill rule 2: prompt D is read in reverse (fewer than 3 of 5 "
                   "moving forward), B and N in the forward direction (3 or more of 5 moving at all).",
           "summary": summary, "probes": dict(sorted(per.items()))}
    p = runs_dir() / "probes.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=1, allow_nan=False) + "\n")
    return rep


def _label(img: np.ndarray, text: str, y: int = 18) -> None:
    cv2.putText(img, text, (6, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, text, (6, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)


def _num(x) -> str:
    return "-" if x is None else f"{x:.3f}"


def make_sheet(report: dict, path=None, w: int = 352) -> Path:
    """runs/sheets/probes.jpg: a row per recording, a column per prompt (D, B, N); each cell is the probe's first
    and last frame side by side, labelled with the prompt, the seed and both zoom readings."""
    path = Path(path or runs_dir() / "sheets" / "probes.jpg")
    good, _ = clips.scan_clips(check=False)          # an unchecked scan, and never written over the checked probes_index.json
    idx = {s.id: {"video": str(clips.video_path(s))} for s in good if s.kind == "probe"}
    rows = []
    h = None
    for cond in RECORDING_NAMES:
        cells = []
        for p in "DBN":
            cid = ClipSpec(cond, "gen45", p, 2, "probe").id
            if cid in idx:
                try:
                    fr = read_frames(idx[cid]["video"])
                    h = h or int(round(fr[0].shape[0] * w / fr[0].shape[1]))
                    a, b = (cv2.resize(f, (w, h), interpolation=cv2.INTER_AREA) for f in (fr[0], fr[-1]))
                except Exception:                                  # a truncated or corrupt mp4: say so on the sheet
                    cells.append("unreadable")
                    continue
                cell = np.hstack([a, b])
                r = report["probes"].get(cid)
                _label(cell, f"{cond} {p}  first", 18)
                _label(cell[:, w:], "last", 18)
                if r:      # the readings sit on the "last" half, which is the frame they describe
                    _label(cell[:, w:], f"sift {_num(r['sift']['scale'])} {r['sift_reading']}", h - 26)
                    _label(cell[:, w:], f"flow {_num(r['flow']['scale'])} {r['flow_reading']}", h - 8)
            else:
                cell = None
            cells.append(cell)
        rows.append(cells)
    if h is None:
        if not idx:
            raise SystemExit("no probes on disk: nothing to put on a sheet")
        h = int(round(720 * w / 1280))        # every probe is unreadable: the cells still say so, at the engine's 16:9
    blank = np.full((h, 2 * w, 3), 40, np.uint8)
    out = []
    for cond, cells in zip(RECORDING_NAMES, rows):
        row = [c if isinstance(c, np.ndarray) else blank.copy() for c in cells]
        for c, cell in zip(cells, row):
            if not isinstance(c, np.ndarray):
                _label(cell, "missing" if c is None else "unreadable", h // 2)
        out.append(np.hstack(row))
    head = np.full((28, 6 * w, 3), 20, np.uint8)
    for i, p in enumerate("DBN"):
        _label(head[:, 2 * w * i:], f"prompt {p}", 19)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), np.vstack([head] + out), [cv2.IMWRITE_JPEG_QUALITY, 85])
    return path


def contact_sheet(frames: list[np.ndarray], every: int = 12, cols: int = 5, w: int = 256, label: str = "") -> np.ndarray:
    """Every `every`th frame (and always the last), `cols` per row, each labelled with its frame number. For reading a
    clip with the eye: round 2's one-line readings and the hunt's yes-or-no (task 2.6)."""
    idx = sorted(set(range(0, len(frames), every)) | {len(frames) - 1})
    h = int(round(frames[0].shape[0] * w / frames[0].shape[1]))
    tiles = []
    for i in idx:
        t = cv2.resize(frames[i], (w, h), interpolation=cv2.INTER_AREA)
        _label(t, f"{label} f{i}".strip(), 18)
        tiles.append(t)
    while len(tiles) % cols:
        tiles.append(np.full_like(tiles[0], 30))
    return np.vstack([np.hstack(tiles[r:r + cols]) for r in range(0, len(tiles), cols)])
