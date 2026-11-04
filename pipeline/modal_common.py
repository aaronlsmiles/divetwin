"""Local-side helpers for the Modal apps: encoding, the spend cap and the spend log. Imported only by
local entrypoints, never inside a container.

Spend model (all of it an upper bound, never an estimate of what Modal will bill):
  * a Meter bills the wall time since its first remote call plus the scaledown window, at the GPU rate plus
    the CPU and memory the class reserves (Modal bills a container for what it reserves);
  * a task's cap is cumulative: the Meter starts from the `usd_upper` already logged for that task in
    runs/modal_spend.jsonl, so a re-run does not get a fresh allowance;
  * Phase 1 as a whole is capped at PHASE1_CAP_USD across every task in the log;
  * a remote call is refused when the spend so far plus the call's expected cost would pass the cap, and
    each call has a timeout of about three times its expected duration, so one call cannot run away;
  * every paid section ends with exactly one log line, whatever way it ends (ok, cap, error, interrupted)."""
from __future__ import annotations

import contextlib
import io
import json
import time

import cv2
import numpy as np

from recordings import runs_dir

USD_PER_GPU_HOUR = {"L40S": 1.95, "A100-80GB": 2.50}   # Modal list prices; re-check at modal.com/pricing before a run
USD_PER_CPU_CORE_S = 0.0000131      # per physical core, per second reserved
USD_PER_GIB_S = 0.00000222          # per GiB of memory, per second reserved
SCALEDOWN_S = 60
PHASE1_CAP_USD = 5.00               # every task in modal_spend.jsonl is Phase 1
SPEND_LOG = "modal_spend.jsonl"


def png(img: np.ndarray) -> bytes:
    ok, b = cv2.imencode(".png", img)
    assert ok
    return b.tobytes()


def jpg(img: np.ndarray, q: int = 95) -> bytes:
    ok, b = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    assert ok
    return b.tobytes()


def npy_load(b: bytes) -> np.ndarray:
    return np.load(io.BytesIO(b))


def _strict(x):
    """JSON-safe copy: NaN and infinities become None (strict JSON has no NaN), numpy scalars plain."""
    if isinstance(x, dict):
        return {k: _strict(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_strict(v) for v in x]
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return float(x) if np.isfinite(x) else None
    return x


def rate_per_s(gpu: str | None, cpu: float = 0.0, mem_gib: float = 0.0) -> float:
    """USD per second of one container: GPU + reserved CPU cores + reserved memory."""
    g = USD_PER_GPU_HOUR[gpu] / 3600 if gpu else 0.0
    return g + cpu * USD_PER_CPU_CORE_S + mem_gib * USD_PER_GIB_S


def estimate(n: int, s_per_item: float, load_s: float, gpu: str | None, cpu: float = 0.0, mem_gib: float = 0.0) -> float:
    return (load_s + SCALEDOWN_S + n * s_per_item) * rate_per_s(gpu, cpu, mem_gib)


# ---- the log -----------------------------------------------------------------------------------------

def spend_lines() -> list[dict]:
    """Every readable line of runs/modal_spend.jsonl (a torn or foreign line is skipped, never fatal)."""
    p = runs_dir() / SPEND_LOG
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


def _usd(r: dict) -> float:
    v = r.get("usd_upper")
    return float(v) if isinstance(v, (int, float)) and np.isfinite(v) else 0.0


def task_spent_usd(task: str) -> float:
    """What earlier runs of this task logged (their `usd_upper`, summed)."""
    return sum(_usd(r) for r in spend_lines() if r.get("task") == task)


def phase_total_usd() -> float:
    return sum(_usd(r) for r in spend_lines())


def clamp_to_phase(meter: "Meter", phase_cap: float = PHASE1_CAP_USD) -> "Meter":
    """Hold the meter's cumulative cap to what Phase 1 has left, so the phase total binds while the run goes.

    The cap is cumulative for the task (baseline + this run), and the phase headroom is what the log has not yet spent.
    """
    meter.cap = min(meter.cap, meter.baseline + phase_cap - phase_total_usd())
    return meter


def check_phase_budget(estimate_usd: float, phase_cap: float = PHASE1_CAP_USD) -> None:
    """Refuse (non-zero exit) to start a run that could take Phase 1 past its total."""
    total = phase_total_usd()
    if total + estimate_usd > phase_cap:
        raise SystemExit(f"Phase 1 budget: ${total:.2f} is already logged in {SPEND_LOG} and this run is estimated at "
                         f"${estimate_usd:.2f}, which would pass the ${phase_cap:.2f} Phase 1 total; nothing was started")


class CapReached(Exception):
    """A remote call was refused because it could take the task past its cap."""


class FetchDeadline(RuntimeError):
    """A remote call did not return within its deadline and was cancelled."""


def call_with_deadline(fn, deadline_s: float, *args):
    """Spawn `fn` (a Modal function), wait at most `deadline_s` for its result, cancel it if it hangs.

    `fn.remote` waits forever when the container crash-loops at startup, and the Meter never sees it;
    run through `Meter.remote`, a hang ends in FetchDeadline, so `Meter.section` still writes its spend line."""
    import modal.exception
    call = fn.spawn(*args)
    try:
        return call.get(timeout=deadline_s)
    except (TimeoutError, modal.exception.TimeoutError) as e:
        call.cancel()
        raise FetchDeadline(f"no result within {deadline_s:.0f} s; the call was cancelled") from e


class Meter:
    """Upper bound on billed time for one task: the wall time since the Meter was created (build it just before
    the first remote call) plus the scaledown window, at GPU + CPU + memory rates, on top of whatever the log
    already holds for the task. `cap` is cumulative."""

    _now = staticmethod(time.time)   # a test can swap the clock

    def __init__(self, gpu: str | None, cap_usd: float, task: str = "", cpu: float = 0.0, mem_gib: float = 0.0):
        self.gpu, self.cap, self.task, self.cpu, self.mem_gib = gpu, cap_usd, task, cpu, mem_gib
        self.rate_s = rate_per_s(gpu, cpu, mem_gib)
        self.baseline = task_spent_usd(task) if task else 0.0
        self.t0 = self._now()
        self.gpu_s = 0.0
        self.calls = 0       # remote calls made: with none, nothing was billed
        self.warm = False    # a GPU container has loaded its model, so later calls skip the load time
        self.n_done = 0      # units of work actually finished (the log's `n`)
        self.call_log: list[list[float]] = []   # [wall seconds, units of work] of each remote call that returned
        self.status = "ok"
        self.phase = None    # Phases 2 and 3 set it (spendguard.GuardedMeter); Phase 1 lines carry no tag

    def run_usd(self) -> float:
        """This run's upper bound so far: wall time since the Meter started plus one scaledown window."""
        return (self._now() - self.t0 + SCALEDOWN_S) * self.rate_s

    def usd(self) -> float:
        """Cumulative for the task: what earlier runs logged plus this run's bound."""
        return self.baseline + self.run_usd()

    def over(self) -> bool:
        return self.usd() > self.cap

    def allows(self, est_s: float) -> bool:
        """Would a call expected to take `est_s` seconds still end at or under the cap?"""
        return self.usd() + est_s * self.rate_s <= self.cap

    def remote(self, fn, *args, est_s: float, units: int = 0, **kw):
        """Run one remote call, unless it would pass the cap (raises CapReached before anything is sent). `units` is
        the work the call does (clips, frames; 0 for a download); its wall time is kept in `call_log` so a smoke run's
        warm calls can be told from the call that paid for the container start and the model load."""
        if not self.allows(est_s):
            raise CapReached(f"cap ${self.cap:.2f} (cumulative for {self.task or 'this run'}): ${self.usd():.2f} spent "
                             f"so far plus about ${est_s * self.rate_s:.2f} for the next call")
        self.calls += 1
        t = self._now()
        out = fn(*args, **kw)
        self.call_log.append([round(self._now() - t, 1), units])
        return out

    @contextlib.contextmanager
    def section(self, task: str, app: str, n_planned: int | None = None):
        """A paid section: whatever way it ends, one spend line is written, with the count actually done."""
        self.task = task
        self.n_done, self.status, self.call_log = 0, "ok", []
        try:
            yield self
        except CapReached as e:
            self.status = "cap"
            print(f"stopped: {e}")
        except KeyboardInterrupt:
            self.status = "interrupted"
            raise
        except BaseException:
            self.status = "error"
            raise
        finally:
            self.log(task, app, self.n_done, self.status, n_planned)

    def log(self, task: str, app: str, n: int, status: str = "ok", n_planned: int | None = None) -> dict:
        run = self.run_usd() if self.calls else 0.0   # no remote call was made: nothing was billed
        wall = self._now() - self.t0 + SCALEDOWN_S if self.calls else 0.0
        line = {"task": task, "app": app, "gpu": self.gpu, "status": status, "n": n, "n_planned": n_planned,
                "gpu_s_in_calls": round(self.gpu_s, 1), "wall_s": round(wall, 1), "usd_upper": round(run, 3),
                "cum_usd": round(self.baseline + run, 3), "cap_usd": self.cap,
                "cpu": self.cpu, "mem_gib": self.mem_gib,
                "rate_gpu_usd_h": USD_PER_GPU_HOUR[self.gpu] if self.gpu else 0.0,
                "rate_cpu_usd_core_s": USD_PER_CPU_CORE_S, "rate_mem_usd_gib_s": USD_PER_GIB_S,
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
        if self.phase is not None:
            line["phase"] = self.phase   # an untagged line is Phase 1 (modal_spend.jsonl before sub-plan B)
            line["calls"] = self.call_log   # [wall s, units] per call: the smoke's projection reads the warm ones
        line = _strict(line)  # a non-finite field is written as null, never an error
        text = json.dumps(line, allow_nan=False)
        runs_dir().mkdir(parents=True, exist_ok=True)
        with open(runs_dir() / SPEND_LOG, "a") as fh:
            fh.write(text + "\n")
        print(text)
        return line
