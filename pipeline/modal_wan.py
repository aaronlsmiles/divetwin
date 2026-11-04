"""Modal app: Wan 2.2 TI2V-5B image-to-video (Apache-2.0), the open-weights engine.

    uv run python modal_wan.py --dry-run [--smoke] [--only air] [--prompt D]   # the clip list, the estimate: nothing remote
    uv run modal run modal_wan.py --smoke                                      # ONE clip (air, prompt D): task 2.4-wan-smoke
    uv run modal run modal_wan.py [--only air] [--prompt D]                    # every clip still missing: task 2.4-wan
    uv run modal run modal_wan.py --only air --prompt D --retake-reason "why"  # pay again for one existing clip

The smoke run is exempt from Gate P; the rest wait for it (runs/gates.json). --smoke is exactly air, prompt D (a retake
of that clip is allowed; --retake-reason needs the clip on disk). A capped weights fetch ends the run before the GPU starts. The full run needs an ok smoke line in the
log (otherwise it refuses and starts nothing), is re-estimated from that line, and refuses (for Aaron) if the projection
passes the task cap or Phase 2.
A file on disk that is not a valid clip is never regenerated silently: a retake (one clip, a logged reason) retires it
to runs/wan22/retired/, logs runs/retakes.jsonl and uses seed_for(spec, n). Every GPU call runs through a deadline
(the first adds the container start), so a crash-looping model load cannot bill without limit.

The model: Wan-AI/Wan2.2-TI2V-5B-Diffusers at the MODELS.md revision, through diffusers' WanImageToVideoPipeline
(its model_index has expand_timesteps true, no image encoder), bfloat16 with a float32 VAE as the model card does,
1280 x 704, 121 frames, 24 fps, 50 steps, guidance 5.0, no negative prompt (Gen-4.5 has none, so the words D, B
and N are the only steering on both engines). The input is the recording's start frame resized to 1280 x 720
(exactly as Gen-4.5's) and centre-cropped by 16 rows. One fixed seed per clip from clips.seed_for, B and N sharing
one, logged in runs/wan22/seeds.jsonl. Output: runs/wan22/<clip_id>.mp4.

Spend guards, as modal_depth.py (modal_common.Meter through spendguard.GuardedMeter): a cumulative cap per task,
Phase 2's own $5.80 total, the 25 GBP generation stop checked before every remote call, a timeout of about 3x the
expected time on every call, the weights downloaded by a CPU-only function with a deadline, the GPU class pinned
(A100-80GB, $2.50/h) so the meter's rate is exact, and one spend line however a run ends. `modal run` starts the
app on Modal before the entrypoint runs; the dry run that touches nothing remote is the plain-Python form above."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import modal

WAN_REPO = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
WAN_REV = "b8fff7315c768468a5333511427288870b2e9635"
WAN_W, WAN_H, WAN_FRAMES, WAN_FPS = 1280, 704, 121, 24
CROP_ROWS = 8                    # (720 - 704) / 2 off the top and the bottom of the 1280 x 720 start image
STEPS, GUIDANCE = 50, 5.0        # the model card's settings
WEIGHTS_JSON = "/weights/wan_weights.json"
APP_NAME = "divetwin-wan"
GPU = "A100-80GB"
PHASE = 2
CAPS = {"fetch": 0.15, "smoke": 0.70, "wan": 5.30}   # USD per task, cumulative across re-runs (sub-plan B section 5.2); wan raised from 4.50 by Aaron, 3 Nov (call 72)
TASKS = {"fetch": "2.4-wan-fetch", "smoke": "2.4-wan-smoke", "wan": "2.4-wan"}
SMOKE_CONDITION, SMOKE_PROMPT = "air", "D"      # the smoke clip: air__wan22__D__5s, always

CPU, MEM_GIB = 4, 40
# Expected durations (the estimates' own numbers); each timeout is about 3x its expected time.
LOAD_S, S_PER_CLIP, OVERHEAD_S = 300, 300, 30
FETCH_DEADLINE_S = 1800     # 34 GB from Hugging Face; a startup crash-loop would otherwise wait forever
FETCH_EXPECT_S = 600


def _ceil30(x: float) -> int:
    return int(-(-x // 30) * 30)


CLIP_TIMEOUT_S = _ceil30(3 * (S_PER_CLIP + OVERHEAD_S))      # one clip: 990 s
STARTUP_S = _ceil30(3 * LOAD_S)
FETCH_TIMEOUT_S = _ceil30(3 * FETCH_EXPECT_S)
FETCH_CPU, FETCH_MEM_GIB = 2, 4

app = modal.App(APP_NAME)
weights = modal.Volume.from_name("divetwin-weights", create_if_missing=True)

# Provisional until the smoke run builds it (MODELS.md): diffusers 0.35.1 is the first release line that has the
# Wan 2.2 TI2V transformer config; transformers 4.55.0 and huggingface_hub 0.34.4 are the pair it requires.
wan_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "libgl1", "libglib2.0-0")
    .pip_install("torch==2.5.1", "torchvision==0.20.1", index_url="https://download.pytorch.org/whl/cu124")
    .pip_install("diffusers==0.35.1", "transformers==4.55.0", "accelerate==1.10.0", "huggingface_hub==0.34.4",
                 "safetensors==0.4.5", "sentencepiece==0.2.0", "ftfy==6.3.1", "numpy<2", "Pillow==11.0.0",
                 "av==13.1.0")
)
# CPU-only: no torch, no GPU. Everything that can fail on the network happens here.
weights_image = modal.Image.debian_slim(python_version="3.11").pip_install("huggingface_hub==0.34.4")


@app.function(image=weights_image, volumes={"/weights": weights}, cpu=FETCH_CPU, memory=FETCH_MEM_GIB * 1024,
              timeout=FETCH_TIMEOUT_S)
def fetch_weights() -> dict:
    """Download the pinned Wan checkpoint into the Volume (no GPU) and record what arrived."""
    import json
    from pathlib import Path

    from huggingface_hub import snapshot_download

    path = Path(snapshot_download(WAN_REPO, revision=WAN_REV, cache_dir="/weights/hf",
                                  allow_patterns=["model_index.json", "scheduler/*", "text_encoder/*", "tokenizer/*",
                                                  "transformer/*", "vae/*"]))
    files = {str(p.relative_to(path)): p.stat().st_size for p in sorted(path.rglob("*")) if p.is_file()}
    rec = {"repo": WAN_REPO, "revision": WAN_REV, "files": files}
    Path(WEIGHTS_JSON).write_text(json.dumps(rec, indent=1))
    weights.commit()
    return rec


def encode_mp4(frames, fps: int = WAN_FPS) -> bytes:
    """uint8 RGB frames (N, H, W, 3) -> H.264 mp4 bytes (yuv420p, crf 12). PyAV, like the rest of the pipeline."""
    import io
    from fractions import Fraction

    import av
    import numpy as np
    buf = io.BytesIO()
    with av.open(buf, "w", format="mp4") as c:
        s = c.add_stream("libx264", rate=Fraction(fps, 1))
        s.height, s.width, s.pix_fmt = frames.shape[1], frames.shape[2], "yuv420p"
        s.options = {"crf": "12", "preset": "medium"}
        for f in frames:
            for pkt in s.encode(av.VideoFrame.from_ndarray(np.ascontiguousarray(f), format="rgb24")):
                c.mux(pkt)
        for pkt in s.encode():
            c.mux(pkt)
    return buf.getvalue()


@app.cls(gpu=GPU, image=wan_image, volumes={"/weights": weights.read_only()}, cpu=(CPU, CPU), memory=MEM_GIB * 1024,
         timeout=CLIP_TIMEOUT_S, startup_timeout=STARTUP_S, max_containers=1, scaledown_window=60)
class WanI2V:
    @modal.enter()
    def load(self):
        import os

        import torch
        from diffusers import AutoencoderKLWan, WanImageToVideoPipeline
        # read-only: fails at once if fetch_weights has not filled the Volume
        if not os.path.exists(WEIGHTS_JSON):
            raise FileNotFoundError(f"{WEIGHTS_JSON} is not in the divetwin-weights Volume: run fetch_weights first")
        from huggingface_hub import snapshot_download
        path = snapshot_download(WAN_REPO, revision=WAN_REV, cache_dir="/weights/hf", local_files_only=True)
        vae = AutoencoderKLWan.from_pretrained(path, subfolder="vae", torch_dtype=torch.float32)
        self.pipe = WanImageToVideoPipeline.from_pretrained(path, vae=vae, torch_dtype=torch.bfloat16).to("cuda")

    @modal.method()
    def generate(self, start_png: bytes, prompt: str, seed: int) -> tuple[bytes, float]:
        """One clip: the start frame (1280 x 704 PNG) and the prompt -> (mp4 bytes, GPU seconds)."""
        import io

        import numpy as np
        import torch
        from PIL import Image

        t0 = time.time()
        img = Image.open(io.BytesIO(start_png)).convert("RGB")
        assert img.size == (WAN_W, WAN_H), img.size
        gen = torch.Generator(device="cuda").manual_seed(int(seed))
        out = self.pipe(image=img, prompt=prompt, height=WAN_H, width=WAN_W, num_frames=WAN_FRAMES,
                        num_inference_steps=STEPS, guidance_scale=GUIDANCE, generator=gen, output_type="np").frames[0]
        frames = (np.clip(np.asarray(out), 0.0, 1.0) * 255.0).round().astype(np.uint8)
        assert frames.shape == (WAN_FRAMES, WAN_H, WAN_W, 3), frames.shape
        return encode_mp4(frames), time.time() - t0


# ---- local side --------------------------------------------------------------------------------------

def _local():
    sys.path.insert(0, str(Path(__file__).resolve().parent))


def wan_start_path(condition: str) -> Path:
    from recordings import runs_dir
    return runs_dir() / "start" / f"{condition}_wan.png"


def make_wan_start(condition: str) -> Path:
    """The 1280 x 720 start image (the same file Gen-4.5 gets) centre-cropped by 16 rows to 1280 x 704."""
    import cv2

    import runway_calls
    out = wan_start_path(condition)
    if out.exists():
        return out
    img = cv2.imread(str(runway_calls.make_start_image(condition)), cv2.IMREAD_COLOR)
    assert img.shape[:2] == (720, 1280), img.shape
    cv2.imwrite(str(out), img[CROP_ROWS:CROP_ROWS + WAN_H])
    return out


def plan_specs(smoke: bool = False, only: str = "", prompt: str = "", retake_reason: str = ""):
    """The Wan clips to make (5 s, prompts D, B, N per recording). A valid file on disk is skipped. A file that is on
    disk but invalid is never silently regenerated: it is paid for, so the plan refuses until a retake is asked for
    (`--retake-reason`, exactly one clip), which retires it and uses the clip's next seed."""
    import clips
    from recordings import RECORDING_NAMES
    if only and only not in RECORDING_NAMES:
        sys.exit(f"--only: unknown condition '{only}' (conditions: {', '.join(RECORDING_NAMES)})")
    if smoke:
        # the smoke is exactly one clip, the same one every time; --only and --prompt may only name it
        if (only and only != SMOKE_CONDITION) or (prompt and prompt != SMOKE_PROMPT):
            sys.exit(f"--smoke: the smoke clip is {SMOKE_CONDITION}, prompt {SMOKE_PROMPT} (got --only '{only}' --prompt "
                     f"'{prompt}'); run the other clips without --smoke")
        allspecs = [clips.ClipSpec(SMOKE_CONDITION, "wan22", SMOKE_PROMPT, 5)]
    else:
        allspecs = [clips.ClipSpec(c, "wan22", p, 5) for c in RECORDING_NAMES if not only or c == only
                    for p in "DBN" if not prompt or p == prompt]
    if retake_reason:
        if len(allspecs) != 1:
            sys.exit("--retake-reason pays again, so it needs exactly one clip: use --only and --prompt")
        if not clips.video_path(allspecs[0]).exists():
            sys.exit(f"--retake-reason: {allspecs[0].id} is not on disk, so there is nothing to retake; "
                     "make it without --retake-reason")
        return allspecs
    todo, blocked = [], []
    for s_ in allspecs:
        if not clips.video_path(s_).exists():
            todo.append(s_)
        elif not clips.check_clip(s_)["ok"]:
            blocked.append(f"{s_.id}: {clips.check_clip(s_)['reason']}")
    if blocked:
        sys.exit("a clip is on disk but is not the expected one (it is paid for and kept): " + "; ".join(blocked)
                 + ". Look at it, then retake it with --only <condition> --prompt <P> --retake-reason \"<why>\".")
    return todo


def _est(n: int) -> float:
    from modal_common import estimate
    return estimate(n, S_PER_CLIP + OVERHEAD_S, LOAD_S if n else 0, GPU, CPU, MEM_GIB)


def plan_line(todo: list, kind: str) -> str:
    import spendguard as sg
    from modal_common import task_spent_usd
    task = TASKS[kind]
    s = sg.spent()
    return (f"{len(todo)} Wan clips to make; estimate ${_est(len(todo)):.2f} (cap ${CAPS[kind]:.2f}, cumulative for {task}: "
            f"${task_spent_usd(task):.2f} already logged; Phase {PHASE}: ${sg.phase_spent_usd(PHASE):.2f} logged of "
            f"${sg.PHASE_TOTAL_USD[PHASE]:.2f}; the card GBP {s['total_gbp']:.2f} of the GBP {sg.GENERATION_STOP_GBP:.0f} stop)")


def _projection(todo: list, kind: str):
    """Re-estimate the full run from the smoke run's own spend line (none yet: None)."""
    import spendguard as sg
    from modal_common import rate_per_s
    if kind == "smoke":
        return None
    return sg.projection_from_smoke(TASKS["smoke"], len(todo), LOAD_S, rate_per_s(GPU, CPU, MEM_GIB),
                                    n_clips=len(todo), overhead_s=OVERHEAD_S)


def _require_gate_p(smoke: bool) -> None:
    """The finals-stage Wan clips wait for Gate P like the Gen-4.5 finals; the smoke run is exempt (it is the build test)."""
    import runway_calls
    if not smoke and "P" not in runway_calls.read_gates():
        sys.exit("Gate P (Aaron reads the probes) is not recorded: the Wan clips wait for it like the Gen-4.5 finals "
                 "(`runway_calls.py gate P --note \"...\"` after his go); only --smoke may run before it")


def _start_meter(kind: str, n: int):
    """The GPU Meter for one task, after the Phase 2 total and the task's cumulative cap have been checked."""
    import spendguard as sg
    task = TASKS[kind]
    sg.check_phase_total(PHASE, _est(n))
    meter = sg.GuardedMeter(GPU, CAPS[kind], task, PHASE, cpu=CPU, mem_gib=MEM_GIB)
    if meter.over():
        sys.exit(f"{task}: ${meter.baseline:.2f} is already logged against its ${CAPS[kind]:.2f} cap, which is cumulative "
                 "across runs; nothing was started (raise the cap in the source only as a deliberate decision)")
    return meter


def run_wan(smoke: bool = False, only: str = "", prompt: str = "", retake_reason: str = "") -> None:
    _local()
    import clips
    import spendguard as sg
    from modal_common import CapReached, call_with_deadline, task_spent_usd
    from prompts import PROMPTS
    from recordings import runs_dir
    kind = "smoke" if smoke else "wan"
    _require_gate_p(smoke)
    todo = plan_specs(smoke, only, prompt, retake_reason)
    print(plan_line(todo, kind))
    if not todo:
        return
    if not smoke:
        sg.require_projection_fits(_projection(todo, kind), task=TASKS[kind], task_cap=CAPS[kind],
                                   baseline=task_spent_usd(TASKS[kind]), phase=PHASE, n_remaining=len(todo), unit="clip")
    starts = [make_wan_start(s.condition).read_bytes() for s in todo]       # all local work before the first remote call
    _start_meter(kind, len(todo))        # refuses before the download starts if the phase total or the task cap is spent
    # The 34 GB download is CPU-only and can take ten minutes cold: it has its own meter at the CPU rate, so the
    # GPU meter below (created after it) does not bill those minutes at the A100 rate.
    fm = sg.GuardedMeter(None, CAPS["fetch"], TASKS["fetch"], PHASE, cpu=FETCH_CPU, mem_gib=FETCH_MEM_GIB)
    with fm.section(TASKS["fetch"], APP_NAME, n_planned=1):
        fm.remote(call_with_deadline, fetch_weights, FETCH_DEADLINE_S, est_s=FETCH_EXPECT_S)
        fm.n_done = 1
    if fm.status != "ok":     # Meter.section swallows CapReached: a capped fetch must not go on to the A100
        sys.exit(f"{TASKS['fetch']}: {fm.status}; the GPU was not started")
    meter = _start_meter(kind, len(todo))      # created after the download, so its clock starts at the first GPU call
    seeds_log = runs_dir() / "wan22" / "seeds.jsonl"
    with meter.section(TASKS[kind], APP_NAME, n_planned=len(todo)):
        model = WanI2V()
        for i, (spec, png) in enumerate(zip(todo, starts)):
            n_retake = clips.retake_count(spec) + (1 if retake_reason else 0)
            seed = clips.seed_for(spec, n_retake)
            est_s = (LOAD_S if i == 0 else 0) + S_PER_CLIP + OVERHEAD_S
            # A hang guard on every GPU call, widest on the first (which includes the container start and the model
            # load): a crash-looping @enter on an A100 would otherwise bill without limit (call 41's failure mode).
            deadline = (STARTUP_S if i == 0 else 0) + CLIP_TIMEOUT_S
            try:
                meter.check(est_s)
            except CapReached as e:
                print(f"stopped before {spec.id}: {e}")
                meter.status = "cap"
                break
            if retake_reason:
                clips.log_retake(spec, n_retake, retake_reason, seed, clips.retire_existing(spec))
            mp4, secs = meter.remote(call_with_deadline, model.generate, deadline, png, PROMPTS[spec.prompt], seed, est_s=est_s, units=1)
            meter.gpu_s += secs
            dest = clips.video_path(spec)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(mp4)                    # kept even if invalid: it is paid for
            with open(seeds_log, "a") as fh:
                fh.write(json.dumps({"clip": spec.id, "seed": seed, "retake": n_retake, "steps": STEPS, "guidance": GUIDANCE,
                                     "revision": WAN_REV, "gpu_s": round(secs, 1), "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
            r = clips.check_clip(spec)
            if not r["ok"]:
                raise RuntimeError(f"{spec.id}: the downloaded clip is not the expected one: {r['reason']} "
                                   f"(kept at {dest}; not retried, it is paid for)")
            meter.n_done += 1
            print(f"{spec.id}: {r['frames']} frames {r['size']}, {secs:.0f} s GPU, ${meter.usd():.2f} so far")
    if meter.status == "cap":
        sys.exit(f"cap reached: {meter.n_done}/{len(todo)} done for {meter.task}, ${meter.usd():.2f} of its "
                 f"${meter.cap:.2f} cap (cumulative across runs, so a re-run continues only if the cap is raised)")


@app.local_entrypoint()
def main(smoke: bool = False, dry_run: bool = False, only: str = "", prompt: str = "", retake_reason: str = ""):
    _local()
    if dry_run:
        _dry(smoke, only, prompt, retake_reason)
        return
    run_wan(smoke, only, prompt, retake_reason)


def _dry(smoke: bool, only: str, prompt: str, retake_reason: str) -> None:
    """The plan and, for a full run, the projection. A full run that the real run would refuse (no ok smoke line, or a
    projection that does not fit) says so and exits 1, the real refusal's code; the smoke's dry run and a full one that
    would go ahead return."""
    todo = plan_specs(smoke, only, prompt, retake_reason)
    kind = "smoke" if smoke else "wan"
    print(plan_line(todo, kind))
    proj = _projection(todo, kind)
    if proj:
        print(f"re-estimated from the smoke run: {proj['s_per_unit']:.2f} s a clip; the {len(todo)} clips are projected "
              f"at ${proj['projected_usd']:.2f}")
    if kind == "wan" and todo:
        import spendguard as sg
        from modal_common import task_spent_usd
        why = sg.projection_refusal(proj, task=TASKS[kind], task_cap=CAPS[kind], baseline=task_spent_usd(TASKS[kind]),
                                    phase=PHASE, n_remaining=len(todo), unit="clip")
        if why:
            print("the full run would be refused: " + why)
            sys.exit(1)


def cli_main(argv=None) -> None:
    """`python modal_wan.py --dry-run [--smoke] [--only c] [--prompt P]`: nothing remote."""
    ap = argparse.ArgumentParser(prog="modal_wan.py", description="Local dry run of the divetwin-wan entrypoint.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--prompt", default="", choices=["", "D", "B", "N"])
    ap.add_argument("--retake-reason", default="", help="pay again for one clip that already exists; the reason is logged")
    a = ap.parse_args(argv)
    if not a.dry_run:
        sys.exit("remote runs go through `uv run modal run modal_wan.py [--smoke]`; "
                 "this entry point only does --dry-run, which never contacts Modal")
    _local()
    _dry(a.smoke, a.only, a.prompt, a.retake_reason)


if __name__ == "__main__":
    cli_main()
