"""Modal app: Depth Anything 3 Mono-Large per frame, and SAM 2.1 video masks.

The two classes are the interface sub-plan B builds on (generated clips, tracks):
    Da3Mono().inv_depth.remote(images, out_w, out_h) -> (npy bytes, float16 (N, out_h, out_w) of 1 / z_DA3, GPU s)
        images: PNG or JPEG bytes (BGR as cv2 writes them). Inverse depth is the model's own, never
        normalised per frame (the frozen fit needs every frame on the same footing).
    Sam2Video().track.remote(jpegs, prompts) -> ({obj: npy bytes of packbits (N, H, ceil(W / 8))}, GPU s)
        prompts: [{"frame": int, "obj": str, "box": [x0, y0, x1, y1]}] in the sent frames' pixels.

Local entrypoints (run from pipeline/):
    uv run modal run modal_depth.py::smoke                 # both images build; one call each
    uv run modal run modal_depth.py::masks [--dry-run]     # task 1.2: SAM 2 on every frame of each recording
    uv run modal run modal_depth.py::floor [--dry-run]     # task 1.5: DA3 on the matched real frames
    uv run modal run modal_depth.py::selftest [--dry-run]  # task 1.7: DA3 on the self-test renders
    uv run modal run modal_depth.py::depth_clips [--smoke] [--only ids]   # task 3.1 (sub-plan B): DA3 on every clip in runs/clips_index.json
    uv run modal run modal_depth.py::track_clips [--only ids]            # task 3.1: SAM 2 tracks for the clips named in runs/clip_seeds.json

`modal run` starts the app on Modal before the entrypoint runs, even with --dry-run. The dry run that
touches nothing remote (no login, no image build, no GPU) is the plain-Python form:
    uv run python modal_depth.py <smoke|masks|floor|selftest> --dry-run [--only <condition>]

depth_clips and track_clips are Phase 3: their own caps (CLIP_CAPS), the Phase 3 total and the generation stop, via
spendguard.GuardedMeter; their spend lines carry "phase": 3. Phase 1's cap and checks above are unchanged.

Spend guards, as in modal_stereo.py (modal_common.Meter; upper bounds): each task's cap is cumulative across
re-runs, Phase 1 as a whole is held to PHASE1_CAP_USD, a call is refused when it could pass the cap, every call
has a timeout of about 3x its expected duration, the weights are downloaded by a CPU-only function (the GPU
classes only read the Volume), and every paid section writes one spend line however it ends."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import modal

DA3_REPO = "depth-anything/DA3MONO-LARGE"
DA3_REV = "f465978e618db8cc79c83b8bbf24964857db1875"
DA3_CODE = "3d835ec1a5802d64a8b8b15f817a1ab54809bfe4"
PROCESS_RES = 504  # DA3's default processing resolution (longest side); recorded with every output
SAM2_REPO = "facebook/sam2.1-hiera-large"
SAM2_REV = "665f8e2ad61cf5f53d65644ff27c8ee525124610"
SAM2_CODE = "2b90b9f5ceec907a1c18123530e92e794ad901a4"
SAM2_CFG = "configs/sam2.1/sam2.1_hiera_l.yaml"
SAM2_CKPT = "sam2.1_hiera_large.pt"
WEIGHTS_JSON = "/weights/depth_weights_sha256.json"   # written by fetch_weights
APP_NAME = "divetwin-depth"
GPU = "L40S"
CAPS = {"smoke": 0.25, "masks": 1.50, "floor": 0.75, "selftest": 0.50}  # USD per task, cumulative across re-runs
TASKS = {"smoke": "smoke", "masks": "1.2-masks", "floor": "1.5-floor", "selftest": "1.7-selftest"}
WORK_W, WORK_H = 1280, 720

# Resources both GPU classes reserve; the Meter bills the same numbers (Modal bills reserved CPU and memory).
# SAM 2 needs the memory: offload_video_to_cpu keeps ~400 frames at 1024 x 1024 in host RAM.
CPU, MEM_GIB = 4, 16
# Expected durations, the estimates' own numbers; each timeout below is about 3x its expected time.
DA3_LOAD_S, DA3_S_PER_FRAME, DA3_OVERHEAD_S, DA3_BATCH = 90, 0.25, 20, 24
SAM2_LOAD_S, SAM2_S_PER_FRAME, SAM2_OVERHEAD_S = 60, 0.15, 40
SAM2_MAX_FRAMES = 460     # S1 longest is 455 (Saltwater-pellets smtBtl-fill); one SAM 2 call is one whole recording (Aaron, 3 Nov)
FETCH_DEADLINE_S = 900    # fetch_weights gives up after this (a startup crash-loop would otherwise wait forever)
FETCH_EXPECT_S = 120


def _ceil30(x: float) -> int:
    return int(-(-x // 30) * 30)


DA3_TIMEOUT_S = max(120, _ceil30(3 * (DA3_BATCH * DA3_S_PER_FRAME + DA3_OVERHEAD_S)))      # 24 frames: 120 s
SAM2_TIMEOUT_S = _ceil30(3 * (SAM2_MAX_FRAMES * SAM2_S_PER_FRAME + SAM2_OVERHEAD_S))        # one recording: 330 s
DA3_STARTUP_S = _ceil30(3 * DA3_LOAD_S)
SAM2_STARTUP_S = _ceil30(3 * SAM2_LOAD_S)
FETCH_TIMEOUT_S = _ceil30(3 * FETCH_EXPECT_S)
FETCH_CPU, FETCH_MEM_GIB = 2, 4

app = modal.App(APP_NAME)
weights = modal.Volume.from_name("divetwin-weights", create_if_missing=True)

_torch = ("torch==2.5.1", "torchvision==0.20.1")
_cu = "https://download.pytorch.org/whl/cu124"
# Provisional until the first build (MODELS.md): floating names pinned to the releases nearest torch 2.5.1
# (29 Oct 2024); DA3 itself installs with --no-deps, then only what its inference path imports is added.
da3_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "libgl1", "libglib2.0-0")
    .pip_install(*_torch, index_url=_cu)
    .pip_install("xformers==0.0.28.post3", "numpy<2", "opencv-python-headless==4.10.0.84", "huggingface_hub==0.26.2",
                 "Pillow==11.0.0")
    .pip_install("numpy<2", "einops==0.8.0", "omegaconf==2.3.0", "addict==2.4.0", "tqdm==4.66.5", "safetensors==0.4.5",
                 "imageio==2.36.0", "matplotlib==3.9.2", "moviepy==1.0.3", "plyfile==1.1", "pycolmap==3.10.0",
                 "trimesh==4.5.0", "scipy==1.14.1", "packaging==24.1")
    .pip_install("evo==1.30.4", extra_options="--no-deps")   # pose_align imports evo.core.trajectory (numpy, scipy, packaging)
    .pip_install(f"depth-anything-3 @ git+https://github.com/ByteDance-Seed/Depth-Anything-3@{DA3_CODE}",
                 extra_options="--no-deps")
)
sam2_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "libgl1", "libglib2.0-0")
    .pip_install(*_torch, index_url=_cu)
    .pip_install("numpy<2", "opencv-python-headless==4.10.0.84", "huggingface_hub==0.26.2", "setuptools==75.1.0",
                 "wheel==0.44.0")
    .env({"SAM2_BUILD_CUDA": "0"})
    .pip_install(f"SAM-2 @ git+https://github.com/facebookresearch/sam2@{SAM2_CODE}", extra_options="--no-build-isolation")
)
# CPU-only: no torch, no GPU. Everything that can fail on the network happens here.
weights_image = modal.Image.debian_slim(python_version="3.11").pip_install("huggingface_hub==0.26.2")


@app.function(image=weights_image, volumes={"/weights": weights}, cpu=FETCH_CPU, memory=FETCH_MEM_GIB * 1024,
              timeout=FETCH_TIMEOUT_S)
def fetch_weights(which: list[str]) -> dict:
    """Download the named models' weights ("da3", "sam2") into the Volume (no GPU); record sha256 at first download."""
    import hashlib
    import json
    from pathlib import Path

    from huggingface_hub import hf_hub_download, snapshot_download

    rec = Path(WEIGHTS_JSON)
    known = json.loads(rec.read_text()) if rec.exists() else {}
    files = []
    if "da3" in which:
        files.append(Path(snapshot_download(DA3_REPO, revision=DA3_REV, cache_dir="/weights/hf")) / "model.safetensors")
    if "sam2" in which:
        files.append(Path(hf_hub_download(SAM2_REPO, SAM2_CKPT, revision=SAM2_REV, cache_dir="/weights/hf")))
    for p in files:
        if p.name not in known:
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            known[p.name] = h.hexdigest()
    rec.write_text(json.dumps(known, indent=2))
    weights.commit()
    return known


@app.cls(gpu=GPU, image=da3_image, volumes={"/weights": weights.read_only()}, cpu=(CPU, CPU), memory=MEM_GIB * 1024,
         timeout=DA3_TIMEOUT_S, startup_timeout=DA3_STARTUP_S, max_containers=1, scaledown_window=60)
class Da3Mono:
    @modal.enter()
    def load(self):
        from depth_anything_3.api import DepthAnything3
        from huggingface_hub import snapshot_download
        # read-only: fails at once if fetch_weights has not filled the Volume
        path = snapshot_download(DA3_REPO, revision=DA3_REV, cache_dir="/weights/hf", local_files_only=True)
        self.model = DepthAnything3.from_pretrained(path).to("cuda").eval()

    @modal.method()
    def inv_depth(self, images: list[bytes], out_w: int, out_h: int, process_res: int = PROCESS_RES) -> tuple[bytes, float]:
        import io

        import cv2
        import numpy as np
        from PIL import Image

        t0 = time.time()
        out = np.empty((len(images), out_h, out_w), np.float16)
        for i, b in enumerate(images):
            bgr = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
            pred = self.model.inference([Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))], process_res=process_res)
            z = np.asarray(pred.depth[0], np.float32)
            inv = 1.0 / np.maximum(z, 1e-3)
            out[i] = cv2.resize(inv, (out_w, out_h), interpolation=cv2.INTER_LINEAR).astype(np.float16)
        buf = io.BytesIO()
        np.save(buf, out)
        return buf.getvalue(), time.time() - t0


    @modal.method()
    def depth_native(self, images: list[bytes], process_res: int = PROCESS_RES) -> tuple[bytes, float]:
        """Inverse depth 1 / z at DA3's own output size, float16, for the frames of one clip (task 3.1). The
        median and the resize to the clip's grid are done locally (clipdepth.py), where the file is written."""
        import io

        import cv2
        import numpy as np
        from PIL import Image

        t0 = time.time()
        out = []
        for b in images:
            bgr = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
            pred = self.model.inference([Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))], process_res=process_res)
            z = np.asarray(pred.depth[0], np.float32)
            out.append((1.0 / np.maximum(z, 1e-3)).astype(np.float16))
        buf = io.BytesIO()
        np.save(buf, np.stack(out))
        return buf.getvalue(), time.time() - t0


@app.cls(gpu=GPU, image=sam2_image, volumes={"/weights": weights.read_only()}, cpu=(CPU, CPU), memory=MEM_GIB * 1024,
         timeout=SAM2_TIMEOUT_S, startup_timeout=SAM2_STARTUP_S, max_containers=1, scaledown_window=60)
class Sam2Video:
    @modal.enter()
    def load(self):
        from huggingface_hub import hf_hub_download
        from sam2.build_sam import build_sam2_video_predictor
        ckpt = hf_hub_download(SAM2_REPO, SAM2_CKPT, revision=SAM2_REV, cache_dir="/weights/hf", local_files_only=True)
        self.predictor = build_sam2_video_predictor(SAM2_CFG, ckpt, device="cuda")

    @modal.method()
    def track(self, jpegs: list[bytes], prompts: list[dict]) -> tuple[dict[str, bytes], float]:
        import io
        import tempfile

        import numpy as np
        import torch

        t0 = time.time()
        with tempfile.TemporaryDirectory() as d:
            for i, b in enumerate(jpegs):
                Path(d, f"{i:05d}.jpg").write_bytes(b)
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
                state = self.predictor.init_state(video_path=d, offload_video_to_cpu=True)
                masks = drive_sam2(self.predictor, state, prompts, len(jpegs), state["video_height"], state["video_width"])
        out = {}
        for n, m in masks.items():
            buf = io.BytesIO()
            np.save(buf, np.packbits(m, axis=-1))
            out[n] = buf.getvalue()
        return out, time.time() - t0


def prompt_to_half(p: dict) -> dict:
    """A seeds.json prompt (full-resolution `box` and/or `points` + `labels`) at the half grid SAM 2 runs on.
    Only the keys SAM 2 needs are kept (the `reason` stays in seeds.json)."""
    out = {"frame": int(p["frame"]), "obj": p["obj"]}
    if "box" in p:
        out["box"] = [v / 2 for v in p["box"]]
    if "points" in p:
        out["points"] = [[x / 2, y / 2] for x, y in p["points"]]
        out["labels"] = [int(v) for v in p["labels"]]
    return out


def split_prompts(prompts: list[dict]) -> tuple[list[dict], list[dict]]:
    """(conditioning, refinements). A box or a positive point conditions an untracked frame: all of these go in
    before the first propagation. A prompt with only negative points can only correct a mask SAM 2 has already
    tracked, so it is applied after the first propagation (sorted by frame)."""
    cond = [p for p in prompts if "box" in p or any(v == 1 for v in p.get("labels", []))]
    refine = sorted((p for p in prompts if not any(p is c for c in cond)), key=lambda p: p["frame"])
    return cond, refine


def drive_sam2(predictor, state, prompts: list[dict], n_frames: int, h: int, w: int) -> dict:
    """Prompts (half grid, see prompt_to_half) -> {obj: (n_frames, h, w) bool masks}.

    Conditioning prompts first, then one forward and one backward propagation from the earliest. Negative-only
    prompts then refine the tracked frames, which become conditioning frames, and SAM 2 re-propagates forward
    from the earliest of them (call 39)."""
    import numpy as np
    names = list(dict.fromkeys(p["obj"] for p in prompts))
    ids = {n: i + 1 for i, n in enumerate(names)}
    masks = {n: np.zeros((n_frames, h, w), bool) for n in names}
    cond, refine = split_prompts(prompts)
    if not cond:
        raise ValueError("no conditioning prompt: every object needs a box or a positive point first")

    def add(p):
        kw = {}
        if "box" in p:
            kw["box"] = np.asarray(p["box"], np.float32)
        if "points" in p:
            kw["points"] = np.asarray(p["points"], np.float32)
            kw["labels"] = np.asarray(p["labels"], np.int32)
        predictor.add_new_points_or_box(state, frame_idx=int(p["frame"]), obj_id=ids[p["obj"]], **kw)

    def run(start, reverse):
        for fi, oids, logits in predictor.propagate_in_video(state, start_frame_idx=start, reverse=reverse):
            for j, oid in enumerate(oids):
                masks[names[oid - 1]][fi] = (logits[j, 0] > 0).cpu().numpy()

    for p in cond:
        add(p)
    first = min(int(p["frame"]) for p in cond)
    run(first, False)
    run(first, True)
    if refine:
        # SAM 2 re-runs every non-conditioning frame on each propagation, so a click on an already tracked frame
        # is lost unless that frame becomes a conditioning frame (pinned source, sam2_video_predictor.py)
        predictor.add_all_frames_to_correct_as_cond = True
        for p in refine:
            add(p)
        run(int(refine[0]["frame"]), False)
    return masks


def _local():
    sys.path.insert(0, str(Path(__file__).resolve().parent))


def _seeds() -> dict:
    import json
    return json.loads((Path(__file__).resolve().parent / "seeds.json").read_text())


def _est(n: int, s_per_item: float, load_s: float) -> float:
    from modal_common import estimate
    return estimate(n, s_per_item, load_s, GPU, CPU, MEM_GIB)


def _line(kind: str, n_est: float, task: str) -> str:
    """The estimate and the cumulative cap, for a dry run and for the start of a real one."""
    from modal_common import PHASE1_CAP_USD, phase_total_usd, task_spent_usd
    return (f"estimate ${n_est:.2f} (cap ${CAPS[kind]:.2f}, cumulative for {task}: ${task_spent_usd(task):.2f} already "
            f"logged; Phase 1: ${phase_total_usd():.2f} logged of ${PHASE1_CAP_USD:.2f})")


def _start_meter(kind: str, est_usd: float):
    """The Meter for one task, after the Phase 1 total and the task's cumulative cap have been checked."""
    from modal_common import Meter, check_phase_budget, clamp_to_phase
    task = TASKS[kind]
    check_phase_budget(est_usd)
    meter = clamp_to_phase(Meter(GPU, CAPS[kind], task=task, cpu=CPU, mem_gib=MEM_GIB))
    if meter.over():
        sys.exit(f"{task}: ${meter.baseline:.2f} is already logged against its ${CAPS[kind]:.2f} cap, which is cumulative "
                 "across runs; nothing was started (raise the cap in the source only as a deliberate decision)")
    return meter


def _cap_exit(meter, done: int, planned: int) -> None:
    sys.exit(f"cap reached: {done}/{planned} done for {meter.task}, ${meter.usd():.2f} of its ${meter.cap:.2f} cap "
             "(the cap is cumulative across runs, so a re-run continues only if the cap is raised)")


def plan_smoke() -> str:
    est = _est(11, 0.5, 120)
    return (f"smoke: 1 DA3 frame + 10 SAM 2 frames; {_line('smoke', est, TASKS['smoke'])}; "
            "the first run also builds both images (CPU, a few cents)")


def run_smoke() -> None:
    """One DA3 frame and ten SAM 2 frames of the freshwater recording. The spend line is written however it ends."""
    _local()
    import cv2
    import numpy as np
    from modal_common import call_with_deadline, jpg, npy_load, png
    from recordings import recordings
    rec = recordings()["freshwater"]
    seed = next(p for p in _seeds()[rec.name] if p["obj"] == "bottle")
    f = int(seed["frame"])
    img = cv2.resize(cv2.imread(str(rec.left_path(f))), (WORK_W, WORK_H), interpolation=cv2.INTER_AREA)
    ks = list(range(f, min(f + 10, rec.n_frames)))  # frames f..f+9, clamped to the recording
    half = [cv2.resize(cv2.imread(str(rec.left_path(k))), (1104, 621), interpolation=cv2.INTER_AREA) for k in ks]
    box = [v / 2 for v in seed["box"]]
    meter = _start_meter("smoke", _est(1 + len(ks), 0.5, 120))
    da3_s = DA3_LOAD_S + DA3_S_PER_FRAME + DA3_OVERHEAD_S
    sam_s = SAM2_LOAD_S + len(ks) * SAM2_S_PER_FRAME + SAM2_OVERHEAD_S
    with meter.section(TASKS["smoke"], APP_NAME, n_planned=1 + len(ks)):
        meter.remote(call_with_deadline, fetch_weights, FETCH_DEADLINE_S, ["da3", "sam2"], est_s=FETCH_EXPECT_S)
        b, secs = meter.remote(Da3Mono().inv_depth.remote, [png(img)], WORK_W, WORK_H, est_s=da3_s)
        meter.gpu_s += secs
        meter.n_done += 1
        inv = npy_load(b)
        print("DA3", inv.shape, inv.dtype, float(np.nanmin(inv)), float(np.nanmax(inv)), f"{secs:.1f}s")
        assert inv.shape == (1, WORK_H, WORK_W) and np.isfinite(inv).all() and (inv > 0).all()
        # the cap is checked again, with this call's expected cost, before SAM 2 starts
        masks, secs = meter.remote(Sam2Video().track.remote, [jpg(h) for h in half],
                                   [{"frame": 0, "obj": "bottle", "box": box}], est_s=sam_s)
        meter.gpu_s += secs
        meter.n_done += len(ks)
        m = np.unpackbits(npy_load(masks["bottle"]), axis=-1, count=1104).astype(bool)
        print("SAM2", m.shape, "area per frame", m.sum(axis=(1, 2)).tolist(), f"{secs:.1f}s")
        assert m.shape == (len(ks), 621, 1104) and m[0].sum() > 500
    if meter.status == "cap":
        _cap_exit(meter, meter.n_done, 1 + len(ks))


@app.local_entrypoint()
def smoke(dry_run: bool = False):
    _local()
    print(plan_smoke())
    if dry_run:
        return
    run_smoke()


def plan_masks(only: str = ""):
    """(recordings still to do, frames, the one-line estimate). Local only."""
    from recordings import recordings, runs_dir
    recs = {k: v for k, v in recordings().items() if not only or k == only}
    todo = [r for r in recs.values() if not (runs_dir() / "masks" / f"{r.name}.npz").exists()]
    n = sum(r.n_frames for r in todo)
    est = _est(n, SAM2_S_PER_FRAME, SAM2_LOAD_S * len(todo))
    return todo, n, f"{len(todo)} recordings, {n} frames; {_line('masks', est, TASKS['masks'])}"


def run_masks(only: str = "") -> None:
    """Task 1.2: SAM 2.1 tracks of the bottle and the hand through every frame, at half resolution."""
    _local()
    import cv2
    import numpy as np
    from modal_common import CapReached, call_with_deadline, jpg, npy_load
    from recordings import runs_dir
    todo, n, line = plan_masks(only)
    print(line)
    if not todo:
        return
    too_long = [r.name for r in todo if r.n_frames > SAM2_MAX_FRAMES]
    if too_long:
        sys.exit(f"{too_long}: more than {SAM2_MAX_FRAMES} frames; the {SAM2_TIMEOUT_S} s call timeout was sized for that")
    seeds = _seeds()
    meter = _start_meter("masks", _est(n, SAM2_S_PER_FRAME, SAM2_LOAD_S * len(todo)))
    with meter.section(TASKS["masks"], APP_NAME, n_planned=n):
        meter.remote(call_with_deadline, fetch_weights, FETCH_DEADLINE_S, ["sam2"], est_s=FETCH_EXPECT_S)
        model = Sam2Video()
        for i, rec in enumerate(todo):
            prompts = [prompt_to_half(p) for p in seeds[rec.name]]
            frames = [jpg(cv2.resize(cv2.imread(str(rec.left_path(k))), (1104, 621), interpolation=cv2.INTER_AREA))
                      for k in range(rec.n_frames)]
            est_s = (SAM2_LOAD_S if i == 0 else 0) + rec.n_frames * SAM2_S_PER_FRAME + SAM2_OVERHEAD_S
            try:
                out, secs = meter.remote(model.track.remote, frames, prompts, est_s=est_s)
            except CapReached as e:
                print(f"stopped before {rec.name}: {e}")
                meter.status = "cap"
                break
            meter.gpu_s += secs
            packed = {k: npy_load(v) for k, v in out.items()}
            for name in ("bottle", "hand"):
                packed.setdefault(name, np.packbits(np.zeros((rec.n_frames, 621, 1104), bool), axis=-1))
            (runs_dir() / "masks").mkdir(parents=True, exist_ok=True)
            np.savez_compressed(runs_dir() / "masks" / f"{rec.name}.npz", width=1104, **packed)
            meter.n_done += rec.n_frames
            print(f"{rec.name}: {rec.n_frames} frames, {secs:.0f}s, ${meter.usd():.2f} so far")
    if meter.status == "cap":
        _cap_exit(meter, meter.n_done, n)


@app.local_entrypoint()
def masks(dry_run: bool = False, only: str = ""):
    _local()
    if dry_run:
        print(plan_masks(only)[-1])
        return
    run_masks(only)


def _da3_batches(images: list[bytes], meter, out_w=WORK_W, out_h=WORK_H, batch: int = DA3_BATCH):
    """DA3 inverse depth for `images`, `batch` frames per call, each call only if the cap allows it.
    Returns (array, False), or (None, True) when the cap stopped it (nothing is half-written); frames already
    sent are counted in meter.n_done either way."""
    import numpy as np
    from modal_common import CapReached, call_with_deadline, npy_load
    model = Da3Mono()
    parts = []
    for i in range(0, len(images), batch):
        chunk = images[i:i + batch]
        est_s = (0 if getattr(meter, "warm", False) else DA3_LOAD_S) + len(chunk) * DA3_S_PER_FRAME + DA3_OVERHEAD_S
        try:
            b, secs = meter.remote(model.inv_depth.remote, chunk, out_w, out_h, est_s=est_s)
        except CapReached as e:
            print(f"stopped after {i} frames of this set: {e}; nothing written for it")
            return None, True
        meter.warm = True
        meter.gpu_s += secs
        meter.n_done += len(chunk)
        parts.append(npy_load(b))
    return np.concatenate(parts), False


def plan_floor(only: str = ""):
    from recordings import recordings, runs_dir
    recs = {k: v for k, v in recordings().items() if not only or k == only}
    todo = [r for r in recs.values() if not (runs_dir() / "da3" / "floor" / f"{r.name}.npz").exists()]
    n = sum(len(r.matched_frames) for r in todo)
    return todo, n, f"{n} frames; {_line('floor', _est(n, DA3_S_PER_FRAME, 90), TASKS['floor'])}"


def run_floor(only: str = "") -> None:
    """Task 1.5: DA3 on every matched real left frame, on the 1280 x 720 work grid."""
    _local()
    import cv2
    import numpy as np
    from modal_common import call_with_deadline, png
    from recordings import runs_dir
    todo, n, line = plan_floor(only)
    print(line)
    if not todo:
        return
    meter = _start_meter("floor", _est(n, DA3_S_PER_FRAME, 90))
    with meter.section(TASKS["floor"], APP_NAME, n_planned=n):
        meter.remote(call_with_deadline, fetch_weights, FETCH_DEADLINE_S, ["da3"], est_s=FETCH_EXPECT_S)
        for rec in todo:
            frames = rec.matched_frames
            imgs = [png(cv2.resize(cv2.imread(str(rec.left_path(k))), (WORK_W, WORK_H), interpolation=cv2.INTER_AREA))
                    for k in frames]
            inv, capped = _da3_batches(imgs, meter)
            if capped:
                meter.status = "cap"
                break
            (runs_dir() / "da3" / "floor").mkdir(parents=True, exist_ok=True)
            np.savez_compressed(runs_dir() / "da3" / "floor" / f"{rec.name}.npz", frames=np.array(frames), inv=inv,
                                process_res=PROCESS_RES)
            print(f"{rec.name}: {len(frames)} frames, ${meter.usd():.2f} so far")
    if meter.status == "cap":
        _cap_exit(meter, meter.n_done, n)


@app.local_entrypoint()
def floor(dry_run: bool = False, only: str = ""):
    _local()
    if dry_run:
        print(plan_floor(only)[-1])
        return
    run_floor(only)


def plan_selftest(only: str = ""):
    from recordings import recordings, runs_dir
    recs = {k: v for k, v in recordings().items() if not only or k == only}
    sets = []
    for rec in recs.values():
        d = runs_dir() / "selftest" / rec.name
        out = runs_dir() / "da3" / "selftest" / f"{rec.name}.npz"
        if not out.exists():
            sets.append((rec, sorted(d.glob("frame_*.png")), out))
    n = sum(len(f) for _, f, _ in sets)
    line = f"{n} renders; {_line('selftest', _est(n, DA3_S_PER_FRAME, 90), TASKS['selftest'])}"
    if sets and n == 0:
        line += "; no renders on disk yet: run `uv run python cli.py selftest-prep` first"
    return sets, n, line


def run_selftest(only: str = "") -> None:
    """Task 1.7: DA3 on the self-test renders written by `python cli.py selftest-prep`."""
    _local()
    import numpy as np
    from modal_common import call_with_deadline
    sets, n, line = plan_selftest(only)
    print(line)
    if not sets:
        return
    assert all(len(f) == 49 for _, f, _ in sets), "run `python cli.py selftest-prep` first"
    meter = _start_meter("selftest", _est(n, DA3_S_PER_FRAME, 90))
    with meter.section(TASKS["selftest"], APP_NAME, n_planned=n):
        meter.remote(call_with_deadline, fetch_weights, FETCH_DEADLINE_S, ["da3"], est_s=FETCH_EXPECT_S)
        for rec, files, out in sets:
            inv, capped = _da3_batches([f.read_bytes() for f in files], meter)
            if capped:
                meter.status = "cap"
                break
            out.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(out, inv=inv, process_res=PROCESS_RES)
            print(f"{rec.name}: {len(files)} renders, ${meter.usd():.2f} so far")
    if meter.status == "cap":
        _cap_exit(meter, meter.n_done, n)


@app.local_entrypoint()
def selftest(dry_run: bool = False, only: str = ""):
    _local()
    if dry_run:
        print(plan_selftest(only)[-1])
        return
    run_selftest(only)


# ---- Phase 3 (sub-plan B, task 3.1): DA3 and SAM 2 on the generated clips -----------------------------------------

CLIP_PHASE = 3
CLIP_CAPS = {"smoke": 0.25, "depth": 1.70, "tracks": 0.40}   # USD per task, cumulative; the Phase 3 total ($2.00) binds first
CLIP_TASKS = {"smoke": "3.1-depth-smoke", "depth": "3.1-depth", "tracks": "3.1-sam2"}
SMOKE_CLIP = "air__gen45__D__5s"     # what `--smoke` runs when it has no --only, if it is indexed and still lacks depth


def _clip_est(n_frames: int, n_clips: int, per_frame: float = DA3_S_PER_FRAME, load: float = DA3_LOAD_S) -> float:
    """spendguard.depth_est_usd, the one cost model the hunt's reserve shares."""
    import spendguard as sg
    return sg.depth_est_usd(n_frames, n_clips, per_frame, load)


def _clip_projection(n_frames: int, smoke: bool, n_clips: int):
    """The full run re-estimated from the depth smoke run's own spend line: the load, the warm rate per frame, and the
    local work per clip (decode, encode, median, savez, check_depth) for `n_clips` clips. None before the smoke, or for
    the smoke."""
    import spendguard as sg
    from modal_common import rate_per_s
    if smoke:
        return None
    return sg.projection_from_smoke(CLIP_TASKS["smoke"], n_frames, DA3_LOAD_S, rate_per_s(GPU, CPU, MEM_GIB),
                                    n_clips=n_clips, overhead_s=DA3_OVERHEAD_S)


def _clip_line(est: float, kind: str) -> str:
    import spendguard as sg
    from modal_common import task_spent_usd
    task, s = CLIP_TASKS[kind], sg.spent()
    return (f"estimate ${est:.2f} (cap ${CLIP_CAPS[kind]:.2f}, cumulative for {task}: ${task_spent_usd(task):.2f} already "
            f"logged; Phase {CLIP_PHASE}: ${sg.phase_spent_usd(CLIP_PHASE):.2f} logged of ${sg.PHASE_TOTAL_USD[CLIP_PHASE]:.2f}; "
            f"the card GBP {s['total_gbp']:.2f} of the GBP {sg.DEPTH_STOP_GBP:.0f} stop)")


def plan_clips(smoke: bool = False, only: str = "", write_index: bool = False):
    """(clips still to do, frames, the one-line estimate). The clips are the valid finals and hunt takes on disk (what
    runs/clips_index.json lists; it is rewritten only when `write_index`, so a dry run touches no file); a clip is done
    when check_depth says its npz is valid. The smoke is one clip: with no --only it is SMOKE_CLIP (air, Gen-4.5, D) when
    that clip is indexed and lacks depth, else the first clip still to do."""
    import clipdepth
    import clips
    if write_index:
        idx = clips.rebuild_clips_index()["index"]
    else:
        idx = [s_.id for s_ in clips.scan_clips()[0] if s_.in_finals_index]
    want = {x for x in only.split(",") if x}
    unknown = want - set(idx)
    if unknown:
        sys.exit(f"--only: not in clips_index.json: {', '.join(sorted(unknown))}")
    todo = [clips.parse_clip_id(c) for c in idx if (not want or c in want) and not clipdepth.check_depth(clips.parse_clip_id(c))["ok"]]
    if smoke:
        first = [s_ for s_ in todo if s_.id == SMOKE_CLIP] if not want else []
        todo = first or todo[:1]
    n = sum(clips.expected_frames(s) for s in todo)
    kind = "smoke" if smoke else "depth"
    return todo, n, f"{len(todo)} clips, {n} frames; {_clip_line(_clip_est(n, len(todo)), kind)}"


def _clip_meter(kind: str, est_usd: float):
    import spendguard as sg
    task = CLIP_TASKS[kind]
    sg.check_phase_total(CLIP_PHASE, est_usd)
    meter = sg.GuardedMeter(GPU, CLIP_CAPS[kind], task, CLIP_PHASE, cpu=CPU, mem_gib=MEM_GIB, stop_gbp=sg.DEPTH_STOP_GBP)
    if meter.over():
        sys.exit(f"{task}: ${meter.baseline:.2f} is already logged against its ${CLIP_CAPS[kind]:.2f} cap, which is "
                 "cumulative across runs; nothing was started (raise the cap in the source only as a deliberate decision)")
    return meter


def _native_depth(model, jp: list[bytes], meter):
    """DA3 inverse depth at its own size for one clip's frames, DA3_BATCH frames per call (each call within the
    class timeout), each call only if the caps allow it. Returns (array, False) or (None, True) when a cap stopped it."""
    import numpy as np
    from modal_common import CapReached, npy_load
    parts = []
    for i in range(0, len(jp), DA3_BATCH):
        chunk = jp[i:i + DA3_BATCH]
        est_s = (0 if meter.warm else DA3_LOAD_S) + len(chunk) * DA3_S_PER_FRAME + DA3_OVERHEAD_S
        try:
            b, secs = meter.remote(model.depth_native.remote, chunk, PROCESS_RES, est_s=est_s, units=len(chunk))
        except CapReached as e:
            print(f"stopped after {i} frames of this clip: {e}; nothing written for it")
            return None, True
        meter.warm = True
        meter.gpu_s += secs
        parts.append(npy_load(b))
    return np.concatenate(parts), False


def run_clips(smoke: bool = False, only: str = "") -> None:
    """Task 3.1: DA3 on every frame of each clip -> 5-frame median -> runs/da3/clips/<id>.npz (inv, float16, the clip's grid)."""
    _local()
    import clipdepth
    import clips
    from modal_common import call_with_deadline, jpg
    todo, n, line = plan_clips(smoke, only, write_index=True)
    print(line)
    if not todo:
        return
    kind = "smoke" if smoke else "depth"
    if not smoke:
        import spendguard as sg
        from modal_common import task_spent_usd
        sg.require_projection_fits(_clip_projection(n, smoke, len(todo)), task=CLIP_TASKS[kind], task_cap=CLIP_CAPS[kind],
                                   baseline=task_spent_usd(CLIP_TASKS[kind]), phase=CLIP_PHASE, n_remaining=n, unit="frame")
    meter = _clip_meter(kind, _clip_est(n, len(todo)))
    done = []
    with meter.section(CLIP_TASKS[kind], APP_NAME, n_planned=n):
        meter.remote(call_with_deadline, fetch_weights, FETCH_DEADLINE_S, ["da3"], est_s=FETCH_EXPECT_S)
        model = Da3Mono()
        for spec in todo:
            frames = _read_clip(spec)
            jp = [jpg(f) for f in frames]
            native, capped = _native_depth(model, jp, meter)
            if capped:
                meter.status = "cap"
                break
            if len(native) != len(frames):
                raise RuntimeError(f"{spec.id}: {len(native)} depth maps came back for {len(frames)} frames")
            w, h = clips.GRID[spec.engine]
            clipdepth.write_depth_npz(spec, clipdepth.process(native, w, h), meta={"native": list(native.shape[1:])})
            r = clipdepth.check_depth(spec)
            if not r["ok"]:
                raise RuntimeError(f"{spec.id}: the depth file is not the contract's: {r['reason']}")
            meter.n_done += len(frames)
            done.append(spec.id)
            print(f"{spec.id}: {len(frames)} frames, ${meter.usd():.2f} so far")
    clips.rebuild_clips_index()
    if meter.status == "cap":
        _cap_exit(meter, meter.n_done, n)


def _read_clip(spec):
    from dive import read_video
    import clips
    return read_video(clips.video_path(spec))


def plan_tracks(only: str = ""):
    """(clips with seeds and a valid depth file, frames, the one-line estimate)."""
    import clipdepth
    import clips
    seeds = clipdepth.load_clip_seeds()
    want = {x for x in only.split(",") if x}
    todo = []
    for cid in seeds:
        spec = clips.parse_clip_id(cid)
        if want and cid not in want:
            continue
        if not clipdepth.check_depth(spec)["ok"]:
            sys.exit(f"{cid}: has a seed but no valid depth file yet: run `modal run modal_depth.py::depth_clips` first")
        todo.append(spec)
    n = sum(clips.expected_frames(s) for s in todo)
    est = _est(n, SAM2_S_PER_FRAME, SAM2_LOAD_S + len(todo) * SAM2_OVERHEAD_S) if todo else 0.0     # nothing to track: nothing to pay
    note = "" if seeds else " (no runs/clip_seeds.json: no clip is tracked, which is the default)"
    return todo, n, f"{len(todo)} clips to track, {n} frames; {_clip_line(est, 'tracks')}{note}"


def run_tracks(only: str = "") -> None:
    """Task 3.1: SAM 2 tracks for the clips named in runs/clip_seeds.json; their union is stored as `moving`."""
    _local()
    import numpy as np
    import clipdepth
    import clips
    from modal_common import CapReached, call_with_deadline, jpg, npy_load
    todo, n, line = plan_tracks(only)
    print(line)
    if not todo:
        return
    seeds = clipdepth.load_clip_seeds()
    est = _est(n, SAM2_S_PER_FRAME, SAM2_LOAD_S + len(todo) * SAM2_OVERHEAD_S)
    meter = _clip_meter("tracks", est)
    with meter.section(CLIP_TASKS["tracks"], APP_NAME, n_planned=n):
        meter.remote(call_with_deadline, fetch_weights, FETCH_DEADLINE_S, ["sam2"], est_s=FETCH_EXPECT_S)
        model = Sam2Video()
        for i, spec in enumerate(todo):
            frames = _read_clip(spec)
            est_s = (SAM2_LOAD_S if i == 0 else 0) + len(frames) * SAM2_S_PER_FRAME + SAM2_OVERHEAD_S
            try:
                out, secs = meter.remote(model.track.remote, [jpg(f) for f in frames], seeds[spec.id], est_s=est_s)
            except CapReached as e:
                print(f"stopped before {spec.id}: {e}")
                meter.status = "cap"
                break
            meter.gpu_s += secs
            w, h = clips.GRID[spec.engine]
            moving = clipdepth.union_masks({k: npy_load(v) for k, v in out.items()})
            inv = np_load_inv(spec)
            clipdepth.write_depth_npz(spec, inv, np.unpackbits(moving, axis=-1, count=w).astype(bool),
                                      meta={"tracked_objects": sorted(out)})
            r = clipdepth.check_depth(spec)
            if not r["ok"]:
                raise RuntimeError(f"{spec.id}: the depth file with tracks is not the contract's: {r['reason']}")
            meter.n_done += len(frames)
            print(f"{spec.id}: tracked {sorted(out)}, ${meter.usd():.2f} so far")
    if meter.status == "cap":
        _cap_exit(meter, meter.n_done, n)


def np_load_inv(spec):
    import numpy as np
    import clips
    with np.load(clips.depth_path(spec)) as z:
        return z["inv"]


def _dry_clips(smoke: bool, only: str) -> None:
    """The estimate and, for the full run, the projection from the smoke line. A full run that the real run would refuse
    (no ok smoke line, or a projection that does not fit) says so and exits 1, the real refusal's code; the smoke's dry
    run and a full one that would go ahead return. Writes no file (not even clips_index.json)."""
    todo, n, line = plan_clips(smoke, only)
    print(line)
    proj = _clip_projection(n, smoke, len(todo))
    if proj:
        print(f"re-estimated from the smoke run: {proj['s_per_unit']:.2f} s a frame; the {n} frames are projected at "
              f"${proj['projected_usd']:.2f}")
    if not smoke and todo:
        import spendguard as sg
        from modal_common import task_spent_usd
        why = sg.projection_refusal(proj, task=CLIP_TASKS["depth"], task_cap=CLIP_CAPS["depth"],
                                    baseline=task_spent_usd(CLIP_TASKS["depth"]), phase=CLIP_PHASE, n_remaining=n,
                                    unit="frame")
        if why:
            print("the full run would be refused: " + why)
            sys.exit(1)


@app.local_entrypoint()
def depth_clips(dry_run: bool = False, smoke: bool = False, only: str = ""):
    _local()
    if dry_run:
        _dry_clips(smoke, only)
        return
    run_clips(smoke, only)


@app.local_entrypoint()
def track_clips(dry_run: bool = False, only: str = ""):
    _local()
    if dry_run:
        print(plan_tracks(only)[-1])
        return
    run_tracks(only)


def cli_main(argv=None) -> None:
    """`python modal_depth.py <entry> --dry-run`: the estimate and the work list, nothing remote."""
    ap = argparse.ArgumentParser(prog="modal_depth.py", description="Local dry runs of the divetwin-depth entrypoints.")
    ap.add_argument("entry", choices=["smoke", "masks", "floor", "selftest", "clips", "tracks"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="clips: the first clip only (task 3.1-depth-smoke)")
    ap.add_argument("--only", default="", help="one condition, e.g. air (clips and tracks: comma-separated clip ids)")
    a = ap.parse_args(argv)
    if not a.dry_run:
        sys.exit(f"remote runs go through `uv run modal run modal_depth.py::{a.entry}`; "
                 "this entry point only does --dry-run, which never contacts Modal")
    _local()
    if a.entry == "clips":
        _dry_clips(a.smoke, a.only)
    elif a.entry == "tracks":
        print(plan_tracks(a.only)[-1])
    else:
        print(plan_smoke() if a.entry == "smoke" else {"masks": plan_masks, "floor": plan_floor,
                                                      "selftest": plan_selftest}[a.entry](a.only)[-1])


if __name__ == "__main__":
    cli_main()
