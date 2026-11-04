"""Gen-4.5 calls through tools/runway/runway.sh: probes, finals, long dives and the hunt.

    uv run python runway_calls.py probes            # the plan only: clips, seeds, credits, the command; nothing is sent
    uv run python runway_calls.py probes --estimate # runway.sh's own estimate for each clip (no --yes: exit 3, nothing sent)
    uv run python runway_calls.py probes --yes      # pay (Aaron's go): one clip at a time, the 25 GBP stop checked before each
    uv run python runway_calls.py finals|long [--only air] [--prompt D] [--yes]        # need Gate P (gate P --note ...)
    uv run python runway_calls.py hunt --condition air --take 3 [--yes]                # needs Gate H for that condition
    uv run python runway_calls.py fetch --clip air__gen45__D__5s [--task ID]           # free: re-download a timed-out task
    uv run python runway_calls.py status

Every call gets --yes, --max-credits (30 for 2 s, 70 for 5 s, 130 for 10 s), a fixed logged --seed and
--log prototypes/divetwin/spend.jsonl. The prompt text comes only from prompts.PROMPTS. The start image is the
real left frame at start_frames.json[rec]["start"], a pure resize to 1280x720 (mapping.FILL_1280x720), at
runs/start/<condition>.png. A clip is never paid for twice: a valid mp4 on disk is skipped, a finished or
timed-out task is fetched (free), and anything else that needs a second payment takes --retake-reason.
Exit codes: 0 ok, 1 failed or invalid file, 3 Runway refused, 4 task still running, 7 generation stop, 2 usage."""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import cv2

import clips
import spendguard as sg
from clips import ClipSpec, check_clip, log_retake, retake_count, retire_existing, seed_for, video_path
from prompts import PROMPTS
from recordings import RECORDING_NAMES, recordings, runs_dir

STUDIO = Path(os.environ.get("STUDIO_ROOT", Path(__file__).resolve().parents[3]))
RUNWAY_SH = STUDIO / "tools" / "runway" / "runway.sh"
MODEL, RATIO, SIZE = "gen4.5", "1280:720", (1280, 720)
CREDITS_PER_S = 12
MAX_CREDITS = {2: 30, 5: 70, 10: 130}          # per call, by length: the estimate plus a little headroom
MAX_INLINE_BYTES = 3_300_000                    # runway_gen._data_uri inlines up to this; bigger needs Pillow
EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_REFUSED, EXIT_PENDING = 0, 1, 2, 3, 4
RETAKE_CREDITS_MAX = 300     # master section 5: "Runway retakes (logged reason only) <= 300 credits"
HUNT_CREDITS_MAX = 600       # master task 2.6: 10 takes or 600 credits, whichever comes first


def credits(seconds: int) -> int:
    return CREDITS_PER_S * seconds


def start_image_path(condition: str) -> Path:
    return runs_dir() / "start" / f"{condition}.png"


def make_start_image(condition: str) -> Path:
    """The recording's start frame (task 1.2) resized to 1280x720 and written as a PNG; skipped when it exists."""
    out = start_image_path(condition)
    if out.exists():
        return out
    rec = recordings()[condition]
    img = cv2.imread(str(rec.left_path(rec.start_frame)), cv2.IMREAD_COLOR)
    if img is None or img.shape[:2] != (1242, 2208):
        raise RuntimeError(f"{condition}: start frame is {None if img is None else img.shape}, expected 1242x2208")
    small = cv2.resize(img, SIZE, interpolation=cv2.INTER_AREA)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), small)
    if out.stat().st_size > MAX_INLINE_BYTES:
        out.unlink()
        raise RuntimeError(f"{condition}: the start PNG is over {MAX_INLINE_BYTES} bytes; runway_gen would need Pillow")
    return out


def _log_arg() -> str:
    log = sg.runway_log_path().resolve()
    try:
        return str(log.relative_to(STUDIO.resolve()))
    except ValueError:
        return str(log)


def build_command(spec: ClipSpec, seed: int, *, yes: bool = True) -> list[str]:
    """The exact runway.sh argv for one clip. `yes=False` is the estimate form: runway_gen prints its estimate
    and exits 3 without sending anything."""
    text = PROMPTS[spec.prompt]
    assert len(text) <= 1000
    argv = [str(RUNWAY_SH), "video", "--model", MODEL, "--image", str(start_image_path(spec.condition)),
            "--prompt", text, "--duration", str(spec.seconds), "--ratio", RATIO, "--seed", str(seed),
            "--out", str(video_path(spec)), "--max-credits", str(MAX_CREDITS[spec.seconds]), "--log", _log_arg()]
    return argv + (["--yes"] if yes else [])


def build_fetch(task_id: str, spec: ClipSpec) -> list[str]:
    return [str(RUNWAY_SH), "fetch", "--task", task_id, "--out", str(video_path(spec)), "--log", _log_arg()]


# ---- plans for each batch ----------------------------------------------------------------------------

def plan_specs(batch: str, only: str = "", prompt: str = "", condition: str = "", take: int = 0) -> list[ClipSpec]:
    conds = [c for c in RECORDING_NAMES if not only or c == only]
    if only and not conds:
        raise SystemExit(f"--only: unknown condition {only!r} ({', '.join(RECORDING_NAMES)})")
    prompts = [p for p in "DBN" if not prompt or p == prompt]
    if batch == "probes":
        return [ClipSpec(c, "gen45", p, 2, "probe") for c in conds for p in prompts]
    if batch == "finals":
        return [ClipSpec(c, "gen45", p, 5) for c in conds for p in prompts]
    if batch == "long":
        return [ClipSpec(c, "gen45", "D", 10) for c in conds]
    if batch == "hunt":
        return [ClipSpec(condition, "gen45", "B", 5, "hunt", take)]
    raise SystemExit(f"unknown batch {batch!r}")


# ---- gates (Aaron's word, written down) ---------------------------------------------------------------

def gates_path() -> Path:
    return runs_dir() / "gates.json"


def read_gates() -> dict:
    p = gates_path()
    return json.loads(p.read_text()) if p.exists() else {}


def record_gate(name: str, note: str, **extra) -> dict:
    g = read_gates()
    g[name] = {"note": note, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **extra}
    gates_path().parent.mkdir(parents=True, exist_ok=True)
    gates_path().write_text(json.dumps(g, indent=1) + "\n")
    return g


def require_gate(batch: str, specs: list[ClipSpec]) -> None:
    g = read_gates()
    if batch in ("finals", "long") and "P" not in g:
        raise SystemExit("Gate P (Aaron reads the probes) is not recorded: `runway_calls.py gate P --note \"…\"` "
                         "after his go; the finals do not start without it")
    if batch == "hunt":
        h = g.get("H")
        if not h or not h.get("definition"):
            raise SystemExit("Gate H (the hunt's recording and its frozen definition of an invention) is not recorded: "
                             "`runway_calls.py gate H --condition <c> --definition-file <f>` after Aaron's word")
        if specs[0].condition != h["condition"]:
            raise SystemExit(f"the hunt is on {h['condition']} (Gate H), not {specs[0].condition}")


# ---- the master plan's Runway budget lines, enforced -------------------------------------------------------

def _clip_calls() -> list[tuple[ClipSpec, dict]]:
    """(clip, call) for every logged call whose --out is a clip file, in log order."""
    out = []
    for c in sg.runway_calls():
        if not c["out"]:
            continue
        try:
            out.append((clips.parse_clip_id(Path(c["out"]).stem), c))
        except ValueError:
            continue
    return out


def retake_credits_spent() -> float:
    """Credits counted for every call after a clip's first: the retakes."""
    seen, total = set(), 0.0
    for spec, c in _clip_calls():
        if spec.id in seen:
            total += c["counted"]
        seen.add(spec.id)
    return total


def hunt_spent() -> tuple[float, set[str]]:
    """(credits counted for the hunt's calls, the hunt takes that have been called)."""
    calls = [(s, c) for s, c in _clip_calls() if s.kind == "hunt"]
    return sum(c["counted"] for _, c in calls), {s.id for s, _ in calls}


def budget_refusal(spec: ClipSpec, retake: bool) -> str | None:
    """Why a paid call must not start, if one of the master plan's budget lines would be passed; else None."""
    cr = credits(spec.seconds)
    if retake and retake_credits_spent() + cr > RETAKE_CREDITS_MAX:
        return (f"retakes have used {retake_credits_spent():.0f} of the {RETAKE_CREDITS_MAX} credits the master plan "
                f"allows; one more ({cr}) would pass it")
    if spec.kind == "hunt":
        spent, takes = hunt_spent()
        if spent + cr > HUNT_CREDITS_MAX:
            return f"the hunt has used {spent:.0f} of its {HUNT_CREDITS_MAX} credits; one more ({cr}) would pass them"
        if spec.id not in takes and len(takes) >= clips.HUNT_MAX_TAKES:
            return f"the hunt already has {len(takes)} takes, its limit"
    return None


# ---- what to do about one clip ----------------------------------------------------------------------

def action_for(spec: ClipSpec, retake_reason: str = "") -> dict:
    """{'do': 'skip'|'fetch'|'pay'|'refuse', 'why': str, 'task': id|None, 'retake': int}.
    Reads the mp4 on disk and the last logged call whose --out is this clip's file."""
    path = video_path(spec)
    n_retakes = retake_count(spec)
    # match on the file's name and engine directory, not the logged absolute path: a different DIVETWIN_RUNS must never
    # hide a pending call and so cause a second payment
    mine = [c for c in sg.runway_calls()
            if c["out"] and Path(c["out"]).stem == spec.id and Path(c["out"]).parent.name == spec.engine]
    last = mine[-1] if mine else None
    chk = check_clip(spec) if path.exists() else None
    out = {"do": "pay", "why": "no earlier call for this clip", "task": None, "retake": n_retakes}
    if chk and chk["ok"] and not retake_reason:
        return {**out, "do": "skip", "why": "a valid mp4 is already on disk"}
    if retake_reason and last is not None and last["state"] == "pending":
        return {**out, "do": "refuse", "why": f"its last call (task {last['task_id']}) is still pending: fetch it first "
                                               "(`runway_calls.py fetch --clip <id> --yes`), a retake would pay for it twice"}
    if retake_reason:
        return {**out, "do": "pay", "why": f"retake: {retake_reason}", "retake": n_retakes + 1}
    if last is None:
        return out if not chk else {**out, "do": "refuse", "why": f"a file is on disk that no logged call made: {chk['reason']}"}
    if last["state"] in ("finished", "pending") and last["task_id"]:
        return {**out, "do": "fetch", "task": last["task_id"],
                "why": f"task {last['task_id']} is {last['state']}; fetching it is free (outputs live 24-48 h)"}
    if last["state"] == "failed":
        return {**out, "do": "refuse", "why": "the last task failed (moderation failures are billed); --retake-reason to pay again"}
    if last["state"] == "rejected":
        return {**out, "do": "refuse", "why": "the last submit was rejected, not billed (a 4xx: the task was never created); "
                                               "read its error in the spend log, then --retake-reason to submit again"}
    return {**out, "do": "refuse", "why": f"the last call's outcome is {last['state']}: check the Runway dashboard, "
                                           "then --retake-reason to pay again"}


def run_one(spec: ClipSpec, *, yes: bool, estimate: bool = False, retake_reason: str = "", runner=subprocess.run,
            out=print) -> int:
    """One clip. Returns an exit code (0 also for 'skipped' and for a dry plan)."""
    act = action_for(spec, retake_reason)
    cr = credits(spec.seconds)
    seed = seed_for(spec, act["retake"])
    out(f"{spec.id:44s} {act['do']:6s} {cr:3d} cr  seed {seed:10d}  {act['why']}")
    if act["do"] == "skip":
        return EXIT_OK
    if act["do"] == "refuse":
        out("  refused: " + act["why"])
        return EXIT_FAILED
    if act["do"] == "fetch":
        cmd = build_fetch(act["task"], spec)
        if not yes:
            out("  would run: " + shlex.join(cmd))
            return EXIT_OK
        rc = runner(cmd, cwd=str(STUDIO)).returncode
        if rc != 0:
            return rc
        r = check_clip(spec)
        out(f"  fetched: {'ok' if r['ok'] else 'INVALID: ' + str(r['reason'])}")
        return EXIT_OK if r["ok"] else EXIT_FAILED
    why_not = budget_refusal(spec, bool(retake_reason))
    if why_not:
        out(f"  refused: {why_not}")
        return EXIT_FAILED
    reserve = sg.depth_reserve_usd(spec) if spec.kind == "hunt" else 0.0     # the hunt, run last, absorbs the stop (call 56)
    try:
        sg.check_generation_cap(cr * sg.CREDIT_USD, extra_usd=reserve,
                                label=spec.id + (f" with ${reserve:.2f} held back for depth" if reserve else ""))
    except sg.GenerationStop as e:
        out(f"  {e}")
        return sg.EXIT_STOP
    if not yes and not estimate:
        out("  would run: " + shlex.join(build_command(spec, seed, yes=True)) + "\n  (add --yes to pay)")
        return EXIT_OK
    make_start_image(spec.condition)
    if estimate and not yes:
        rc = runner(build_command(spec, seed, yes=False), cwd=str(STUDIO)).returncode
        return EXIT_OK if rc in (0, EXIT_REFUSED) else rc          # exit 3 is runway_gen printing its estimate
    if retake_reason:
        log_retake(spec, act["retake"], retake_reason, seed, retire_existing(spec))
    rc = runner(build_command(spec, seed, yes=True), cwd=str(STUDIO)).returncode
    if rc != 0:
        out(f"  runway exit {rc}" + {1: " (failed)", 3: " (refused)", 4: f" (still running: runway_calls.py fetch --clip {spec.id} --yes)"}.get(rc, ""))
        return rc
    r = check_clip(spec)
    out(f"  saved {video_path(spec)}: {'ok' if r['ok'] else 'INVALID: ' + str(r['reason'])} ({r['frames']} frames, {r['size']})")
    return EXIT_OK if r["ok"] else EXIT_FAILED


def run_batch(batch: str, specs: list[ClipSpec], *, yes: bool, estimate: bool = False, retake_reason: str = "",
              runner=subprocess.run, out=print) -> int:
    """Clips in order, stopping at the first one that does not end well. The whole batch must fit the stop first."""
    require_gate(batch, specs)
    if retake_reason and len(specs) != 1:
        out("--retake-reason pays again, so it needs exactly one clip: use --only and --prompt")
        return EXIT_USAGE
    todo = [s for s in specs if action_for(s, retake_reason)["do"] == "pay"]
    total_cr = sum(credits(s.seconds) for s in todo)
    s = sg.spent()
    for cond in sorted({s.condition for s in todo}):      # free and local: the start images can be looked at before any payment
        make_start_image(cond)
    out(f"{batch}: {len(specs)} clips, {len(todo)} to pay for, {total_cr} credits (${total_cr * sg.CREDIT_USD:.2f}); "
        f"the card so far GBP {s['total_gbp']:.2f} of the GBP {sg.GENERATION_STOP_GBP:.0f} stop")
    reserve = sg.depth_reserve_usd(specs[0]) if batch == "hunt" else 0.0
    try:
        sg.check_generation_cap(total_cr * sg.CREDIT_USD, extra_usd=reserve,
                                label=f"the {batch} batch" + (f" with ${reserve:.2f} held back for depth" if reserve else ""))
    except sg.GenerationStop as e:
        out(str(e))
        return sg.EXIT_STOP
    for spec in specs:
        rc = run_one(spec, yes=yes, estimate=estimate, retake_reason=retake_reason, runner=runner, out=out)
        if rc != EXIT_OK:
            return rc
    return EXIT_OK


# ---- command line -----------------------------------------------------------------------------------

def cmd_status(out=print) -> int:
    s = sg.spent()
    out(f"Runway ${s['runway_usd']:.2f} + Modal ${s['modal_usd']:.2f} = ${s['total_usd']:.2f} = GBP {s['total_gbp']:.2f} "
        f"(stop GBP {sg.GENERATION_STOP_GBP:.0f}, card cap GBP {sg.CARD_CAP_GBP:.0f}, GBP {sg.GBP_PER_USD:.2f} per $)")
    for c in sg.runway_calls():
        out(f"  {c['state']:9s} {c['counted']:6.0f} cr  {c['label'] or '':14s} {Path(c['out']).name if c['out'] else '-'}")
    out(f"gates: {', '.join(read_gates()) or 'none recorded'}")
    return EXIT_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="runway_calls.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("probes", "finals", "long", "hunt"):
        sp = sub.add_parser(name)
        sp.add_argument("--yes", action="store_true", help="pay (Aaron's go); without it only the plan is printed")
        sp.add_argument("--estimate", action="store_true", help="runway.sh's own estimate per clip (sends nothing)")
        sp.add_argument("--retake-reason", default="", help="pay again for a clip that already exists; the reason is logged")
        sp.add_argument("--only", default="")
        sp.add_argument("--prompt", default="", choices=["", "D", "B", "N"])
        if name == "hunt":
            sp.add_argument("--condition", required=True, choices=list(RECORDING_NAMES))
            sp.add_argument("--take", required=True, type=int)
    sp = sub.add_parser("fetch")
    sp.add_argument("--clip", required=True)
    sp.add_argument("--task", default="")
    sp.add_argument("--yes", action="store_true")
    sp = sub.add_parser("gate")
    sp.add_argument("name", choices=["P", "H"])
    sp.add_argument("--note", required=True)
    sp.add_argument("--condition", choices=list(RECORDING_NAMES))
    sp.add_argument("--definition-file")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        return cmd_status()
    if a.cmd == "gate":
        extra = {}
        if a.name == "H":
            if not (a.condition and a.definition_file):
                ap.error("gate H needs --condition and --definition-file (the frozen definition, as STATUS records it)")
            extra = {"condition": a.condition, "definition": Path(a.definition_file).read_text().strip()}
        record_gate(a.name, a.note, **extra)
        print(f"recorded Gate {a.name}")
        return EXIT_OK
    if a.cmd == "fetch":
        spec = clips.parse_clip_id(a.clip)
        task = a.task or action_for(spec)["task"]
        if not task:
            print("no task id: pass --task (the id runway printed when it timed out)")
            return EXIT_USAGE
        cmd = build_fetch(task, spec)
        if not a.yes:
            print("would run: " + shlex.join(cmd) + "  (free; add --yes to run it)")
            return EXIT_OK
        rc = subprocess.run(cmd, cwd=str(STUDIO)).returncode
        return rc if rc else (EXIT_OK if check_clip(spec)["ok"] else EXIT_FAILED)
    specs = plan_specs(a.cmd, a.only, a.prompt, getattr(a, "condition", ""), getattr(a, "take", 0))
    return run_batch(a.cmd, specs, yes=a.yes, estimate=a.estimate, retake_reason=a.retake_reason)


if __name__ == "__main__":
    sys.exit(main())
