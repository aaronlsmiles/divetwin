"""Modal app: Stereo Anywhere (CVPR 2025, CC BY-NC-SA 4.0) on the dataset's published rectified pairs.

Fresh disparity (Gate 0, 3 Nov). The code is cloned at the MODELS.md commit and the weights are
fetched at run time (Google Drive for Stereo Anywhere, Hugging Face for its Depth Anything V2 Large
prior, CC BY-NC 4.0), never vendored. The downloads happen in a CPU-only function (`fetch_weights`, no GPU)
that writes both files into the Volume and records their sha256; the GPU class only reads the Volume and
fails at once if a file is missing, so a Drive failure never loops on an L40S.

Run from pipeline/:
    uv run python modal_stereo.py --dry-run        # counts, cost estimate, no GPU, nothing remote
    uv run modal run modal_stereo.py --smoke       # 2 pairs of one recording
    uv run modal run modal_stereo.py               # every pair task 1.3a needs (needs start_frames.json)
    uv run modal run modal_stereo.py --dy-test     # R2 step 2b: 5 pairs, as published and vertically shifted
Pairs go up as half-resolution PNGs (1104 x 621, the network's input at iscale 2); disparity comes back
in half-resolution pixels and is stored as runs/disp/<recording>/<frame>.npz (disp_half, iscale=2, dy_px).

Spend guards (modal_common.Meter; the numbers are upper bounds):
  * the cap is cumulative per task: a re-run starts from what runs/modal_spend.jsonl already holds for the
    task, and the whole of Phase 1 is held to PHASE1_CAP_USD;
  * a call is refused when the spend so far plus its expected cost would pass the cap, and every call's
    timeout is about 3x its expected duration, so one call cannot run away;
  * every paid section writes one spend line however it ends (ok, cap, error, interrupted).

`modal run` starts the app on Modal before the entrypoint runs, even with --dry-run, so the dry run that
touches nothing remote (no login, no image build, no GPU) is the plain-Python form above; it also takes
--smoke, --dy-test, --only <condition> and --pairs.

The vertical-offset test (Aaron, 3 Nov): `--dy-test` runs N given pairs (`--pairs air:351,freshwater:215`,
default one auto-picked matched pair per recording) twice, once as published and once with the right image
translated down by that pair's measured dy_px before the half-resolution resize (`shift_dy`), into
runs/disp_dytest/{published,shifted}/<recording>/<frame>.npz. `python cli.py dy-score` reads them."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

import modal

SA_COMMIT = "c4aa114b8e4dbba97c41663efb80df95875eeb95"
SA_WEIGHTS_GDRIVE_ID = "11jYAFvSXNwaePwvAmrAGDJkluhqaP79J"  # stereoanywhere_sceneflow.pth in the authors' folder
DAV2_REPO = "depth-anything/Depth-Anything-V2-Large"
DAV2_REV = "cbbb86a30ce19b5684b7a05155dc7e6cbc7685b9"
DAV2_FILE = "depth_anything_v2_vitl.pth"
SA_FILE = "/weights/stereoanywhere_sceneflow.pth"
WEIGHTS_JSON = "/weights/stereo_weights_sha256.json"   # written by fetch_weights, read by the GPU class
APP_NAME = "divetwin-stereo"
GPU = "L40S"
CAP_SMOKE_USD = 0.25      # task 1.3a-smoke: 2 pairs, its own cap (cumulative like the others)
CAP_USD = 2.00            # task 1.3a cap: cumulative across re-runs of the task (modal_common.Meter)
CAP_DYTEST_USD = 0.25     # R2 step 2b: ten pairs, mostly model load and the 60 s scaledown
ISCALE = 2
BATCH = 16                # pairs per remote call

# Resources the GPU class reserves; the Meter bills the same numbers (Modal bills reserved CPU and memory).
CPU, MEM_GIB = 4, 16
# Expected durations, the estimates' own numbers; each timeout below is about 3x its expected time.
LOAD_S = 90               # model load on a cold container
S_PER_PAIR = 1.2          # GPU seconds per pair
CALL_OVERHEAD_S = 20      # upload, decode and download around one batch
FETCH_DEADLINE_S = 900    # fetch_weights gives up after this (a startup crash-loop would otherwise wait forever)
FETCH_EXPECT_S = 120      # Drive (44 MB) plus the Hugging Face file (1.3 GB) on a cold volume


def _ceil30(x: float) -> int:
    return int(-(-x // 30) * 30)


BATCH_TIMEOUT_S = max(120, _ceil30(3 * (BATCH * S_PER_PAIR + CALL_OVERHEAD_S)))   # 16 pairs: 120 s
STARTUP_S = _ceil30(3 * LOAD_S)                                                   # load has its own limit
FETCH_TIMEOUT_S = _ceil30(3 * FETCH_EXPECT_S)
FETCH_CPU, FETCH_MEM_GIB = 2, 4

app = modal.App(APP_NAME)
weights = modal.Volume.from_name("divetwin-weights", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "libgl1", "libglib2.0-0")
    .pip_install("torch==2.4.0", "torchvision==0.19.0", index_url="https://download.pytorch.org/whl/cu121")
    # provisional until the first build (MODELS.md): the floating names are pinned to the releases nearest torch 2.4.0
    .pip_install("xformers==0.0.27.post2", "timm==1.0.15", "numpy<2", "opencv-python-headless==4.10.0.84",
                 "opt_einsum==3.4.0", "kornia==0.7.3", "matplotlib==3.9.1", "huggingface_hub==0.24.0", "Pillow==10.4.0")
    .run_commands(f"git clone https://github.com/bartn8/stereoanywhere /opt/sa && cd /opt/sa && git checkout {SA_COMMIT}")
)
# CPU-only: no torch, no GPU. Everything that can fail on the network happens here.
weights_image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "huggingface_hub==0.24.0", "gdown==5.2.0", "numpy<2", "opencv-python-headless==4.10.0.84")  # numpy, cv2: top-level imports


@app.function(image=weights_image, volumes={"/weights": weights}, cpu=FETCH_CPU, memory=FETCH_MEM_GIB * 1024,
              timeout=FETCH_TIMEOUT_S)
def fetch_weights() -> dict:
    """Download both weight files into the Volume (no GPU) and record their sha256 at first download."""
    import hashlib
    import json
    import os
    import subprocess
    from pathlib import Path

    from huggingface_hub import hf_hub_download

    rec = Path(WEIGHTS_JSON)
    known = json.loads(rec.read_text()) if rec.exists() else {}
    if not os.path.exists(SA_FILE):
        subprocess.run(["gdown", SA_WEIGHTS_GDRIVE_ID, "-O", SA_FILE], check=True)
        known.pop(Path(SA_FILE).name, None)
    if os.path.getsize(SA_FILE) < 10_000_000:   # an HTML quota page, not the 44 MB checkpoint
        raise RuntimeError(f"{SA_FILE} is {os.path.getsize(SA_FILE)} bytes: the Drive download did not return the weights")
    dav2_path = hf_hub_download(DAV2_REPO, DAV2_FILE, revision=DAV2_REV, cache_dir="/weights/hf")
    for p in (SA_FILE, dav2_path):
        if Path(p).name not in known:
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            known[Path(p).name] = h.hexdigest()
    rec.write_text(json.dumps(known, indent=2))
    weights.commit()
    return known


@app.cls(gpu=GPU, image=image, volumes={"/weights": weights.read_only()}, cpu=(CPU, CPU), memory=MEM_GIB * 1024,
         timeout=BATCH_TIMEOUT_S, startup_timeout=STARTUP_S, max_containers=1, scaledown_window=60)
class StereoAnywhere:
    @modal.enter()
    def load(self):
        import json
        import os
        from types import SimpleNamespace

        import torch
        sys.path.insert(0, "/opt/sa")
        from huggingface_hub import hf_hub_download
        from models.depth_anything_v2 import get_depth_anything_v2
        from models.stereoanywhere import StereoAnywhere as SA

        # read-only: fail at once if fetch_weights has not filled the Volume
        if not (os.path.exists(SA_FILE) and os.path.exists(WEIGHTS_JSON)):
            raise FileNotFoundError(f"{SA_FILE} or {WEIGHTS_JSON} is not in the divetwin-weights Volume: "
                                    "run fetch_weights first (the entrypoint does, before any GPU starts)")
        sa_path = SA_FILE
        dav2_path = hf_hub_download(DAV2_REPO, DAV2_FILE, revision=DAV2_REV, cache_dir="/weights/hf", local_files_only=True)
        self.sha256 = json.loads(open(WEIGHTS_JSON).read())

        # the README's evaluation settings
        self.args = SimpleNamespace(
            iters=32, maxdisp=192, n_downsample=2, n_additional_hourglass=0, volume_channels=8, vol_downsample=0,
            vol_n_masks=8, use_truncate_vol=True, mirror_conf_th=0.98, mirror_attenuation=0.9,
            use_aggregate_stereo_vol=False, use_aggregate_mono_vol=True, normal_gain=10, lrc_th=1.0,
            vit_encoder="vitl", monomodel="DAv2")
        self.device = torch.device("cuda:0")
        stereo = torch.nn.DataParallel(SA(self.args)).to(self.device)
        sd = torch.load(sa_path, map_location=self.device)
        stereo.load_state_dict(sd["state_dict"] if "state_dict" in sd else sd, strict=True)
        self.stereo = stereo.module.eval().float()
        self.mono = get_depth_anything_v2(dav2_path, encoder="vitl").to(self.device).float().eval()

    @modal.method()
    def info(self) -> dict:
        return {"sha256": self.sha256, "commit": SA_COMMIT, "args": vars(self.args)}

    @modal.method()
    def disparity(self, pairs: list[tuple[bytes, bytes]]) -> tuple[list[bytes], float]:
        """PNG pairs (left, right) -> npy bytes of float16 disparity in the input's pixels; GPU seconds."""
        import io

        import cv2
        import numpy as np
        import torch
        import torch.nn.functional as F

        t0 = time.time()
        out = []
        with torch.no_grad():
            for lb, rb in pairs:
                ims = []
                for b in (lb, rb):
                    im = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
                    im = cv2.cvtColor(im, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
                    ims.append(torch.from_numpy(im).permute(2, 0, 1)[None].to(self.device))
                left, right = ims
                mono = self.mono.infer_image(torch.cat([left, right], 0), input_size_width=518, input_size_height=518)
                mono = (mono - mono.min()) / (mono.max() - mono.min())  # the demo's joint normalisation
                lm, rm = mono[0:1], mono[1:2]
                ht, wt = left.shape[-2:]
                ph, pw = (((ht // 32) + 1) * 32 - ht) % 32, (((wt // 32) + 1) * 32 - wt) % 32
                pad = [pw // 2, pw - pw // 2, ph // 2, ph - ph // 2]
                L, R, LM, RM = (F.pad(x, pad, mode="replicate") for x in (left, right, lm, rm))
                disp, _ = self.stereo(L, R, LM, RM, test_mode=True, iters=self.args.iters)
                disp = -disp.squeeze(1)
                hd, wd = disp.shape[-2:]
                disp = disp[..., pad[2]:hd - pad[3], pad[0]:wd - pad[1]]
                buf = io.BytesIO()
                np.save(buf, disp.squeeze().float().cpu().numpy().astype(np.float16))
                out.append(buf.getvalue())
        return out, time.time() - t0



def shift_vertical(img: np.ndarray, dy: float) -> np.ndarray:
    """Translate an image down by `dy` pixels (negative: up): a pure vertical shift, INTER_LINEAR, border
    replicate. A non-finite or zero dy returns the image unchanged."""
    if not np.isfinite(dy) or dy == 0:
        return img
    h, w = img.shape[:2]
    m = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, float(dy)]])
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def _load_half(rec, f: int):
    Lf = cv2.imread(str(rec.left_path(f)), cv2.IMREAD_COLOR)
    Rf = cv2.imread(str(rec.right_path(f)), cv2.IMREAD_COLOR)
    size = (Lf.shape[1] // ISCALE, Lf.shape[0] // ISCALE)
    return Lf, Rf, cv2.resize(Lf, size, interpolation=cv2.INTER_AREA), cv2.resize(Rf, size, interpolation=cv2.INTER_AREA), size


def prepare_pair_both(rec, f: int, shifted: bool = True):
    """One rectified pair at the network's half resolution, SIFT dy measured once:
    (left, right as published, right shifted by dy or None, dy_px, dy_applied).

    dy_px is the pair's measured vertical residual (left y minus right y, median SIFT match, full-resolution
    pixels), recorded with every output. The shifted right view is translated down by that dy_px (pure vertical
    translation, INTER_LINEAR, border replicate) at full resolution, before the half-resolution resize; with no
    measurable dy (too few matches) nothing is shifted (dy_applied 0.0, and the shifted view is the published one)."""
    from units import epipolar_dy
    Lf, Rf, L, R, size = _load_half(rec, f)
    dy = float(epipolar_dy(L[..., 1], R[..., 1]).get("median_dy", float("nan")) * ISCALE)
    applied, R_sh = 0.0, None
    if shifted:
        R_sh = R
        if np.isfinite(dy):
            R_sh = cv2.resize(shift_vertical(Rf, dy), size, interpolation=cv2.INTER_AREA)
            applied = dy
    return L, R, R_sh, dy, applied


def prepare_pair(rec, f: int, shift_dy: bool = False):
    """(left, right, dy_px, dy_applied): the published pair, or with shift_dy the right view shifted by its dy_px."""
    L, R, R_sh, dy, applied = prepare_pair_both(rec, f, shifted=shift_dy)
    return (L, R_sh, dy, applied) if shift_dy else (L, R, dy, 0.0)


def frames_needed(rec) -> list[int]:
    """Matched (labelled) frames, the static tail and the start frame (task 1.2's start_frames.json).
    Refuses a recording whose start_frames entry records a Gate S failure: its tail and start are not trusted."""
    info = rec.start_info or {}
    if info.get("gate_s"):
        sys.exit(f"{rec.name}: Gate S failed ({info['gate_s']}), so its tail and start frame are not run; "
                 "settle Gate S first (`uv run python cli.py start-frames`)")
    need = set(rec.matched_frames)
    if info.get("tail"):
        a, b = info["tail"]
        need |= set(range(a, b + 1))
    if info.get("start") is not None:
        need.add(int(info["start"]))
    return sorted(need)


def plan_jobs(recs: dict, smoke: bool = False) -> list:
    """Pairs still to run: (recording, frame, output path). Smoke is the first two matched frames of the first
    recording (matched frames only, so it does not depend on Gate S)."""
    from recordings import runs_dir
    jobs = []
    for rec in recs.values():
        frames = sorted(rec.matched_frames)[:2] if smoke else frames_needed(rec)
        out_dir = runs_dir() / "disp" / rec.name
        jobs += [(rec, f, out_dir / f"{f:06d}.npz") for f in frames if not (out_dir / f"{f:06d}.npz").exists()]
        if smoke:
            break
    return jobs


def parse_pairs(spec: str, recs: dict) -> list:
    """'air:351,freshwater:215' -> [(recording, frame)]; the frame must be one of that recording's matched frames."""
    out = []
    for item in spec.split(","):
        cond, _, f = item.strip().partition(":")
        if cond not in recs or not f.lstrip("-").isdigit() or int(f) not in recs[cond].matched_frames:
            sys.exit(f"--pairs: '{item}' is not <condition>:<matched frame> (conditions: {', '.join(recs)})")
        out.append((recs[cond], int(f)))
    return out


def pick_dytest_frame(rec, n_candidates: int = 5) -> int:
    """The matched frame, among 5 spread over 10-90 % of the recording, with the most SIFT matches on the
    half-resolution pair (so the measured dy_px is trustworthy); ties go to the earlier frame."""
    from units import epipolar_dy
    mf = rec.matched_frames
    idx = sorted({int(round(q * (len(mf) - 1))) for q in np.linspace(0.1, 0.9, n_candidates)})
    best, best_n = mf[idx[0]], -1
    for i in idx:
        _, _, L, R, _ = _load_half(rec, mf[i])
        n = epipolar_dy(L[..., 1], R[..., 1]).get("n", 0)
        if n > best_n:
            best, best_n = mf[i], n
    return best


def plan_dytest(recs: dict, spec: str = "") -> list:
    from recordings import runs_dir
    pairs = parse_pairs(spec, recs) if spec else [(r, pick_dytest_frame(r)) for r in recs.values()]
    return [(rec, f, {m: runs_dir() / "disp_dytest" / m / rec.name / f"{f:06d}.npz" for m in ("published", "shifted")})
            for rec, f in pairs]


def _recs(only: str) -> dict:
    from recordings import recordings
    recs = recordings()
    if only:
        if only not in recs:
            sys.exit(f"--only: unknown condition '{only}' (conditions: {', '.join(recs)})")
        recs = {only: recs[only]}
    return recs


def _estimate_line(n: int, cap: float, task: str, what: str = "pairs to run") -> str:
    from modal_common import PHASE1_CAP_USD, estimate, phase_total_usd, task_spent_usd
    return (f"{n} {what}; estimate ${estimate(n, S_PER_PAIR, LOAD_S, GPU, CPU, MEM_GIB):.2f} "
            f"(cap ${cap:.2f}, cumulative for {task}: ${task_spent_usd(task):.2f} already logged; "
            f"Phase 1: ${phase_total_usd():.2f} logged of ${PHASE1_CAP_USD:.2f})")


def _dytest_line(plan: list) -> str:
    n = 2 * len(plan)
    return "dy-test: " + _estimate_line(n, CAP_DYTEST_USD, "2b-dytest",
                                         f"runs ({len(plan)} pairs x 2: as published, vertically shifted)")


def _write_disp(path: Path, d: np.ndarray, dy: float, applied: float | None = None) -> None:
    assert d.shape == (621, 1104) and np.isfinite(d).all(), (str(path), d.shape)
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = {} if applied is None else {"dy_applied": np.float32(applied)}
    np.savez_compressed(path, disp_half=d, iscale=np.float32(ISCALE), dy_px=np.float32(dy), **extra)


def _start_meter(task: str, cap: float, n: int):
    """The Meter for one task, after the Phase 1 total and the task's cumulative cap have been checked."""
    from modal_common import Meter, check_phase_budget, clamp_to_phase, estimate
    check_phase_budget(estimate(n, S_PER_PAIR, LOAD_S, GPU, CPU, MEM_GIB))
    meter = clamp_to_phase(Meter(GPU, cap, task=task, cpu=CPU, mem_gib=MEM_GIB))
    if meter.over():
        sys.exit(f"{task}: ${meter.baseline:.2f} is already logged against its ${cap:.2f} cap, which is cumulative "
                 "across runs; nothing was started (raise the cap in the source only as a deliberate decision)")
    return meter


def _cap_exit(meter, task: str, done: int, planned: int) -> None:
    sys.exit(f"cap reached: {done}/{planned} done for {task}, ${meter.usd():.2f} of its ${meter.cap:.2f} cap "
             "(the cap is cumulative across runs, so a re-run continues only if the cap is raised)")


def _warm_up(meter, model):
    """CPU-only weights download, then the GPU class's first call (model load). Returns its info dict."""
    from modal_common import call_with_deadline
    meter.remote(call_with_deadline, fetch_weights, FETCH_DEADLINE_S, est_s=FETCH_EXPECT_S)
    return meter.remote(model.info.remote, est_s=LOAD_S + 5)


def _run_chunks(meter, model, items: list, pair_of, on_result) -> bool:
    """Send `items` in BATCH-sized calls, each only if the cap allows it. Returns True if it stopped at the cap."""
    from modal_common import CapReached, npy_load
    for i in range(0, len(items), BATCH):
        chunk = items[i:i + BATCH]
        try:
            outs, secs = meter.remote(model.disparity.remote, [pair_of(c) for c in chunk],
                                      est_s=len(chunk) * S_PER_PAIR + CALL_OVERHEAD_S)
        except CapReached as e:
            print(f"stopped: {e}; {len(items) - i} left")
            meter.status = "cap"
            return True
        meter.gpu_s += secs
        for c, b in zip(chunk, outs):
            on_result(c, npy_load(b))
        meter.n_done += len(chunk)
        print(f"{meter.n_done}/{len(items)}, ${meter.usd():.2f} so far")
    return False


def _merge_manifest(path: Path, new: list) -> list:
    """Earlier dy-test pairs stay in the manifest; a pair run again is replaced, not listed twice."""
    old = json.loads(path.read_text()) if path.exists() else []
    key = lambda p: (p["recording"], p["frame"])
    fresh = {key(p): p for p in new}
    merged = [fresh.pop(key(p), p) for p in old]       # a re-run pair keeps its place
    return merged + list(fresh.values())


def _run_dytest(recs: dict, spec: str, dry_run: bool) -> None:
    from modal_common import png
    from recordings import runs_dir
    task = "2b-dytest"
    plan = plan_dytest(recs, spec)
    print(_dytest_line(plan))
    for rec, f, _ in plan:
        print(f"  {rec.condition:24s} frame {f}")
    if dry_run:
        return
    # everything local first (one SIFT measurement per pair, all PNG encodes), then the first remote call
    manifest, slots = [], []
    for rec, f, paths in plan:
        L, R0, R1, dy, applied = prepare_pair_both(rec, f)
        manifest.append({"condition": rec.condition, "recording": rec.name, "frame": f,
                         "dy_px": None if not np.isfinite(dy) else dy, "dy_applied": applied})
        for mode, R, ap in (("published", R0, 0.0), ("shifted", R1, applied)):
            slots.append({"path": paths[mode], "dy": dy, "ap": ap, "pair": (png(L), png(R))})
    model = StereoAnywhere()
    meter = _start_meter(task, CAP_DYTEST_USD, len(slots))
    out_root = runs_dir() / "disp_dytest"
    out_root.mkdir(parents=True, exist_ok=True)

    def save(slot, d):
        _write_disp(slot["path"], d, slot["dy"], slot["ap"])

    with meter.section(task, APP_NAME, n_planned=len(slots)):
        info = _warm_up(meter, model)
        (out_root / "weights.json").write_text(json.dumps(info, indent=2, allow_nan=False))
        if not _run_chunks(meter, model, slots, lambda s: s["pair"], save):
            (out_root / "pairs.json").write_text(json.dumps(_merge_manifest(out_root / "pairs.json", manifest),
                                                            indent=1, allow_nan=False))
            print(f"{len(slots)} maps -> {out_root}; next: uv run python cli.py dy-score")
    if meter.status == "cap":
        _cap_exit(meter, task, meter.n_done, len(slots))


def _run_main(recs: dict, smoke: bool, dry_run: bool) -> None:
    from modal_common import png
    from recordings import runs_dir
    task = "1.3a-smoke" if smoke else "1.3a"
    jobs = plan_jobs(recs, smoke)
    cap = CAP_SMOKE_USD if smoke else CAP_USD
    print(_estimate_line(len(jobs), cap, task))
    missing = [] if smoke else [c for c, r in recs.items() if r.start_info is None]
    if missing:
        why = (f"no start_frames.json entry for {', '.join(missing)}: run task 1.2 (`uv run python cli.py start-frames`) "
               "first, or the static tails and start frames are silently left out of the run")
        if not dry_run:
            sys.exit(why)
        print("a real run would refuse: " + why)
    if dry_run or not jobs:
        return
    # everything local first (SIFT dy and the PNG encodes for every pair), then the first remote call
    prepared = []
    for rec, f, path in jobs:
        L, R, dy, _ = prepare_pair(rec, f)
        prepared.append({"path": path, "dy": dy, "pair": (png(L), png(R))})
    model = StereoAnywhere()
    meter = _start_meter(task, cap, len(jobs))
    (runs_dir() / "disp").mkdir(parents=True, exist_ok=True)

    def save(item, d):
        _write_disp(item["path"], d, item["dy"])

    with meter.section(task, APP_NAME, n_planned=len(jobs)):
        info = _warm_up(meter, model)
        (runs_dir() / "disp" / "weights.json").write_text(json.dumps(info, indent=2, allow_nan=False))
        print("weights sha256:", info["sha256"])
        _run_chunks(meter, model, prepared, lambda it: it["pair"], save)
    if meter.status == "cap":
        _cap_exit(meter, task, meter.n_done, len(jobs))


@app.local_entrypoint()
def main(smoke: bool = False, dry_run: bool = False, only: str = "", dy_test: bool = False, pairs: str = ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    recs = _recs(only)
    if dy_test:
        _run_dytest(recs, pairs, dry_run)
    else:
        _run_main(recs, smoke, dry_run)


def cli_main(argv=None) -> None:
    """`python modal_stereo.py --dry-run [--smoke|--dy-test] [--only c] [--pairs ...]`: nothing remote."""
    ap = argparse.ArgumentParser(prog="modal_stereo.py", description="Local dry run of the divetwin-stereo entrypoint.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--dy-test", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--pairs", default="", help="--dy-test: <condition>:<matched frame>,...")
    a = ap.parse_args(argv)
    if not a.dry_run:
        sys.exit("remote runs go through `uv run modal run modal_stereo.py [--smoke|--dy-test]`; "
                 "this entry point only does --dry-run, which never contacts Modal")
    main(smoke=a.smoke, dry_run=True, only=a.only, dy_test=a.dy_test, pairs=a.pairs)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    cli_main()
