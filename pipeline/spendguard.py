"""The card's money, in one place: the 25 GBP generation stop (kill rule 3) and the Phase 2 and 3 Modal budgets.

What counts, in USD (upper bounds, never optimistic):
  * Runway: every call in the card's spend log (spend.jsonl at the repo root). A call's cost is its `final`
    row's cost.credits x $0.01; a `fetch` row supplies it for a call that timed out; a call with no cost yet
    (still running, interrupted, an unparsed answer) counts at the larger of our estimate and the API's own
    estimatedCost. A submit the API rejected with a 4xx status was never created and is not billed.
  * Modal: every `usd_upper` in runs/modal_spend.jsonl, `correction` lines (negative) included, so the
    total here equals the one in STATUS. Phase 1 counts: the stop reads the whole card, not one phase.
The conversion is GBP_PER_USD = 0.80: the records so far used about 0.787, so this overstates pounds by ~2 %.

`check_generation_cap` is the one function both engines call, before every paid call. It raises
GenerationStop (a CapReached, so a Modal section ends with a 'cap' spend line) when the card's total plus
the call's estimate would pass the stop. The Phase 1 Modal cap in modal_common is untouched."""
from __future__ import annotations

import json
import os
from pathlib import Path

import clips
import modal_common
from modal_common import CapReached, Meter, rate_per_s

GBP_PER_USD = 0.80            # pounds per dollar; slightly pessimistic (records so far: ~0.787)
CREDIT_USD = 0.01             # Runway: one credit
GENERATION_STOP_GBP = 25.0    # kill rule 3 (Gate 0, 3 Nov): no generation call that would pass this
CARD_CAP_GBP = 30.0           # the card's hard cap
DEPTH_STOP_GBP = GENERATION_STOP_GBP   # DA3 on the clips obeys the same stop; call 56 may raise it to CARD_CAP_GBP
EXIT_STOP = 7                 # 5 and 6 are the kill-rule exits in cli.py

# Modal budgets for the phases after Phase 1 (PHASE1_CAP_USD = 5.00 in modal_common stays as it is). Each task has
# its own cumulative cap in its own module; the phase total here binds first (see sub-plan B section 5.2).
PHASE_TOTAL_USD = {2: 5.80, 3: 2.00}   # Phase 2 raised from 5.00 by Aaron, 3 Nov (call 72)

# What DA3 on the clips (task 3.1) is expected to cost: modal_depth's per-clip estimates use these numbers, and the
# hunt's reserve below holds this much back so depth is never starved (call 56). The Phase 1 floor run measured
# 497 s of wall time for 547 frames, 0.91 s a frame, almost all of it transfer; the clips path sends a tenth of the
# bytes, so 0.25 s a frame is a bet that only the depth smoke run can confirm (see projection_from_smoke).
DEPTH_GPU, DEPTH_CPU, DEPTH_MEM_GIB = "L40S", 4, 16
DEPTH_S_PER_FRAME, DEPTH_LOAD_S, DEPTH_OVERHEAD_S = 0.25, 90, 20
PHASE1_MEASURED_S_PER_FRAME = 0.91
SMOKE_CLIPS = 1        # every smoke run is one clip (modal_wan --smoke, modal_depth --smoke)
DEPTH_SMOKE_TASK = "3.1-depth-smoke"    # modal_depth.CLIP_TASKS["smoke"]; a test pins that they agree

# the card's Runway spend log; DIVETWIN_RUNWAY_LOG redirects it in tests
RUNWAY_LOG = Path(__file__).resolve().parent.parent / "spend.jsonl"


class GenerationStop(CapReached):
    """A paid call was refused because the card's total plus the call would pass the generation stop."""


def runway_log_path() -> Path:
    return Path(os.environ.get("DIVETWIN_RUNWAY_LOG", RUNWAY_LOG))


def read_rows(path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    for t in p.read_text().splitlines():
        try:
            r = json.loads(t)
        except ValueError:
            continue
        if isinstance(r, dict):
            rows.append(r)
    return rows


def _num(x) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x == x and abs(x) != float("inf") else None


def runway_calls(path=None) -> list[dict]:
    """One dict per Runway call in the log: {'call_id', 'task_id', 'label', 'out', 'state', 'credits', 'est',
    'counted'}. state: finished | failed | pending | rejected | unknown. `counted` is the credits that go in the total."""
    calls: dict[str, dict] = {}
    by_task: dict[str, str] = {}
    fetches: list[dict] = []
    for r in read_rows(path or runway_log_path()):
        ev, cid = r.get("event"), r.get("call_id")
        if ev == "fetch":
            fetches.append(r)
            continue
        if not cid:
            continue
        c = calls.setdefault(cid, {"call_id": cid, "task_id": None, "label": None, "out": None, "state": "unknown",
                                   "credits": None, "est": 0.0, "rejected": False, "created": False})
        if ev == "pre":
            c.update(label=r.get("label"), out=r.get("out"), est=max(c["est"], _num(r.get("our_estimate")) or 0.0))
        elif ev == "created":
            c.update(task_id=r.get("task_id"), created=True,
                     est=max(c["est"], _num(r.get("estimated_cost_credits")) or 0.0))
            if r.get("task_id"):
                by_task[r["task_id"]] = cid
        elif ev == "final":
            c["task_id"] = r.get("task_id") or c["task_id"]
            c["state"] = "finished" if r.get("status") == "SUCCEEDED" else "failed"
            c["credits"] = _num(r.get("cost_credits"))
            c["out"] = r.get("output_path") or c["out"]
            if r.get("download_error"):
                c["download_error"] = r["download_error"]
        elif ev in ("timeout", "interrupted", "poll_error"):
            c["task_id"] = r.get("task_id") or c["task_id"]
            if c["state"] not in ("finished", "failed"):
                c["state"] = "pending"
        elif ev == "submit_error" and not c["created"]:
            st = r.get("status")
            if isinstance(st, int) and 400 <= st < 500 and st != 429:
                c["rejected"] = True
    for r in fetches:                      # a fetch finishes a call that timed out, or stands alone
        tid = r.get("task_id")
        cid = by_task.get(tid)
        if cid is None:
            cid = "task:" + str(tid)
            calls.setdefault(cid, {"call_id": cid, "task_id": tid, "label": "fetch", "out": None, "state": "unknown",
                                   "credits": None, "est": 0.0, "rejected": False, "created": True})
        c = calls[cid]
        if r.get("status") == "SUCCEEDED":
            c["state"] = "finished"
            c["credits"] = _num(r.get("cost_credits")) if _num(r.get("cost_credits")) is not None else c["credits"]
            c["out"] = r.get("output_path") or c["out"]
        elif r.get("status") in ("FAILED", "CANCELLED") and c["state"] == "pending":
            c["state"] = "failed"
            c["credits"] = _num(r.get("cost_credits")) if _num(r.get("cost_credits")) is not None else c["credits"]
    out = []
    for c in calls.values():
        if c["state"] == "unknown" and c["rejected"]:
            c["state"] = "rejected"
        c["counted"] = 0.0 if c["state"] == "rejected" else (c["credits"] if c["credits"] is not None else c["est"])
        out.append(c)
    return out


def runway_usd(path=None) -> float:
    return sum(c["counted"] for c in runway_calls(path)) * CREDIT_USD


def modal_usd() -> float:
    """Every `usd_upper` line of runs/modal_spend.jsonl, corrections (negative) included; all phases."""
    return sum(modal_common._usd(r) for r in modal_common.spend_lines())


def spent() -> dict:
    r, m = runway_usd(), modal_usd()
    return {"runway_usd": round(r, 4), "modal_usd": round(m, 4), "total_usd": round(r + m, 4),
            "total_gbp": round((r + m) * GBP_PER_USD, 4)}


def check_generation_cap(est_usd: float, *, extra_usd: float = 0.0, cap_gbp: float = GENERATION_STOP_GBP,
                         label: str = "") -> dict:
    """Refuse (GenerationStop) when the card's spend so far, `extra_usd` not yet logged (a running Modal
    section's own bound) and this call's estimate would pass `cap_gbp`. Returns the sums when it fits."""
    s = spent()
    after = (s["total_usd"] + extra_usd + est_usd) * GBP_PER_USD
    s.update(call_usd=round(est_usd, 4), after_gbp=round(after, 4), cap_gbp=cap_gbp)
    if after > cap_gbp:
        raise GenerationStop(
            f"generation stop: {label or 'this call'} (about ${est_usd:.2f}) would take the card to "
            f"GBP {after:.2f}, over the GBP {cap_gbp:.2f} stop (Runway ${s['runway_usd']:.2f} + Modal "
            f"${s['modal_usd']:.2f} so far, at GBP {GBP_PER_USD:.2f} per dollar)")
    return s


# ---- Modal phases 2 and 3 ----------------------------------------------------------------------------

def phase_of(row: dict) -> int:
    """An untagged line is Phase 1."""
    p = row.get("phase")
    return int(p) if isinstance(p, int) and not isinstance(p, bool) else 1


def phase_spent_usd(phase: int) -> float:
    return sum(modal_common._usd(r) for r in modal_common.spend_lines() if phase_of(r) == phase)


def check_phase_total(phase: int, est_usd: float) -> None:
    """Refuse (non-zero exit) to start a run that could take the phase past its total."""
    cap, now = PHASE_TOTAL_USD[phase], phase_spent_usd(phase)
    if now + est_usd > cap:
        raise SystemExit(f"Phase {phase} budget: ${now:.2f} is already logged and this run is estimated at "
                         f"${est_usd:.2f}, which would pass the ${cap:.2f} Phase {phase} total; nothing was started")


class GuardedMeter(Meter):
    """A Meter for Phase 2 or 3: tags its spend lines with the phase, holds its cumulative cap to what the
    phase has left, and checks the generation stop before every remote call."""

    def __init__(self, gpu, cap_usd, task, phase, cpu=0.0, mem_gib=0.0, stop_gbp=GENERATION_STOP_GBP):
        super().__init__(gpu, cap_usd, task=task, cpu=cpu, mem_gib=mem_gib)
        self.phase, self.stop_gbp = phase, stop_gbp
        self.cap = min(self.cap, self.baseline + PHASE_TOTAL_USD[phase] - phase_spent_usd(phase))

    def check(self, est_s: float) -> None:
        """Raise (a CapReached) when a call expected to take `est_s` seconds must not start: the generation stop first,
        then this meter's own cumulative cap. Sends nothing; `remote` runs it before every call."""
        check_generation_cap(est_s * self.rate_s, extra_usd=self.run_usd(), cap_gbp=self.stop_gbp,
                             label=self.task or "this call")
        if not self.allows(est_s):
            raise CapReached(f"cap ${self.cap:.2f} (cumulative for {self.task or 'this run'}): ${self.usd():.2f} spent "
                             f"so far plus about ${est_s * self.rate_s:.2f} for the next call")

    def remote(self, fn, *args, est_s, **kw):
        self.check(est_s)
        return super().remote(fn, *args, est_s=est_s, **kw)


# ---- the cost of depth, and the hunt's reserve for it ----------------------------------------------------

def depth_est_usd(n_frames: int, n_clips: int, s_per_frame: float = DEPTH_S_PER_FRAME,
                  load_s: float = DEPTH_LOAD_S, overhead_s: float = DEPTH_OVERHEAD_S) -> float:
    """Upper-bound estimate of DA3 on `n_frames` frames in `n_clips` clips: one load, `overhead_s` of local work per clip
    (decode, encode, median, savez, check_depth: the meter bills it too), the scaledown window, at the GPU + CPU +
    memory rate."""
    if n_clips <= 0 and n_frames <= 0:
        return 0.0                           # nothing to do: no container, no scaledown
    secs = load_s + n_clips * overhead_s + modal_common.SCALEDOWN_S + n_frames * s_per_frame
    return secs * rate_per_s(DEPTH_GPU, DEPTH_CPU, DEPTH_MEM_GIB)


def depth_reserve_usd(extra: "clips.ClipSpec | None" = None) -> float:
    """What depth still needs: the estimate for every valid indexed clip without a depth file, plus `extra` (a clip
    about to be made, such as a hunt take). The hunt holds this back so it shrinks before depth is starved."""
    good, _ = clips.scan_clips(check=False)
    need = [s for s in good if s.in_finals_index and not clips.depth_ready(s)]
    if extra is not None and all(extra.id != s.id for s in need):
        need.append(extra)
    if not need:
        return 0.0
    return depth_est_usd(sum(clips.expected_frames(s) for s in need), len(need), depth_s_per_frame(),
                         depth_load_s(), depth_clip_overhead_s())


# ---- re-estimating from a smoke run before the full run (I4) ------------------------------------------------

def _smoke_row(smoke_task: str) -> dict | None:
    rows = [r for r in modal_common.spend_lines()
            if r.get("task") == smoke_task and r.get("status") == "ok" and (r.get("n") or 0) > 0 and r.get("wall_s")]
    return rows[-1] if rows else None


def smoke_s_per_unit(smoke_task: str, load_s: float) -> float | None:
    """Seconds per unit of work from the smoke run's own spend line, or None before an ok smoke.

    From the warm calls only: the line's `calls` are [wall s, units] for each remote call; calls with no units (a
    download) are not work, and the first call that did work paid for the container start and the model load, so it is
    left out. Whatever the later calls took, a unit at a time, is the rate, and an error in the assumed load time cannot
    touch it. With no warm call (a smoke of one clip, or a line from before calls were logged) the rate is the larger of
    the GPU time inside the calls per unit and (wall - scaledown - load) per unit."""
    r = _smoke_row(smoke_task)
    if r is None:
        return None
    work = []
    for c in r.get("calls") or []:
        try:
            s_, u_ = float(c[0]), float(c[1])
        except (TypeError, ValueError, IndexError):
            continue
        if u_ > 0 and s_ >= 0:
            work.append((s_, u_))
    warm = work[1:]
    if warm:
        return sum(s_ for s_, _ in warm) / sum(u_ for _, u_ in warm)
    n = float(r["n"])
    formula = max((float(r["wall_s"]) - modal_common.SCALEDOWN_S - load_s) / n, 0.0)
    gpu = r.get("gpu_s_in_calls")
    return max(formula, float(gpu) / n if isinstance(gpu, (int, float)) and gpu > 0 else 0.0)


def _smoke_calls(r: dict) -> list[tuple[float, float]]:
    """The smoke line's valid `calls` as (wall s, units), in order (units may be 0)."""
    out = []
    for c in r.get("calls") or []:
        try:
            s_, u_ = float(c[0]), float(c[1])
        except (TypeError, ValueError, IndexError):
            continue
        if s_ >= 0 and u_ >= 0:
            out.append((s_, u_))
    return out


def smoke_measure(smoke_task: str, load_s: float, overhead_s: float = DEPTH_OVERHEAD_S) -> dict | None:
    """What the smoke run measured, each figure never below the nominal one it replaces (a smoke can only make the
    projection more careful), or None before an ok smoke:

      s_per_unit  `smoke_s_per_unit` (warm calls; the gpu_s_in_calls fallback with none)
      load_s      the larger of `load_s` and the first work call's wall time less its units at the warm rate: that call
                  paid for the container start and the model load, so a load longer than assumed shows up here
      per_clip_s  the larger of `overhead_s` and the local work per clip: wall - scaledown - the sum of the calls' wall
                  times, per smoke clip (decode, encode, median, savez, check_depth for DA3; the transfer and check for
                  Wan). A line with no `calls` has no such measure, and `overhead_s` stands."""
    r = _smoke_row(smoke_task)
    if r is None:
        return None
    rate = smoke_s_per_unit(smoke_task, load_s)
    calls = _smoke_calls(r)
    load = load_s
    first = next(((s_, u_) for s_, u_ in calls if u_ > 0), None)
    if first is not None and rate is not None:
        load = max(load_s, first[0] - first[1] * rate)
    per_clip = overhead_s
    if calls:
        local = (float(r["wall_s"]) - modal_common.SCALEDOWN_S - sum(s_ for s_, _ in calls)) / SMOKE_CLIPS
        per_clip = max(overhead_s, local)
    return {"s_per_unit": rate, "load_s": load, "per_clip_s": per_clip}


def depth_s_per_frame() -> float:
    """What the reserve assumes DA3 costs a frame: the nominal figure, or the depth smoke's own measurement once an
    ok smoke line exists, whichever is slower. The smoke can only ever make the hunt more careful."""
    m = smoke_s_per_unit(DEPTH_SMOKE_TASK, DEPTH_LOAD_S)
    return max(DEPTH_S_PER_FRAME, m or 0.0)


def depth_load_s() -> float:
    """The reserve's load time: nominal, or the depth smoke's measured one when that is longer."""
    m = smoke_measure(DEPTH_SMOKE_TASK, DEPTH_LOAD_S)
    return m["load_s"] if m else float(DEPTH_LOAD_S)


def depth_clip_overhead_s() -> float:
    """The reserve's local work per clip: nominal, or the depth smoke's measured one when that is longer."""
    m = smoke_measure(DEPTH_SMOKE_TASK, DEPTH_LOAD_S)
    return m["per_clip_s"] if m else float(DEPTH_OVERHEAD_S)


def projection_from_smoke(smoke_task: str, n_remaining: int, load_s: float, rate_s: float, n_clips: int = 0,
                          overhead_s: float = DEPTH_OVERHEAD_S) -> dict | None:
    """Project the full run from the smoke run's own spend line (`smoke_measure`): (load + scaledown + remaining x
    seconds per unit + `n_clips` x local work per clip) x rate. The load and the local work are never below `load_s`
    and `overhead_s`. None when no ok smoke run is logged."""
    r = _smoke_row(smoke_task)
    if r is None:
        return None
    m = smoke_measure(smoke_task, load_s, overhead_s)
    usd = (m["load_s"] + modal_common.SCALEDOWN_S + n_remaining * m["s_per_unit"] + n_clips * m["per_clip_s"]) * rate_s
    return {"s_per_unit": m["s_per_unit"], "load_s": m["load_s"], "per_clip_s": m["per_clip_s"], "projected_usd": usd,
            "smoke_usd": modal_common._usd(r), "units": int(r["n"])}


def no_smoke_message(task: str) -> str:
    return (f"{task}: no ok smoke run is logged, so the full run is refused: the nominal estimate is a bet, and the "
            "smoke run is what measures it (run the --smoke form first). Nothing was started.")


def projection_refusal(proj: dict | None, *, task: str, task_cap: float, baseline: float, phase: int,
                       n_remaining: int, unit: str) -> str | None:
    """Why a full run would be refused: no ok smoke run to project from, or a projected cost that would pass the task's
    cap or the phase total. None when it fits. The real run and the dry run both use this message."""
    if proj is None:
        return no_smoke_message(task)
    if baseline + proj["projected_usd"] > task_cap or phase_spent_usd(phase) + proj["projected_usd"] > PHASE_TOTAL_USD[phase]:
        return (f"{task}: the smoke run's own numbers project ${proj['projected_usd']:.2f} for the remaining "
                f"{n_remaining} {unit}s, which does not fit the ${task_cap:.2f} task cap (${baseline:.2f} already "
                f"logged) or Phase {phase}'s ${PHASE_TOTAL_USD[phase]:.2f} total (${phase_spent_usd(phase):.2f} "
                "logged). Nothing was started. This is Aaron's decision; no cap was raised.")
    return None


def require_projection_fits(proj: dict | None, *, task: str, task_cap: float, baseline: float, phase: int,
                            n_remaining: int, unit: str) -> None:
    """Stop (non-zero exit, for Aaron) when there is no ok smoke run to project from, or the projected cost would pass the
    task's cap or the phase total."""
    why = projection_refusal(proj, task=task, task_cap=task_cap, baseline=baseline, phase=phase,
                             n_remaining=n_remaining, unit=unit)
    if proj is not None:
        print(f"re-estimated from the smoke run: {proj['s_per_unit']:.2f} s a {unit} (smoke ${proj['smoke_usd']:.2f}); the "
              f"remaining {n_remaining} {unit}s are projected at ${proj['projected_usd']:.2f}")
    if why:
        raise SystemExit(why)
