"""Sub-plan A's commands, one per task step. Run from pipeline/: `uv run python cli.py <command>`.
GPU steps are the Modal entrypoints (modal_stereo.py, modal_depth.py); everything here is local CPU.
Every JSON this file writes is strict (no NaN or Infinity: a non-finite number is written as null)."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from align import huber_affine_fit, rel_residual
from mapping import FILL_1280x720, measure_box, resample, warp_mask
from metrics import abs_rel, noise_floor
from realside import (MIN_OBS, classify_with_ious, exclusion_mask, progress, region_mad, start_and_tail, tail_min_obs,
                      tank_median, unpack_masks, write_png16, xcheck)
from recordings import START_FRAMES, recordings, runs_dir
from units import REAL_W, bottle_depth, epipolar_dy, half_to_full, load_disp, ratio_summary

HALF_BOX = (0.0, 0.0, 1104.0, 621.0)  # the half grid as a box over itself: half -> work grid is a fill
KILL1, KILL4 = 0.25, 0.15
DY_STOP_GAIN, DY_STOP_PAIRS = 0.10, 3  # R2 step 2b stop rule: shifted beats published by > 10 % on 3 of the recordings
DY_MIN_USED = 30  # a recording counts only with at least this many pooled SIFT matches inside valid pixels of both maps
DASH = "—"


# ---- small helpers ----------------------------------------------------------------------------------

def _dump(path: Path, obj, indent: int | None = 2) -> None:
    """Strict JSON to `path`: non-finite numbers become null first, then allow_nan=False makes any that
    slipped through an error. Lists of plain numbers/strings stay on one line."""
    from dive import _strict  # imported late: dive pulls in numba
    text = json.dumps(_strict(obj), indent=indent, allow_nan=False)
    if indent:
        text = re.sub(r"\[\s*([^\[\]{}]*?)\s*\]", lambda m: "[" + re.sub(r"\s*\n\s*", " ", m.group(1)) + "]", text)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text + "\n")


def _fmt(x, spec: str = ".2f", none: str = DASH) -> str:
    """Format a number that may be None or NaN (the clip entry's floats and lists can hold None)."""
    return none if x is None or not np.isfinite(x) else format(x, spec)


def _arr(x) -> np.ndarray:
    """A list that may hold None -> float array (None becomes NaN)."""
    return np.asarray(x, dtype=float)


def _nan_summary(x) -> dict:
    v = _arr(x)
    v = v[np.isfinite(v)]
    return {"median": float(np.median(v)) if v.size else None, "max": float(v.max()) if v.size else None}


def _need(path: Path, hint: str) -> Path:
    if not Path(path).exists():
        sys.exit(f"missing {path}\n  {hint}")
    return Path(path)


def _require_floor(recs) -> None:
    """run_clip refuses a tank without a finite, positive noise floor; say so before any heavy work."""
    for rec in recs:
        p = _need(runs_dir() / "floor" / f"{rec.name}.json",
                  "no noise floor for this recording: run task 1.5 first "
                  "(`uv run modal run modal_depth.py::floor`, then `uv run python cli.py floor`)")
        v = json.loads(p.read_text()).get("floor")
        if v is None or not np.isfinite(v) or v <= 0:
            sys.exit(f"{p}: the noise floor is {v}, not a finite positive number; "
                     "re-run `uv run python cli.py floor` and look at that recording's DA3 frames")


def _refuse_gate_s(recs) -> None:
    """Tank and recon build on the start frame and the tail; a recording that failed Gate S has neither."""
    for cond, rec in recs.items():
        info = rec.start_info
        if info and info.get("gate_s"):
            sys.exit(f"{rec.name} ({cond}): Gate S failed ({info['gate_s']}), so its start frame and tail are not used; "
                     "settle Gate S first (`uv run python cli.py start-frames`, with `--allow-quiet <condition>` only if accepted)")


def _masks(rec):
    z = np.load(_need(runs_dir() / "masks" / f"{rec.name}.npz",
                      "run `uv run modal run modal_depth.py::masks` first (task 1.2)"))
    w = int(z["width"])
    return unpack_masks(z["bottle"], w), unpack_masks(z["hand"], w)


def _sheet(tiles: list[np.ndarray], labels: list[str], cols: int, path: Path, w: int = 552) -> None:
    out = []
    for t, s in zip(tiles, labels):
        im = cv2.resize(t, (w, int(round(t.shape[0] * w / t.shape[1]))), interpolation=cv2.INTER_AREA)
        cv2.putText(im, s, (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        out.append(im)
    while len(out) % cols:
        out.append(np.zeros_like(out[0]))
    rows = [np.hstack(out[i:i + cols]) for i in range(0, len(out), cols)]
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
    print("sheet:", path)


# ---- task 1.2 ---------------------------------------------------------------------------------------

def cmd_calib(_):
    """Question 1's free checks on every recording: epipolar residual and disparity sign on 3 pairs."""
    out = {}
    for cond, rec in recordings().items():
        rows = []
        for f in (rec.matched_frames[0], rec.matched_frames[len(rec.matched_frames) // 2], rec.n_frames - 1):
            L = cv2.imread(str(rec.left_path(f)), cv2.IMREAD_GRAYSCALE)
            R = cv2.imread(str(rec.right_path(f)), cv2.IMREAD_GRAYSCALE)
            rows.append({"frame": f, **epipolar_dy(L, R)})
        out[rec.name] = rows
        print(cond, [(r["frame"], r["n"], round(r.get("median_dy", float("nan")), 2), r.get("frac_dx_pos")) for r in rows])
    _dump(runs_dir() / "calib.json", out)


def cmd_seed_sheet(_):
    """A gridded image of each recording's first matched frame, for drawing the SAM 2 boxes."""
    for cond, rec in recordings().items():
        f = rec.matched_frames[0]
        im = cv2.imread(str(rec.left_path(f)))
        for x in range(0, 2208, 100):
            cv2.line(im, (x, 0), (x, 1241), (0, 255, 255) if x % 500 == 0 else (0, 160, 160), 1)
            cv2.putText(im, str(x), (x + 2, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        for y in range(0, 1242, 100):
            cv2.line(im, (0, y), (2207, y), (0, 255, 255) if y % 500 == 0 else (0, 160, 160), 1)
            cv2.putText(im, str(y), (2, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        p = runs_dir() / "sheets" / f"seed_{cond}_{f:06d}.jpg"
        p.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(p), im, [cv2.IMWRITE_JPEG_QUALITY, 85])
        print(cond, "frame", f, "->", p)


def gate_s_reason(info: dict, allow_quiet: bool, cond: str = "<condition>") -> str | None:
    """Why this recording fails Gate S, or None if it has an acceptable start frame.

    A start frame counts only with a hand-free tail behind it (`tail` is None when the recording ends in a
    hand or a moving bottle: a start found then can be from before the hand left, so it is not accepted,
    whatever else is true). An 'empty' start is always acceptable; a 'quiet' one only if --allow-quiet names the
    recording's condition (`cond`)."""
    if info["tail"] is None:
        return ("no hand-free run at the end of the recording" +
                (f" (a start at {info['start']} exists, but from before the hand left)" if info["start"] is not None else ""))
    if info["kind"] == "quiet" and not allow_quiet:
        return f"only a still bottle, no empty tank (best: quiet); pass --allow-quiet {cond} if Gate S accepts it"
    return None


def cmd_start_frames(a):
    """Task 1.2: frame states from the fresh masks -> start frame, tail, recipe; the MAD cross-check.
    Exits 2 (Gate S) when a recording has no hand-free tail, or its start frame is a still bottle and
    --allow-quiet did not name its condition (`--allow-quiet air`). Writes each recording's states and
    best-neighbour bottle IoUs too, and its Gate S reason (`gate_s`, null when it passes): later steps refuse
    a recording whose `gate_s` is set."""
    allowed = set(a.allow_quiet)
    unknown = sorted(allowed - set(recordings()))
    if unknown:
        sys.exit(f"--allow-quiet: unknown condition {unknown} (conditions: {', '.join(recordings())})")
    table, tiles, labels, stop = {}, [], [], False
    for cond, rec in recordings().items():
        bottle, hand = _masks(rec)
        states, ious = classify_with_ious(bottle, hand)
        info = start_and_tail(states)
        region = exclusion_mask(hand.any(axis=0), np.zeros_like(hand[0]), 0.5)[::2, ::2]
        gray = np.stack([cv2.resize(cv2.imread(str(rec.left_path(k)), cv2.IMREAD_GRAYSCALE), (552, 311),
                                    interpolation=cv2.INTER_AREA) for k in range(rec.n_frames)]).astype(np.float32)
        mad = region_mad(gray, region[:311, :552]) if region.any() else np.zeros(rec.n_frames)
        hand_idx = [k for k, s in enumerate(states) if s == "hand"]
        info.update({"condition": cond, "n_frames": rec.n_frames, "n_hand": len(hand_idx),
                     "counts": {s: states.count(s) for s in ("hand", "moving", "quiet", "empty")},
                     "mad_start": None if info["start"] is None else round(float(mad[info["start"]]), 3),
                     "mad_hand_median": round(float(np.median(mad[hand_idx])), 3) if hand_idx else None,
                     "states": states, "ious": [None if v is None else round(float(v), 4) for v in ious]})
        why = gate_s_reason(info, cond in allowed, cond)
        info["gate_s"] = why
        table[rec.name] = info
        print(f"{cond:24s} start={info['start']} kind={info['kind']} tail={info['tail']} ({info['tail_len']}, "
              f"empty {info['empty_tail_len']}) recipe={info['recipe']} mad {info['mad_start']} vs hand {info['mad_hand_median']}")
        if why:
            stop = True
            print(f"  GATE S: {cond}: {why}")
        for k in ([info["start"]] if info["start"] is not None else []) + [rec.n_frames - 1]:
            tiles.append(cv2.imread(str(rec.left_path(k))))
            labels.append(f"{cond} {k} {states[k]}")
    _dump(START_FRAMES, table)
    _sheet(tiles, labels, 2, runs_dir() / "sheets" / "start_frames.jpg")
    if stop:
        sys.exit(2)


# ---- tasks 1.3, 1.4 ---------------------------------------------------------------------------------

def _bottle_curve(rec, bottle_half):
    cal = rec.calibration
    z = {}
    for f in rec.matched_frames:
        p = runs_dir() / "disp" / rec.name / f"{f:06d}.npz"
        if not p.exists():
            continue
        m = cv2.resize(bottle_half[f].astype(np.uint8), (2208, 1242), interpolation=cv2.INTER_NEAREST) > 0
        z[f] = bottle_depth(load_disp(p), m, cal.fx, cal.baseline_mm)
    return z


def cmd_units(_):
    """Task 1.3 (private): stereo depth at the bottle over the labels' Center_Distance."""
    out = {}
    for cond, rec in recordings().items():
        bottle, _ = _masks(rec)
        z = _bottle_curve(rec, bottle)
        s = ratio_summary(z, rec.matched)
        dys = [float(np.load(p)["dy_px"]) for p in sorted((runs_dir() / "disp" / rec.name).glob("*.npz"))]
        s["dy_px_median"] = float(np.nanmedian(dys)) if dys and np.isfinite(dys).any() else None
        out[cond] = s
        print(cond, s)
    _dump(runs_dir() / "units.json", out)
    air = out["air"].get("median", float("nan"))
    if not 0.71 < air < 1.41:
        sys.exit(f"units: air ratio {air:.3f} is nearer 0.5 or 2 than 1; check the half-resolution factor")


def _load_disps(rec, frames):
    """The half-resolution disparities of `frames` (N, h, w) and their shared iscale, with the Task 1.3a checks."""
    missing = [f for f in frames if not (runs_dir() / "disp" / rec.name / f"{f:06d}.npz").exists()]
    if not frames or missing:
        sys.exit(f"{rec.name}: {len(missing) if frames else 'all'} disparity files missing "
                 f"(e.g. frame {missing[:3] or '-'}): run `uv run modal run modal_stereo.py` first (task 1.3a)")
    disps, iscales = [], set()
    for f in frames:
        with np.load(runs_dir() / "disp" / rec.name / f"{f:06d}.npz") as z:
            disps.append(z["disp_half"].astype(np.float32))
            iscales.add(float(z["iscale"]))
    if len(iscales) != 1:
        sys.exit(f"{rec.name}: the disparity files disagree on iscale ({sorted(iscales)}); re-run task 1.3a")
    iscale = iscales.pop()
    if abs(iscale - REAL_W / disps[0].shape[1]) > 1e-6:
        sys.exit(f"{rec.name}: the disparity files say iscale {iscale:g}, but their {disps[0].shape[1]}-wide grid "
                 f"is {REAL_W / disps[0].shape[1]:g}x smaller than the {REAL_W}-wide frames")
    return np.stack(disps), iscale


def cmd_tank(_):
    """Task 1.4: tank_disp per recording, by the recipe task 1.2 chose. An empty tail of any length builds the
    map (call 45); for a tail shorter than MIN_OBS the masked median is also computed, as a cross-check only
    (`xcheck masked`, written to <name>_xcheck.json); it never feeds the map."""
    _refuse_gate_s(recordings())
    for cond, rec in recordings().items():
        info = rec.start_info
        if info is None:
            sys.exit(f"no start_frames.json entry for {rec.name}: run task 1.2 (`uv run python cli.py start-frames`)")
        bottle, hand = _masks(rec)
        matched = [f for f in rec.matched_frames if (runs_dir() / "disp" / rec.name / f"{f:06d}.npz").exists()]
        if info["recipe"] == "tail":
            frames, excl = list(range(info["tail"][0], info["tail"][1] + 1)), None
            min_obs = tail_min_obs(len(frames))
        else:
            frames, min_obs = matched, MIN_OBS
            excl = np.stack([exclusion_mask(bottle[f], hand[f], 0.5) for f in frames]) if frames else None
        disps, iscale = _load_disps(rec, frames)
        out = tank_median(disps, excl, min_obs)
        d = runs_dir() / "tank"
        d.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(d / f"{rec.name}.npz", recipe=info["recipe"], frames=np.array(frames),
                            iscale=np.float32(iscale), **out)
        write_png16(d / f"{rec.name}.png", half_to_full(np.nan_to_num(out["tank_disp_half"]), iscale))
        z = _bottle_curve(rec, bottle)
        curve = [{"frame": f, "p": p, "z_su": z[f]} for f, p in zip(sorted(z), progress(sorted(z)))] if z else []
        _dump(d / f"{rec.name}_bottle.json", curve, indent=1)
        v = out["valid"]
        iqr = np.nanmedian(out["rel_iqr"]) if np.isfinite(out["rel_iqr"]).any() else None
        line = (f"{cond:24s} recipe={info['recipe']} frames={len(frames)} valid={v.mean():.3f} "
                f"median disp={np.nanmedian(out['tank_disp_half']) * iscale:.1f} px (full res) "
                f"rel IQR={'n/a' if iqr is None else format(iqr, '.3f')}")
        if info["recipe"] == "tail" and info.get("kind") == "empty" and len(frames) < MIN_OBS and matched:
            md, _ = _load_disps(rec, matched)
            ex = np.stack([exclusion_mask(bottle[f], hand[f], 0.5) for f in matched])
            masked = tank_median(md, ex)
            x = xcheck(out["tank_disp_half"], masked["tank_disp_half"], ex.any(axis=0))
            x["masked_frames"] = len(matched)
            _dump(d / f"{rec.name}_xcheck.json", x, indent=1)
            line += (f" xcheck masked: n/a (no common pixels)" if x["med"] is None
                     else f" xcheck masked: med={x['med']:.3f} p90={x['p90']:.3f} (n={x['n']} px, masked frames={len(matched)})")
        print(line)


# ---- task 1.5 ---------------------------------------------------------------------------------------

def _tank_work(rec):
    z = np.load(runs_dir() / "tank" / f"{rec.name}.npz")
    half = z["tank_disp_half"]
    iscale = float(z["iscale"]) if "iscale" in z.files else 2.0  # tank files written before iscale was recorded
    ok = np.isfinite(half)
    return resample(np.where(ok, half * iscale, 0.0), ok, HALF_BOX, 1280, 720)


def cmd_floor(_):
    """Task 1.5: the noise floor (kill rule 1). A recording whose floor cannot be computed counts as above it.
    Exits 5 when kill rule 1 FIRES (3 or more of the 5 floors above 25 %), 0 when it holds."""
    floors = {}
    for cond, rec in recordings().items():
        d_work, ok = _tank_work(rec)
        z = np.load(_need(runs_dir() / "da3" / "floor" / f"{rec.name}.npz",
                          "run `uv run modal run modal_depth.py::floor` first (task 1.5)"))
        bottle, hand = _masks(rec)
        ars, fits = [], []
        for f, g in zip(z["frames"].tolist(), z["inv"].astype(np.float64)):
            excl = warp_mask(exclusion_mask(bottle[f], hand[f], 0.5), HALF_BOX, 1280, 720)
            M = ok & ~excl & np.isfinite(g)
            fit = huber_affine_fit(g, d_work, M)
            ars.append(abs_rel(rel_residual(fit.apply(g), d_work), M))
            fits.append(fit.to_dict())
        fl = noise_floor(ars)
        floors[cond] = fl
        fin = [a for a in ars if np.isfinite(a)]
        _dump(runs_dir() / "floor" / f"{rec.name}.json",
              {"floor": fl, "n": len(ars), "p25": float(np.percentile(fin, 25)) if fin else None,
               "p75": float(np.percentile(fin, 75)) if fin else None, "abs_rel": ars,
               "frames": z["frames"].tolist(), "fits": fits}, indent=1)
        print(f"{cond:24s} floor (median AbsRel_tank) = {_fmt(fl, '.3f')} over {len(ars)} frames")
    over = [c for c, f in floors.items() if not np.isfinite(f) or f > KILL1]
    fires = len(over) >= 3
    print(f"kill rule 1: {len(over)} of 5 above {KILL1:.0%} {over} -> {'FIRES' if fires else 'holds'}")
    print("exit 5: kill rule 1 fires (stop and report)" if fires else "exit 0: kill rule 1 holds")
    if fires:
        sys.exit(5)


# ---- task 1.6 ---------------------------------------------------------------------------------------

def cmd_recon(_):
    """Task 1.6: mesh per recording; identity render against tank_disp and the start frame; contact sheet."""
    from camera import Pose
    from dive import load_tank
    from render import render
    _refuse_gate_s(recordings())
    tiles, labels = [], []
    for cond, rec in recordings().items():
        tank = load_tank(rec, runs_dir())
        d = runs_dir() / "recon"
        d.mkdir(parents=True, exist_ok=True)
        tank.mesh.save(d / f"{rec.name}.npz")
        k = tank.k_grid(FILL_1280x720, 1280, 720)
        d_work, ok = tank.on_grid(FILL_1280x720, 1280, 720)
        start = cv2.resize(cv2.imread(str(rec.left_path(rec.start_frame))), (1280, 720), interpolation=cv2.INTER_AREA)
        stats = {"far_end": tank.far_end}
        for fwd in (0.0, 100.0, 200.0):
            rd = render(tank.mesh, k, Pose(np.eye(3), np.array([0.0, 0.0, fwd])))
            stats[f"seen_{int(fwd)}"] = float(rd.seen.mean())
            if fwd == 0.0:
                both = rd.seen & ok
                rel = np.abs(rd.inv_depth[both] * tank.fxb - d_work[both]) / d_work[both]
                stats["depth_rel_err_p99"] = float(np.percentile(rel, 99))
                stats["colour_rmse"] = float(np.sqrt(np.mean((rd.color[both].astype(float) - start[both]) ** 2)))
                stats["seen_vs_valid"] = float(both.sum() / max(ok.sum(), 1))
            tiles.append(rd.color)
            labels.append(f"{cond} +{int(fwd)} su")
        _dump(d / f"{rec.name}.json", stats)
        print(cond, json.dumps(stats))
        assert stats["depth_rel_err_p99"] < 0.01, "identity render must reproduce tank_disp"
    _sheet(tiles, labels, 3, runs_dir() / "sheets" / "recon.jpg", w=640)


# ---- task 1.7 ---------------------------------------------------------------------------------------

def cmd_selftest_prep(_):
    """Task 1.7, step 1: renders along the known path (SELFTEST_TRAVEL_SU = 200 su forward over 48 frames,
    +-3 deg yaw; su = uncorrected stereo units)."""
    from dive import load_tank, selftest_renders
    for cond, rec in recordings().items():
        tank = load_tank(rec, runs_dir())
        frames, inv, truth = selftest_renders(tank)
        d = runs_dir() / "selftest" / rec.name
        d.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(frames):
            cv2.imwrite(str(d / f"frame_{i:03d}.png"), f)
        np.savez_compressed(d / "inv_true.npz", inv=inv.astype(np.float32))
        _dump(d / "truth.json", [{"R": p.R.tolist(), "C": p.C.tolist()} for p in truth], indent=None)
        print(cond, len(frames), "renders ->", d)


def cmd_selftest(_):
    """Task 1.7, step 3: both estimators on the renders; kill rule 4; the frozen choice of primary path.
    Exits 6 when kill rule 4 FIRES."""
    from camera import Pose
    from dive import SELFTEST_TRAVEL_SU, _icp_path, load_tank, run_clip, score_path
    from mapping import box_intrinsics
    recs = recordings()
    _require_floor(recs.values())
    for rec in recs.values():
        _need(runs_dir() / "da3" / "selftest" / f"{rec.name}.npz",
              "run `uv run python cli.py selftest-prep`, then `uv run modal run modal_depth.py::selftest`")
    scores, report = {}, {}
    for cond, rec in recs.items():
        tank = load_tank(rec, runs_dir())
        d = runs_dir() / "selftest" / rec.name
        frames = [cv2.imread(str(p)) for p in sorted(d.glob("frame_*.png"))]
        truth = [Pose(np.array(t["R"]), np.array(t["C"])) for t in json.loads((d / "truth.json").read_text())]
        inv = np.load(runs_dir() / "da3" / "selftest" / f"{rec.name}.npz")["inv"].astype(np.float64)
        entry, arrays = run_clip(tank, frames, inv, None, FILL_1280x720, primary="tracks", clip_id=f"selftest_{cond}")
        tr_lost, icp_lost = entry["tracks"]["lost_from"], entry["icp"]["lost_from"]
        s_tr = score_path([Pose(r, c) for r, c in zip(arrays["R_tracks"], arrays["C_tracks"])], truth,
                          SELFTEST_TRAVEL_SU, tr_lost)
        s_icp = score_path([Pose(r, c) for r, c in zip(arrays["R_icp"], arrays["C_icp"])], truth,
                           SELFTEST_TRAVEL_SU, icp_lost)
        # diagnostic: depth registration on perfect depth, to split registration error from depth-model error
        inv_true = np.load(d / "inv_true.npz")["inv"].astype(np.float64)
        k = box_intrinsics(tank.k_real, FILL_1280x720, 1280, 720)
        d0, ok0 = tank.on_grid(FILL_1280x720, 1280, 720)
        fit_true = huber_affine_fit(inv_true[0], d0, ok0)
        icp_true, _, _, lost_true = _icp_path(tank, k, inv_true, np.zeros(inv_true.shape, bool), fit_true)
        s_true = score_path(icp_true, truth, SELFTEST_TRAVEL_SU, lost_true)
        scores[cond] = {"tracks": s_tr, "icp": s_icp}
        null_d = _nan_summary(entry["D"])
        null_df = _nan_summary(entry["D_float"])
        report[cond] = {"tracks": s_tr, "icp": s_icp, "icp_perfect_depth": s_true, "null_dream_D": null_d,
                        "null_dream_D_float": null_df["median"], "fit": entry["fit"]}
        print(f"{cond:24s} tracks {s_tr['endpoint_err_frac']:.3f} (yaw max {s_tr['yaw_err_deg_max']:.2f} deg)  "
              f"icp(DA3) {s_icp['endpoint_err_frac']:.3f} (yaw max {s_icp['yaw_err_deg_max']:.2f} deg)  "
              f"icp(perfect) {s_true['endpoint_err_frac']:.3f}  null-dream D median {_fmt(null_d['median'])}")
    _selftest_conclude(scores, report)


def _selftest_conclude(scores: dict, report: dict) -> None:
    """Kill rule 4 and the frozen choice of primary path. Writes report.json and path_choice.json, then exits 6
    if kill rule 4 FIRES (3 or more of the 5 recordings above 15 % of travel on the chosen path)."""
    from dive import PATH_CHOICE, choose_primary
    primary = choose_primary(scores)
    over = {e: [c for c in scores if scores[c][e]["endpoint_err_frac"] > KILL4] for e in ("tracks", "icp")}
    fires = len(over[primary]) >= 3
    _dump(runs_dir() / "selftest" / "report.json", report)
    _dump(PATH_CHOICE, {"primary": primary, "kill_rule_4": "FIRES" if fires else "holds", "over_15pct": over,
                        "rule": "lower median endpoint error; ties within 2 % of travel go to icp",
                        "date": time.strftime("%Y-%m-%d")})
    print(f"primary path: {primary}; kill rule 4 on {primary}: {len(over[primary])} of 5 above 15 % -> "
          f"{'FIRES' if fires else 'holds'}")
    print("exit 6: kill rule 4 fires (stop and report)" if fires else "exit 0: kill rule 4 holds")
    if fires:
        sys.exit(6)


# ---- R2 step 2b: the vertical-offset test -------------------------------------------------------------

def sift_matches(left_gray: np.ndarray, right_gray: np.ndarray, top: int = 200, n_features: int = 12000,
                 ratio: float = 0.75, max_dy: float = 6.0) -> dict:
    """Up to `top` SIFT matches on a rectified pair (lowest ratio-test score first, |dy| < max_dy, positive
    disparity): left pixel (x, y) and the match's horizontal disparity dx = x_left - x_right, with dy = y_left - y_right."""
    sift = cv2.SIFT_create(n_features)
    kl, dl = sift.detectAndCompute(left_gray, None)
    kr, dr = sift.detectAndCompute(right_gray, None)
    empty = {"x": np.zeros(0), "y": np.zeros(0), "dx": np.zeros(0), "dy": np.zeros(0)}
    if dl is None or dr is None or len(kl) < 10 or len(kr) < 10:
        return empty
    rows = []
    for p in cv2.BFMatcher().knnMatch(dl, dr, k=2):
        if len(p) == 2 and p[0].distance < ratio * p[1].distance:
            a, b = kl[p[0].queryIdx].pt, kr[p[0].trainIdx].pt
            dx, dy = a[0] - b[0], a[1] - b[1]
            if abs(dy) < max_dy and dx > 0:
                rows.append((p[0].distance / p[1].distance, a[0], a[1], dx, dy))
    rows.sort()
    if not rows:
        return empty
    r = np.array(rows[:top])
    return {"x": r[:, 1], "y": r[:, 2], "dx": r[:, 3], "dy": r[:, 4]}


def sift_errors(published: np.ndarray, shifted: np.ndarray, m: dict) -> tuple[np.ndarray, np.ndarray]:
    """|map(x_left, y_left) - dx| per SIFT match, for each map, over the matches where both maps are valid."""
    vp = np.isfinite(published) & (published > 0)
    vs = np.isfinite(shifted) & (shifted > 0)
    h, w = published.shape
    u = np.clip(np.rint(m["x"]).astype(int), 0, w - 1)
    v = np.clip(np.rint(m["y"]).astype(int), 0, h - 1)
    use = vp[v, u] & vs[v, u]
    return np.abs(published[v, u][use] - m["dx"][use]), np.abs(shifted[v, u][use] - m["dx"][use])


def dy_pool(errs: dict) -> list[dict]:
    """{condition: [(err_published, err_shifted) per pair]} -> one row per recording over its pooled matches
    (same median-absolute-error and gain as a single pair; gain is None with no match or a zero published error)."""
    rows = []
    for cond, pairs in errs.items():
        ep = np.concatenate([p for p, _ in pairs]) if pairs else np.zeros(0)
        es = np.concatenate([s for _, s in pairs]) if pairs else np.zeros(0)
        row = {"condition": cond, "pairs": len(pairs), "sift_n_used": int(len(ep)),
               "sift_err_published": float(np.median(ep)) if len(ep) else None,
               "sift_err_shifted": float(np.median(es)) if len(ep) else None}
        ok = len(ep) > 0 and row["sift_err_published"] > 0
        row["sift_gain"] = (row["sift_err_published"] - row["sift_err_shifted"]) / row["sift_err_published"] if ok else None
        rows.append(row)
    return rows


def score_dy_maps(published: np.ndarray, shifted: np.ndarray, m: dict, tank_valid: np.ndarray | None = None) -> dict:
    """Compare two full-resolution disparity maps of one pair (NaN or <= 0 = invalid).

    median_abs_diff: median |published - shifted| over pixels valid in both (and in `tank_valid` if given).
    valid_published / valid_shifted: share of pixels that are valid (within `tank_valid` if given).
    sift_err_*: median |map(x_left, y_left) - dx| over the matches `m` (sift_matches), on the matches where
    both maps are valid, so the two errors are over the same points; gain = (published - shifted) / published,
    positive when the shifted map is closer to the matches."""
    vp = np.isfinite(published) & (published > 0)
    vs = np.isfinite(shifted) & (shifted > 0)
    region = np.ones(vp.shape, bool) if tank_valid is None else tank_valid
    both = vp & vs & region
    out = {"median_abs_diff": float(np.median(np.abs(published[both] - shifted[both]))) if both.any() else None,
           "valid_published": float(vp[region].mean()) if region.any() else None,
           "valid_shifted": float(vs[region].mean()) if region.any() else None}
    ep, es = sift_errors(published, shifted, m)
    out.update({"sift_n": int(len(m["dx"])), "sift_n_used": int(len(ep)),
                "sift_err_published": float(np.median(ep)) if len(ep) else None,
                "sift_err_shifted": float(np.median(es)) if len(ep) else None})
    ok = len(ep) > 0 and out["sift_err_published"] > 0
    out["sift_gain"] = (out["sift_err_published"] - out["sift_err_shifted"]) / out["sift_err_published"] if ok else None
    return out


def cmd_dy_score(_):
    """R2 step 2b, local: score runs/disp_dytest/{published,shifted} (written by `modal_stereo.py --dy-test`).
    The SIFT matches of all of a recording's pairs are pooled (Aaron, call 43), so a recording is scored on its pooled
    errors; the per-pair rows are printed too. Exit 3: the shifted maps beat the published ones by more than 10 % on
    3 or more recordings. Exit 4: INCONCLUSIVE, fewer than 3 recordings had 30 or more pooled SIFT matches inside
    valid pixels of both maps, so the test could not measure (it must not read as 'holds'). Exit 0: it measured and
    the shift does not help."""
    root = runs_dir() / "disp_dytest"
    manifest = json.loads(_need(root / "pairs.json", "run `uv run modal run modal_stereo.py --dy-test` first").read_text())
    recs = {r.name: r for r in recordings().values()}
    rows, errs = [], {}
    for item in manifest:
        rec, f = recs[item["recording"]], item["frame"]
        pub = load_disp(root / "published" / rec.name / f"{f:06d}.npz")
        sh = load_disp(root / "shifted" / rec.name / f"{f:06d}.npz")
        m = sift_matches(cv2.imread(str(rec.left_path(f)), cv2.IMREAD_GRAYSCALE),
                         cv2.imread(str(rec.right_path(f)), cv2.IMREAD_GRAYSCALE))
        tp = runs_dir() / "tank" / f"{rec.name}.npz"
        tank_valid = None
        if tp.exists():  # the tank's validity region, once task 1.4 has run
            tank_valid = cv2.resize(np.isfinite(np.load(tp)["tank_disp_half"]).astype(np.uint8), (2208, 1242),
                                    interpolation=cv2.INTER_NEAREST) > 0
        rows.append({"condition": item["condition"], "frame": f, "dy_px": item["dy_px"], "dy_applied": item["dy_applied"],
                     "region": "tank validity" if tank_valid is not None else "both maps valid",
                     **score_dy_maps(pub, sh, m, tank_valid)})
        errs.setdefault(item["condition"], []).append(sift_errors(pub, sh, m))
    print("| condition | frame | dy_px | median abs diff (px) | valid published | valid shifted | SIFT n | err published (px) | err shifted (px) | gain |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['condition']} | {r['frame']} | {_fmt(r['dy_px'])} | {_fmt(r['median_abs_diff'])} | "
              f"{_fmt(r['valid_published'], '.3f')} | {_fmt(r['valid_shifted'], '.3f')} | {r['sift_n_used']}/{r['sift_n']} | "
              f"{_fmt(r['sift_err_published'])} | {_fmt(r['sift_err_shifted'])} | "
              f"{_fmt(None if r['sift_gain'] is None else 100 * r['sift_gain'], '+.0f')}% |")
    pooled = dy_pool(errs)
    print("\nPooled over each recording's pairs:\n")
    print("| condition | pairs | SIFT n used | err published (px) | err shifted (px) | gain |")
    print("|---|---|---|---|---|---|")
    for r in pooled:
        print(f"| {r['condition']} | {r['pairs']} | {r['sift_n_used']} | {_fmt(r['sift_err_published'])} | "
              f"{_fmt(r['sift_err_shifted'])} | {_fmt(None if r['sift_gain'] is None else 100 * r['sift_gain'], '+.0f')}% |")
    verdict, better, measured = dy_verdict(pooled)
    _dump(root / "report.json", {"rows": rows, "pooled": pooled, "better_by_over_10pct": better,
                                 "measured_recordings": measured, "stop_rule": verdict})
    if verdict == "INCONCLUSIVE":
        print(f"stop rule: INCONCLUSIVE: only {measured} of {len(pooled)} recordings have at least {DY_MIN_USED} pooled "
              f"SIFT matches inside valid pixels of both maps, fewer than {DY_STOP_PAIRS} needed to read the test; look at "
              "the maps and the pairs before deciding anything. exit 4")
        sys.exit(4)
    print(f"stop rule: shifted beats published by more than {DY_STOP_GAIN:.0%} on {len(better)} of {measured} measured "
          f"recordings {better} -> " + ("FIRES: stop and report to the controller before the full run. exit 3"
                                        if verdict == "FIRES" else "holds: continue with no correction. exit 0"))
    if verdict == "FIRES":
        sys.exit(3)


def dy_verdict(rows: list[dict]) -> tuple[str, list[str], int]:
    """(verdict, conditions where the shift won by more than 10 %, measured count). Rows are recordings (pooled
    matches), measured only with a SIFT gain and at least DY_MIN_USED matches used; with fewer than DY_STOP_PAIRS
    measured the verdict is INCONCLUSIVE, never 'holds'."""
    measured = [r for r in rows if r["sift_gain"] is not None and r["sift_n_used"] >= DY_MIN_USED]
    if len(measured) < DY_STOP_PAIRS:
        return "INCONCLUSIVE", [], len(measured)
    better = [r["condition"] for r in measured if r["sift_gain"] > DY_STOP_GAIN]
    return ("FIRES" if len(better) >= DY_STOP_PAIRS else "holds"), better, len(measured)


# ---- phase 2/3 --------------------------------------------------------------------------------------

def _index() -> dict:
    return json.loads((runs_dir() / "clips_index.json").read_text())


def cmd_map(a):
    """Task 2.5: measure each clip's box on frame 0 against its start frame."""
    from dive import read_video
    idx = _index()
    bad = []
    for cid in (a.clips or list(idx)):
        c = idx[cid]
        rec = recordings()[c["condition"]]
        out = measure_box(cv2.imread(str(rec.left_path(rec.start_frame))), read_video(c["video"])[0])
        _dump(runs_dir() / "mapping" / f"{cid}.json", out)
        print(f"{cid:32s} {out['name']:8s} ratio={_fmt(out['ratio'], '.3f')} ok={out['ok']}")
        if not out["ok"]:
            bad.append(cid)
    if bad:
        sys.exit(f"mapping failed for {bad}: a logged retake reason (task 2.4)")


def cmd_dive(a):
    """Task 3.2: the real run on generated clips; writes runs/dive/<clip>.json/.npz and runs/clips.json."""
    from dive import TRUSTED_TRAVEL_SU, load_tank, primary_path, read_video, run_clip
    idx = _index()
    ids = a.clips or list(idx)
    _require_floor({idx[c]["condition"]: recordings()[idx[c]["condition"]] for c in ids}.values())
    primary = primary_path()
    tanks: dict = {}
    clips_path = runs_dir() / "clips.json"
    allc = json.loads(clips_path.read_text())["clips"] if clips_path.exists() else []
    for cid in ids:
        c = idx[cid]
        rec = recordings()[c["condition"]]
        if rec.name not in tanks:
            tanks[rec.name] = load_tank(rec, runs_dir())
        m = json.loads(_need(runs_dir() / "mapping" / f"{cid}.json", "run `uv run python cli.py map` first").read_text())
        assert m["ok"], f"{cid}: mapping not ok"
        frames = read_video(c["video"])
        dz = np.load(c["depth"])
        inv = dz["inv"].astype(np.float64)
        moving = unpack_masks(dz["moving"], inv.shape[2]) if "moving" in dz.files else None
        assert len(frames) == len(inv) and frames[0].shape[:2] == inv.shape[1:], cid
        meta = {k: c[k] for k in ("condition", "engine", "prompt", "seconds", "take") if k in c}
        entry, arrays = run_clip(tanks[rec.name], frames, inv, moving, tuple(m["box"]), primary, clip_id=cid, meta=meta,
                                 trusted_travel=TRUSTED_TRAVEL_SU.get(c["condition"]))
        d = runs_dir() / "dive"
        d.mkdir(parents=True, exist_ok=True)
        _dump(d / f"{cid}.json", entry, indent=1)
        np.savez_compressed(d / f"{cid}.npz", fit=np.array([entry["fit"]["s"], entry["fit"]["t"]]), **arrays)
        allc = [e for e in allc if e["clip"] != cid] + [entry]
        _dump(clips_path, {"clips": sorted(allc, key=lambda e: e["clip"])}, indent=1)
        print(f"{cid:32s} D@5s={_fmt(entry['D_at'].get('5'))} V@5s={_fmt(entry['V_at'].get('5'))} lost={entry['lost_from']} "
              f"wall={entry['wall_frame']} travel={_fmt(entry['travel'], '.0f')} su")


def cmd_probe_sheet(_):
    """Task 2.2: runs/probes.json (motion cross-check) and runs/sheets/probes.jpg for Gate P. Reports only."""
    import probes
    rep = probes.build_report()
    if not rep["probes"]:
        import clips
        for cid, why in clips.rebuild_probes_index()["invalid"]:
            print(f"  invalid, not indexed: {cid}: {why}")
        sys.exit("no valid probes under runs/gen45 (ids end in __probe2s): run `uv run python runway_calls.py probes --yes` first")
    for cid, r in rep["probes"].items():
        print(f"{cid:40s} sift {_fmt(r['sift']['scale'], '.3f'):>6s} {r['sift_reading']:10s} ({r['sift']['inliers']:3d} in) "
              f"flow {_fmt(r['flow']['scale'], '.3f'):>6s} {r['flow_reading']:10s} change {r['change']['frame_to_frame']:.2f}/frame")
    for p, v in rep["summary"].items():
        if p == "D":
            print(f"prompt D: forward on {v['forward_sift']} of {v['probes']} by SIFT ({v['unmeasured_sift']} unmeasured), "
                  f"{v['forward_flow']} of {v['probes']} by flow ({v['unmeasured_flow']} unmeasured)   "
                  "[kill rule 2, read in reverse: forward on fewer than 3 of 5 means one rewrite, Aaron's, in house wording]")
        else:
            print(f"prompt {p}: moved on {v['moved']} of {v['probes']}, {v['unmeasured']} unmeasured (forward by SIFT "
                  f"{v['forward_sift']} ({v['unmeasured_sift']} unmeasured), by flow {v['forward_flow']} ({v['unmeasured_flow']} unmeasured))"
                  "   [kill rule 2, forward direction: 3 or more of 5 means one rewrite, Aaron's; an unmeasured probe is not a hold]")
    print("a cross-check for the eye: Gate P reads the sheet and decides")
    print("sheet:", probes.make_sheet(rep))


def cmd_clips_index(_):
    """Rebuild runs/clips_index.json (finals and hunt takes) and runs/probes_index.json from the valid mp4s on disk."""
    import clips
    f, p = clips.rebuild_clips_index(), clips.rebuild_probes_index()
    print(f"clips_index.json: {len(f['index'])} clips; probes_index.json: {len(p['index'])} probes")
    for cid, why in f["invalid"]:
        print(f"  not indexed: {cid}: {why}")
    missing = [cid for cid in f["index"] if not clips.depth_ready(clips.parse_clip_id(cid))]
    if missing:
        print(f"  {len(missing)} clips have no depth file yet (task 3.1): {', '.join(missing[:3])}{' …' if len(missing) > 3 else ''}")


def cmd_clip_sheet(a):
    """A contact sheet (every 12th frame) of each named clip in runs/sheets/<clip>.jpg: round 2's readings, the hunt's yes or no."""
    import clips
    import probes
    for cid in a.clips:
        spec = clips.parse_clip_id(cid)
        frames = probes.read_frames(_need(clips.video_path(spec), f"{cid} has not been generated yet"))
        out = runs_dir() / "sheets" / f"{cid}.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out), probes.contact_sheet(frames, a.every, label=cid.split("__")[0][:12]), [cv2.IMWRITE_JPEG_QUALITY, 85])
        print(f"{cid}: {len(frames)} frames -> {out}")


def cmd_assets(a):
    """Task 3.4: every page asset under runs/assets/ (clips, recordings, clips.json, media manifest). Uploads nothing."""
    import assets
    assets.main(a.clips or None, a.recordings_only)


def summarize_entry(e: dict) -> str:
    """One sanity-read line for a clip entry (task P2 step 3). Floats and lists in an entry can be None."""
    D, V = _arr(e["D"]), _arr(e["verified"])
    d0 = D[0] if D.size else float("nan")
    vmin = np.nanmin(V) if np.isfinite(V).any() else float("nan")
    dis, trav = e.get("path_disagreement"), e.get("travel")
    pct = None if dis is None or not trav else 100 * dis / trav
    flag = "" if np.isfinite(d0) and 0.5 <= d0 <= 2 else "  <- D0 outside 0.5-2: check runs/mapping and the fit"
    return (f"{e['clip']:30s} D0={_fmt(d0)} Vmin={_fmt(vmin)} disagree={_fmt(dis, '.0f')}su "
            f"({_fmt(pct, '.0f')}% of travel, at frame {e.get('path_disagreement_frame')}) lost={e['lost_from']} "
            f"primary={e['primary_path']} far_end={_fmt(e.get('far_end'), '.0f')} wall={e.get('wall_frame')}{flag}")


def cmd_summary(_):
    """Task P2 step 3: the sanity read of runs/clips.json (None-safe; replaces the plan's inline snippet)."""
    clips = json.loads(_need(runs_dir() / "clips.json", "run `uv run python cli.py dive` first").read_text())["clips"]
    for e in clips:
        print(summarize_entry(e))


def main(argv=None):
    p = argparse.ArgumentParser(prog="cli.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("start-frames", help=cmd_start_frames.__doc__.strip().split("\n")[0])
    sp.add_argument("--allow-quiet", nargs="+", default=[], metavar="CONDITION",
                    help="the conditions for which Gate S accepted a still, hand-free start frame, e.g. "
                    "`--allow-quiet air` (only counts when the recording has a hand-free tail)")
    sp.set_defaults(fn=cmd_start_frames)
    for name, fn in [("calib", cmd_calib), ("seed-sheet", cmd_seed_sheet), ("units", cmd_units), ("tank", cmd_tank),
                     ("floor", cmd_floor), ("recon", cmd_recon), ("selftest-prep", cmd_selftest_prep),
                     ("selftest", cmd_selftest), ("dy-score", cmd_dy_score), ("summary", cmd_summary),
                     ("probe-sheet", cmd_probe_sheet), ("clips-index", cmd_clips_index)]:
        sub.add_parser(name, help=(fn.__doc__ or "").strip().split("\n")[0]).set_defaults(fn=fn)
    for name, fn in [("map", cmd_map), ("dive", cmd_dive)]:
        sp = sub.add_parser(name, help=(fn.__doc__ or "").strip().split("\n")[0])
        sp.add_argument("clips", nargs="*")
        sp.set_defaults(fn=fn)
    sp = sub.add_parser("clip-sheet", help=cmd_clip_sheet.__doc__.strip().split("\n")[0])
    sp.add_argument("clips", nargs="+")
    sp.add_argument("--every", type=int, default=12)
    sp.set_defaults(fn=cmd_clip_sheet)
    sp = sub.add_parser("assets", help=cmd_assets.__doc__.strip().split("\n")[0])
    sp.add_argument("clips", nargs="*")
    sp.add_argument("--recordings-only", action="store_true", help="only the per-recording assets (floor map, tank relief, plan)")
    sp.set_defaults(fn=cmd_assets)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
