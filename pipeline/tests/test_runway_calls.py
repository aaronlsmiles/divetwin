import itertools
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

import clips
import runway_calls as rc
import spendguard as sg
from clips import ClipSpec, seed_for, video_path
from prompts import PROMPTS
from recordings import RECORDING_NAMES, recordings
from synth_video import noise_frames, write_mp4

_IDS = itertools.count(1)
STUDIO_REAL = Path(os.environ.get("STUDIO_ROOT") or Path(__file__).resolve().parents[4])


@pytest.fixture
def card(tmp_path, monkeypatch):
    """The hub is tmp_path, the card's Runway log is tmp_path/prototypes/divetwin/spend.jsonl, and `--log` is the
    literal relative string `prototypes/divetwin/spend.jsonl`: the fake client resolves it against the cwd it is given,
    exactly as the real client does, so a runner called from the wrong directory writes to the wrong file."""
    monkeypatch.setattr(rc, "STUDIO", tmp_path)
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path / "runs"))
    monkeypatch.setenv("DIVETWIN_RUNWAY_LOG", str(tmp_path / "prototypes" / "divetwin" / "spend.jsonl"))
    (tmp_path / "prototypes" / "divetwin").mkdir(parents=True)
    other = tmp_path / "elsewhere" / "pipeline"            # where the process is: not the hub
    other.mkdir(parents=True)
    monkeypatch.chdir(other)
    monkeypatch.setitem(clips.GRID, "gen45", (64, 48))               # tiny clips; the real grid is pinned elsewhere
    (tmp_path / "runs").mkdir()
    return tmp_path


class FakeRunway:
    """Stands in for runway.sh: appends the client's spend rows and writes an mp4, or fails as told."""

    def __init__(self, card, outcome="ok", frames=None):
        self.card, self.outcome, self.frames, self.calls = card, outcome, frames, []

    def __call__(self, argv, **kw):
        self.calls.append(argv)
        assert kw.get("cwd") == str(rc.STUDIO), "the runner must be given cwd=STUDIO, or --log lands in the wrong place"
        a = dict(zip(argv[2::2], argv[3::2]))
        log = Path(kw["cwd"]) / a["--log"]
        if argv[1] == "fetch":
            self._row(log, {"event": "fetch", "task_id": a["--task"], "status": "SUCCEEDED", "cost_credits": 60,
                            "output_path": a["--out"]})
            write_mp4(a["--out"], noise_frames(self.frames or 121, 64, 48))
            return SimpleNamespace(returncode=0)
        if "--yes" not in argv:
            return SimpleNamespace(returncode=3)
        cid = f"c{next(_IDS)}"
        credits = 12 * int(a["--duration"])
        self._row(log, {"event": "pre", "call_id": cid, "label": "video:gen4.5", "our_estimate": credits,
                        "seed": int(a["--seed"]), "out": a["--out"]})
        if self.outcome == "reject":
            self._row(log, {"event": "submit_error", "call_id": cid, "status": 400, "error": "bad"})
            return SimpleNamespace(returncode=1)
        self._row(log, {"event": "created", "call_id": cid, "task_id": "t" + cid, "estimated_cost_credits": credits})
        if self.outcome == "timeout":
            self._row(log, {"event": "timeout", "call_id": cid, "task_id": "t" + cid})
            return SimpleNamespace(returncode=4)
        if self.outcome == "failed":
            self._row(log, {"event": "final", "call_id": cid, "task_id": "t" + cid, "status": "FAILED", "cost_credits": credits})
            return SimpleNamespace(returncode=1)
        self._row(log, {"event": "final", "call_id": cid, "task_id": "t" + cid, "status": "SUCCEEDED",
                        "cost_credits": credits, "output_path": a["--out"]})
        write_mp4(a["--out"], noise_frames(self.frames or 12 * 0 + clips.FPS * int(a["--duration"]) + 1, 64, 48))
        return SimpleNamespace(returncode=0)

    @staticmethod
    def _row(path, row):
        with open(path, "a") as fh:
            fh.write(json.dumps(row) + "\n")


@pytest.fixture
def fake_data(card, monkeypatch):
    """recordings() with a synthetic 2208x1242 start frame so make_start_image needs no dataset."""
    img = np.random.default_rng(1).integers(0, 255, (1242, 2208, 3), dtype=np.uint8)
    cv2.imwrite(str(card / "left.png"), img)
    rec = SimpleNamespace(left_path=lambda f: card / "left.png", start_frame=0)
    monkeypatch.setattr(rc, "recordings", lambda: {c: rec for c in RECORDING_NAMES})
    return img


def lines():
    out = []
    return out, out.append


# ---- the command ------------------------------------------------------------------------------------

def test_build_command_is_the_plan_s_command(card):
    spec = ClipSpec("air", "gen45", "N", 5)
    seed = seed_for(spec)
    argv = rc.build_command(spec, seed)
    a = dict(zip(argv[2::2], argv[3::2]))
    assert argv[0].endswith("tools/runway/runway.sh") and argv[1] == "video" and argv[-1] == "--yes"
    assert a["--model"] == "gen4.5" and a["--ratio"] == "1280:720" and a["--duration"] == "5"
    assert a["--prompt"] == PROMPTS["N"] and a["--seed"] == str(seed)
    assert a["--max-credits"] == "70" and a["--out"] == str(video_path(spec))
    assert a["--image"].endswith("runs/start/air.png")
    assert rc.build_command(spec, seed, yes=False)[-1] != "--yes"


def test_every_length_has_its_credit_ceiling_and_the_ceiling_clears_the_estimate():
    assert rc.MAX_CREDITS == {2: 30, 5: 70, 10: 130}
    for s, cap in rc.MAX_CREDITS.items():
        assert rc.credits(s) < cap <= rc.credits(s) + 12      # 24/60/120 credits against 30/70/130


def test_the_log_argument_is_the_cards_own_spend_log(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "STUDIO", tmp_path)
    monkeypatch.setenv("DIVETWIN_RUNWAY_LOG", str(tmp_path / "prototypes" / "divetwin" / "spend.jsonl"))
    assert rc._log_arg() == "prototypes/divetwin/spend.jsonl"
    assert sg.RUNWAY_LOG == Path(rc.__file__).resolve().parent.parent / "spend.jsonl"     # the default is the repo's own


def test_no_prompt_text_is_retyped_here():
    src = Path(rc.__file__).read_text()
    for t in PROMPTS.values():
        assert t not in src


def test_the_batches_are_the_plan_s_batches():
    assert len(rc.plan_specs("probes")) == 15 and {s.seconds for s in rc.plan_specs("probes")} == {2}
    assert len(rc.plan_specs("finals")) == 15 and {s.seconds for s in rc.plan_specs("finals")} == {5}
    assert [s.prompt for s in rc.plan_specs("long")] == ["D"] * 5 and {s.seconds for s in rc.plan_specs("long")} == {10}
    assert [s.prompt for s in rc.plan_specs("finals", only="air")] == ["D", "B", "N"]
    assert rc.plan_specs("hunt", condition="air", take=2)[0].id == "air__gen45__B__5s__h02"
    credits = {b: sum(rc.credits(s.seconds) for s in rc.plan_specs(b)) for b in ("probes", "finals", "long")}
    assert credits == {"probes": 360, "finals": 900, "long": 600}       # master section 5, to the credit


def test_the_estimate_form_really_exits_3_without_sending_anything(card, tmp_path, monkeypatch):
    tools = STUDIO_REAL / "tools" / "runway" / "runway_gen.py"
    if not tools.exists():
        pytest.skip("needs the studio hub's runway client")
    img = tmp_path / "s.png"
    cv2.imwrite(str(img), np.zeros((720, 1280, 3), np.uint8))
    env = {k: v for k, v in os.environ.items() if k != "RUNWAY_API_KEY"}
    for spec, want in ((ClipSpec("air", "gen45", "D", 2, "probe"), "24"), (ClipSpec("air", "gen45", "D", 10), "120")):
        argv = rc.build_command(spec, seed_for(spec), yes=False)
        argv = [sys.executable, str(tools)] + argv[1:]
        argv[argv.index("--image") + 1] = str(img)
        r = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=60)
        assert r.returncode == 3 and f"estimate ~{want} credits" in r.stderr and "--yes" in r.stderr


# ---- the start image --------------------------------------------------------------------------------

def test_start_image_is_a_pure_resize_and_is_written_once(card, fake_data):
    p = rc.make_start_image("air")
    got = cv2.imread(str(p))
    assert p == rc.start_image_path("air") and got.shape == (720, 1280, 3)
    assert np.array_equal(got, cv2.resize(fake_data, (1280, 720), interpolation=cv2.INTER_AREA))
    mtime = p.stat().st_mtime_ns
    assert rc.make_start_image("air") == p and p.stat().st_mtime_ns == mtime


def test_a_wrong_sized_start_frame_is_refused(card, monkeypatch):
    cv2.imwrite(str(card / "left.png"), np.zeros((100, 100, 3), np.uint8))
    rec = SimpleNamespace(left_path=lambda f: card / "left.png", start_frame=0)
    monkeypatch.setattr(rc, "recordings", lambda: {"air": rec})
    with pytest.raises(RuntimeError, match="expected 1242x2208"):
        rc.make_start_image("air")


def test_the_five_real_start_images_fit_the_inline_limit_and_match_mapping(card):
    recs = recordings()
    if not all(r.exists() for r in recs.values()):
        pytest.skip("needs the dataset link")
    from mapping import FILL_1280x720, warp_image
    for cond in recs:
        p = rc.make_start_image(cond)
        img = cv2.imread(str(p))
        assert img.shape == (720, 1280, 3) and p.stat().st_size <= rc.MAX_INLINE_BYTES
        real = cv2.imread(str(recs[cond].left_path(recs[cond].start_frame)))
        warped = warp_image(real, FILL_1280x720, 1280, 720)
        assert np.abs(img.astype(float) - warped).mean() < 2.0          # the frame-0 box test will read 'fill'


# ---- what to do about one clip ----------------------------------------------------------------------

def _pay(card, spec, outcome="ok"):
    fake = FakeRunway(card, outcome)
    lns, out = lines()
    code = rc.run_one(spec, yes=True, runner=fake, out=out)
    return code, fake, lns


def test_first_run_pays_once_then_skips(card, fake_data):
    spec = ClipSpec("air", "gen45", "D", 5)
    code, fake, lns = _pay(card, spec)
    assert code == 0 and len(fake.calls) == 1 and clips.check_clip(spec)["ok"]
    assert (card / "prototypes" / "divetwin" / "spend.jsonl").exists() and not Path("prototypes").exists()
    assert sg.runway_usd() == pytest.approx(0.60)              # spendguard reads the very row the fake client wrote
    argv = fake.calls[0]
    assert argv[argv.index("--seed") + 1] == str(seed_for(spec))
    code2, fake2, lns2 = _pay(card, spec)
    assert code2 == 0 and fake2.calls == [] and "skip" in lns2[0]
    assert sg.runway_usd() == pytest.approx(0.60)


def test_a_timed_out_task_is_fetched_never_paid_for_again(card, fake_data):
    spec = ClipSpec("air", "gen45", "D", 10)
    code, fake, _ = _pay(card, spec, "timeout")
    assert code == 4 and not video_path(spec).exists()
    task = rc.action_for(spec)["task"]
    assert rc.action_for(spec)["do"] == "fetch" and task.startswith("tc")
    fake2 = FakeRunway(card, frames=241)
    lns, out = lines()
    assert rc.run_one(spec, yes=True, runner=fake2, out=out) == 0
    assert fake2.calls[0][1] == "fetch" and fake2.calls[0][fake2.calls[0].index("--task") + 1] == task
    assert clips.check_clip(spec)["ok"] and sg.runway_usd() == pytest.approx(0.60)    # still one task's cost


def test_a_failed_or_unknown_call_is_refused_until_a_retake_reason(card, fake_data):
    spec = ClipSpec("air", "gen45", "B", 5)
    assert _pay(card, spec, "failed")[0] == 1
    a = rc.action_for(spec)
    assert a["do"] == "refuse" and "failed" in a["why"]
    code, fake, lns = _pay(card, spec)
    assert code == 1 and fake.calls == []
    # explicit retake: its own seed, the old file retired, the reason logged
    fake2 = FakeRunway(card)
    lns2, out2 = lines()
    assert rc.run_one(spec, yes=True, retake_reason="the first take failed", runner=fake2, out=out2) == 0
    assert fake2.calls[0][fake2.calls[0].index("--seed") + 1] == str(seed_for(spec, 1)) != str(seed_for(spec))
    rec = json.loads((card / "runs" / "retakes.jsonl").read_text().splitlines()[0])
    assert (rec["clip"], rec["retake"], rec["reason"]) == (spec.id, 1, "the first take failed")


def test_retaking_a_valid_clip_retires_it_first(card, fake_data):
    spec = ClipSpec("air", "gen45", "D", 5)
    _pay(card, spec)
    lns, out = lines()
    assert rc.run_one(spec, yes=True, retake_reason="it is a still", runner=FakeRunway(card), out=out) == 0
    retired = list((card / "runs" / "gen45" / "retired").glob("*.mp4"))
    assert len(retired) == 1 and retired[0].name.startswith(spec.id) and clips.check_clip(spec)["ok"]
    assert rc.retake_count(spec) == 1 and sg.runway_usd() == pytest.approx(1.20)


def test_an_invalid_download_is_reported_and_not_paid_for_again(card, fake_data):
    spec = ClipSpec("air", "gen45", "D", 5)
    fake = FakeRunway(card, frames=100)
    lns, out = lines()
    assert rc.run_one(spec, yes=True, runner=fake, out=out) == 1 and "INVALID: 100 frames, expected 121" in lns[-1]
    assert rc.action_for(spec)["do"] == "fetch"          # a finished task with a bad file: refetch is free, no new payment


def test_a_rejected_submit_costs_nothing_and_may_simply_be_retried(card, fake_data):
    spec = ClipSpec("air", "gen45", "D", 5)
    assert _pay(card, spec, "reject")[0] == 1 and sg.runway_usd() == 0.0
    assert rc.action_for(spec)["do"] == "refuse"           # unknown outcome is still a refusal: look, then --retake-reason


def test_without_yes_nothing_is_run_and_the_command_is_shown(card, fake_data):
    fake = FakeRunway(card)
    lns, out = lines()
    assert rc.run_one(ClipSpec("air", "gen45", "D", 5), yes=False, runner=fake, out=out) == 0
    assert fake.calls == [] and any("--yes to pay" in l for l in lns)
    assert shlex.split(next(l for l in lns if "would run" in l).split("would run: ")[1])[1] == "video"


def test_estimate_mode_runs_the_client_without_yes(card, fake_data):
    fake = FakeRunway(card)
    lns, out = lines()
    assert rc.run_one(ClipSpec("air", "gen45", "D", 5), yes=False, estimate=True, runner=fake, out=out) == 0
    assert len(fake.calls) == 1 and "--yes" not in fake.calls[0]


def test_the_generation_stop_blocks_the_call_before_runway_is_touched(card, fake_data):
    with open(card / "runs" / "modal_spend.jsonl", "w") as fh:
        fh.write(json.dumps({"task": "x", "usd_upper": 31.0}) + "\n")      # GBP 24.80
    fake = FakeRunway(card)
    lns, out = lines()
    code = rc.run_one(ClipSpec("air", "gen45", "D", 5), yes=True, runner=fake, out=out)    # +$0.60 = GBP 25.28
    assert code == 7 and fake.calls == [] and "generation stop" in "".join(lns)
    assert rc.run_one(ClipSpec("air", "gen45", "D", 2, "probe"), yes=True, runner=fake, out=out) == 0   # +$0.24 = 24.99


def test_a_batch_that_cannot_fit_the_stop_is_refused_whole(card, fake_data):
    with open(card / "runs" / "modal_spend.jsonl", "w") as fh:
        fh.write(json.dumps({"task": "x", "usd_upper": 28.0}) + "\n")      # GBP 22.40: probes ($3.60) fit; finals ($9) do not
    rc.record_gate("P", "test")
    fake = FakeRunway(card)
    lns, out = lines()
    assert rc.run_batch("finals", rc.plan_specs("finals"), yes=True, runner=fake, out=out) == 7 and fake.calls == []


def test_a_batch_stops_at_the_first_clip_that_does_not_end_well(card, fake_data):
    specs = rc.plan_specs("probes", only="air")
    fake = FakeRunway(card, "failed")
    lns, out = lines()
    assert rc.run_batch("probes", specs, yes=True, runner=fake, out=out) == 1 and len(fake.calls) == 1


def test_a_full_probe_round_pays_fifteen_clips_once(card, fake_data):
    fake = FakeRunway(card)
    lns, out = lines()
    specs = rc.plan_specs("probes")
    assert rc.run_batch("probes", specs, yes=True, runner=fake, out=out) == 0 and len(fake.calls) == 15
    assert sg.runway_usd() == pytest.approx(3.60)
    assert rc.run_batch("probes", specs, yes=True, runner=FakeRunway(card), out=out) == 0
    assert len(list((card / "runs" / "gen45").glob("*.mp4"))) == 15
    assert len(clips.rebuild_probes_index()["index"]) == 15 and clips.rebuild_clips_index()["index"] == {}


# ---- gates ------------------------------------------------------------------------------------------

def test_finals_and_the_long_dives_wait_for_gate_p(card, fake_data):
    lns, out = lines()
    for batch in ("finals", "long"):
        with pytest.raises(SystemExit, match="Gate P"):
            rc.run_batch(batch, rc.plan_specs(batch), yes=True, runner=FakeRunway(card), out=out)
    rc.record_gate("P", "Aaron read the probes")
    assert rc.run_batch("finals", rc.plan_specs("finals", only="air", prompt="D"), yes=False, out=out) == 0


def test_the_hunt_waits_for_gate_h_and_stays_on_its_recording(card, fake_data, tmp_path):
    spec = rc.plan_specs("hunt", condition="air", take=1)
    with pytest.raises(SystemExit, match="Gate H"):
        rc.require_gate("hunt", spec)
    d = tmp_path / "def.txt"
    d.write_text("an object not in the start frame that stays on screen for 12 frames")
    assert rc.main(["gate", "H", "--note", "Aaron", "--condition", "freshwater", "--definition-file", str(d)]) == 0
    with pytest.raises(SystemExit, match="freshwater"):
        rc.require_gate("hunt", spec)
    rc.require_gate("hunt", rc.plan_specs("hunt", condition="freshwater", take=1))
    assert "frame" in rc.read_gates()["H"]["definition"]
    with pytest.raises(ValueError):
        rc.plan_specs("hunt", condition="air", take=11)          # at most ten takes


def test_retake_needs_exactly_one_clip(card, fake_data):
    lns, out = lines()
    assert rc.run_batch("probes", rc.plan_specs("probes"), yes=True, retake_reason="why", runner=FakeRunway(card), out=out) == 2


def test_status_prints_the_money(card, fake_data):
    _pay(card, ClipSpec("air", "gen45", "D", 5))
    lns, out = lines()
    assert rc.cmd_status(out) == 0
    assert "GBP 0.48" in lns[0] and "finished" in lns[1]


def test_a_plan_makes_the_start_images_so_they_can_be_looked_at_before_paying(card, fake_data):
    lns, out = lines()
    assert rc.run_batch("probes", rc.plan_specs("probes", only="air"), yes=False, runner=FakeRunway(card), out=out) == 0
    assert rc.start_image_path("air").exists() and not rc.start_image_path("freshwater").exists()


# ---- the reviewer's findings: the cwd, the retake and hunt budget lines, the depth reserve -------------------------

def test_a_timed_out_clip_rerun_from_a_different_cwd_is_fetched_not_paid_again(card, fake_data, tmp_path, monkeypatch):
    spec = ClipSpec("air", "gen45", "D", 5)
    code, fake, _ = _pay(card, spec, "timeout")
    assert code == 4 and sg.runway_usd() == pytest.approx(0.60)       # the pending call is counted at its estimate
    monkeypatch.chdir(tmp_path)                                        # a different directory entirely
    assert rc.action_for(spec)["do"] == "fetch"
    fake2 = FakeRunway(card, frames=121)
    lns, out = lines()
    assert rc.run_one(spec, yes=True, runner=fake2, out=out) == 0
    assert [c[1] for c in fake2.calls] == ["fetch"] and sg.runway_usd() == pytest.approx(0.60)


def test_every_runner_call_is_given_the_hub_as_its_cwd(card, fake_data, monkeypatch):
    seen = []
    monkeypatch.setattr(rc.subprocess, "run", lambda cmd, **kw: seen.append(kw) or SimpleNamespace(returncode=0))
    rc.main(["fetch", "--clip", "air__gen45__D__5s", "--task", "t1", "--yes"])
    assert seen == [{"cwd": str(card)}]


def _calls(card, clip, n, cr=60):
    """n logged calls for one clip file (the first is the original, the rest are retakes)."""
    out = str(clips.video_path(clip))
    rows = []
    for i in range(n):
        cid = f"{clip.id}-{i}"
        rows += [{"event": "pre", "call_id": cid, "label": "video:gen4.5", "our_estimate": cr, "out": out},
                 {"event": "created", "call_id": cid, "task_id": "t" + cid, "estimated_cost_credits": cr},
                 {"event": "final", "call_id": cid, "task_id": "t" + cid, "status": "SUCCEEDED", "cost_credits": cr, "output_path": out}]
    with open(card / "prototypes" / "divetwin" / "spend.jsonl", "a") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_retakes_stop_at_300_credits(card, fake_data):
    for cond in list(RECORDING_NAMES)[:5]:
        _calls(card, ClipSpec(cond, "gen45", "D", 5), 2)                 # five retakes: 5 x 60 = 300
    assert rc.retake_credits_spent() == 300
    spec = ClipSpec("air", "gen45", "B", 5)
    fake = FakeRunway(card)
    lns, out = lines()
    assert rc.run_one(spec, yes=True, retake_reason="a sixth", runner=fake, out=out) == 1
    assert fake.calls == [] and "retakes have used 300 of the 300" in "".join(lns)
    assert rc.run_one(spec, yes=True, runner=fake, out=out) == 0 and len(fake.calls) == 1     # a first call is not a retake


def test_the_hunt_stops_at_600_credits_and_at_ten_takes(card, fake_data):
    d = card / "def.txt"
    d.write_text("an invention")
    rc.main(["gate", "H", "--note", "Aaron", "--condition", "air", "--definition-file", str(d)])
    for t in range(1, 11):
        _calls(card, ClipSpec("air", "gen45", "B", 5, "hunt", t), 1)
    assert rc.hunt_spent()[0] == 600 and len(rc.hunt_spent()[1]) == 10
    fake = FakeRunway(card)
    lns, out = lines()
    assert rc.run_one(ClipSpec("air", "gen45", "B", 5, "hunt", 3), yes=True, retake_reason="again", runner=fake, out=out) == 1
    assert "the hunt has used 600 of its 600" in "".join(lns) and fake.calls == []


def test_a_retake_is_refused_while_the_last_call_is_pending(card, fake_data):
    spec = ClipSpec("air", "gen45", "D", 5)
    assert _pay(card, spec, "timeout")[0] == 4
    a = rc.action_for(spec, "i want it again")
    assert a["do"] == "refuse" and "fetch it first" in a["why"]
    code, fake, lns = _pay(card, spec)                                  # the plain path fetches it
    assert fake.calls and fake.calls[0][1] == "fetch"
    fake3 = FakeRunway(card)
    lns3, out3 = lines()
    assert rc.run_one(spec, yes=True, retake_reason="x", runner=fake3, out=out3) == 0            # fetched: the retake may go


def test_the_hunt_holds_back_the_depth_it_still_needs(card, fake_data, monkeypatch):
    monkeypatch.setitem(clips.GRID, "gen45", (64, 48))
    for p in "DB":
        write_mp4(video_path(ClipSpec("air", "gen45", p, 5)), noise_frames(121, 64, 48))   # two indexed clips with no depth
    d = card / "def.txt"
    d.write_text("an invention")
    rc.main(["gate", "H", "--note", "Aaron", "--condition", "air", "--definition-file", str(d)])
    spec = ClipSpec("air", "gen45", "B", 5, "hunt", 1)
    reserve = sg.depth_reserve_usd(spec)
    assert reserve == pytest.approx(sg.depth_est_usd(363, 3)) and 0.15 < reserve < 0.25
    with open(card / "runs" / "modal_spend.jsonl", "w") as fh:
        fh.write(json.dumps({"task": "x", "usd_upper": 30.5}) + "\n")   # GBP 24.40: the take ($0.60) fits, the take plus depth does not
    sg.check_generation_cap(0.60)
    fake = FakeRunway(card)
    lns, out = lines()
    assert rc.run_one(spec, yes=True, runner=fake, out=out) == 7 and fake.calls == []
    assert "held back for depth" in "".join(lns)
    with open(card / "runs" / "modal_spend.jsonl", "w") as fh:
        fh.write(json.dumps({"task": "x", "usd_upper": 29.0}) + "\n")   # GBP 23.2: the reserve fits
    assert rc.run_one(spec, yes=True, runner=fake, out=out) == 0 and len(fake.calls) == 1


def test_a_depth_file_removes_a_clip_from_the_reserve(card, fake_data, monkeypatch):
    monkeypatch.setitem(clips.GRID, "gen45", (64, 48))
    a, b = ClipSpec("air", "gen45", "D", 5), ClipSpec("air", "gen45", "B", 5)
    for s in (a, b):
        write_mp4(video_path(s), noise_frames(121, 64, 48))
    two = sg.depth_reserve_usd()
    clips.depth_path(a).parent.mkdir(parents=True)
    clips.depth_path(a).write_bytes(b"x")
    assert sg.depth_reserve_usd() < two and sg.depth_reserve_usd() == pytest.approx(sg.depth_est_usd(121, 1))
    assert sg.depth_reserve_usd(ClipSpec("air", "gen45", "B", 5, "hunt", 1)) == pytest.approx(sg.depth_est_usd(242, 2))


# ---- batch 1 review fixes -----------------------------------------------------------------------------------

def test_the_still_running_hint_is_a_command_that_can_be_pasted(card, fake_data):
    spec = ClipSpec("air", "gen45", "D", 5)
    lns, out = lines()
    assert rc.run_one(spec, yes=True, runner=FakeRunway(card, "timeout"), out=out) == 4
    assert f"runway_calls.py fetch --clip {spec.id} --yes" in "".join(lns)


def test_a_different_runs_directory_never_hides_a_pending_call(card, fake_data, tmp_path, monkeypatch):
    spec = ClipSpec("air", "gen45", "D", 5)
    assert _pay(card, spec, "timeout")[0] == 4
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path / "another_runs"))       # the logged --out names the old directory
    a = rc.action_for(spec)
    assert a["do"] == "fetch" and a["task"]
    assert rc.action_for(spec, "again")["do"] == "refuse"                      # and a retake is still blocked while pending


def test_a_call_for_another_clip_with_a_similar_name_is_not_this_clips_call(card, fake_data):
    spec, other = ClipSpec("air", "gen45", "D", 5), ClipSpec("air", "gen45", "B", 5)
    assert _pay(card, other, "timeout")[0] == 4
    assert rc.action_for(spec)["do"] == "pay"


def test_a_rejected_call_says_it_was_not_billed(card, fake_data):
    spec = ClipSpec("air", "gen45", "D", 5)
    assert _pay(card, spec, "reject")[0] == 1
    a = rc.action_for(spec)
    assert a["do"] == "refuse" and "rejected, not billed" in a["why"]
