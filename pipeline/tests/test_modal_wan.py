import json
import re
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

import clips
import modal_common
import modal_wan
import runway_calls
import spendguard as sg
from clips import ClipSpec
from prompts import PROMPTS
from recordings import RECORDING_NAMES
from test_modal_helpers import PIPELINE, _decorated, _Remote, _run_dry, _top_level_third_party
from synth_video import noise_frames

SMALL = (64, 48)


@pytest.fixture
def card(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path / "runs"))
    monkeypatch.setenv("DIVETWIN_RUNWAY_LOG", str(tmp_path / "spend.jsonl"))
    monkeypatch.setitem(clips.GRID, "wan22", SMALL)
    (tmp_path / "runs").mkdir()
    img = np.random.default_rng(2).integers(0, 255, (1242, 2208, 3), dtype=np.uint8)
    cv2.imwrite(str(tmp_path / "left.png"), img)
    rec = SimpleNamespace(left_path=lambda f: tmp_path / "left.png", start_frame=0)
    monkeypatch.setattr(runway_calls, "recordings", lambda: {c: rec for c in RECORDING_NAMES})
    runway_calls.record_gate("P", "Aaron read the probes (test)")       # the full runs wait for it; --smoke does not
    return tmp_path


def rows(card):
    p = card / "runs" / "modal_spend.jsonl"
    return [json.loads(t) for t in p.read_text().splitlines()] if p.exists() else []


def smoked(card, wall_s=None):
    """An ok Wan smoke line that costs nothing in the sums: the full run is refused without one."""
    with open(card / "runs" / "modal_spend.jsonl", "a") as fh:
        fh.write(json.dumps({"task": "2.4-wan-smoke", "status": "ok", "n": 1, "usd_upper": 0.0, "gpu": "A100-80GB", "phase": 2,
                             "wall_s": wall_s or 60 + modal_wan.LOAD_S + 250}) + "\n")


def fake_wan(monkeypatch, frames=121, clock=None, step_s=0.0, fail_on=None):
    sent = []

    def generate(png, prompt, seed):
        sent.append({"png": png, "prompt": prompt, "seed": seed})
        if fail_on == len(sent):
            raise RuntimeError("the GPU call failed")
        if clock is not None:
            clock[0] += step_s
        return modal_wan.encode_mp4(np.stack([f[..., ::-1] for f in noise_frames(frames, *SMALL)])), 2.0
    monkeypatch.setattr(modal_wan, "WanI2V", lambda: SimpleNamespace(generate=_Remote(generate)))
    monkeypatch.setattr(modal_wan, "fetch_weights", _Remote(lambda *a, **k: {}))
    return sent


# ---- local pieces -----------------------------------------------------------------------------------

def test_encode_mp4_round_trips(tmp_path):
    frames = np.stack([f[..., ::-1] for f in noise_frames(7, *SMALL)])
    p = tmp_path / "a.mp4"
    p.write_bytes(modal_wan.encode_mp4(frames))
    r = clips.check_mp4(p, 7, SMALL)
    assert r["ok"] and r["fps"] == 24.0


def test_the_wan_start_is_the_gen45_start_cropped_by_16_rows(card):
    p = modal_wan.make_wan_start("air")
    got = cv2.imread(str(p))
    full = cv2.imread(str(runway_calls.start_image_path("air")))
    assert got.shape == (704, 1280, 3) and np.array_equal(got, full[8:712])
    assert modal_wan.wan_start_path("air").name == "air_wan.png"


def test_the_plan_is_fifteen_clips_and_skips_what_is_valid(card):
    todo = modal_wan.plan_specs()
    assert len(todo) == 15 and {s.engine for s in todo} == {"wan22"} and {s.seconds for s in todo} == {5}
    assert todo[0].id == "air__wan22__D__5s" and modal_wan.plan_specs(smoke=True) == todo[:1]
    assert [s.id for s in modal_wan.plan_specs(only="air", prompt="N")] == ["air__wan22__N__5s"]
    from synth_video import write_mp4
    write_mp4(clips.video_path(todo[0]), noise_frames(121, *SMALL))
    assert len(modal_wan.plan_specs()) == 14 and modal_wan.plan_specs(smoke=True) == []   # the smoke clip is done: never air B


def test_the_estimate_fits_the_task_cap_and_the_phase_total():
    est15 = modal_wan._est(15)
    assert est15 <= modal_wan.CAPS["wan"] <= sg.PHASE_TOTAL_USD[2]
    assert modal_wan._est(1) <= modal_wan.CAPS["smoke"]
    assert modal_wan.CAPS["fetch"] + modal_wan.CAPS["smoke"] + modal_wan.CAPS["wan"] > sg.PHASE_TOTAL_USD[2]   # the total binds
    assert modal_wan._est(0) < 0.1


# ---- a run with a fake remote -----------------------------------------------------------------------

def test_a_smoke_run_makes_one_clip_and_logs_fetch_and_clip_lines_tagged_phase_2(card, monkeypatch):
    sent = fake_wan(monkeypatch)
    modal_wan.run_wan(smoke=True)
    assert len(sent) == 1 and sent[0]["prompt"] == PROMPTS["D"]
    assert sent[0]["seed"] == clips.seed_for(ClipSpec("air", "wan22", "D", 5))
    assert cv2.imdecode(np.frombuffer(sent[0]["png"], np.uint8), 1).shape == (704, 1280, 3)
    assert clips.check_clip(ClipSpec("air", "wan22", "D", 5))["ok"]
    fetch, clip = rows(card)
    assert (fetch["task"], fetch["gpu"], fetch["phase"], fetch["n"]) == ("2.4-wan-fetch", None, 2, 1)
    assert (clip["task"], clip["gpu"], clip["phase"], clip["n"], clip["status"]) == ("2.4-wan-smoke", "A100-80GB", 2, 1, "ok")
    seeds = [json.loads(t) for t in (card / "runs" / "wan22" / "seeds.jsonl").read_text().splitlines()]
    assert seeds[0]["clip"] == "air__wan22__D__5s" and seeds[0]["revision"] == modal_wan.WAN_REV
    modal_wan.run_wan(smoke=True, only="air", prompt="D")            # nothing left to do for that clip: no remote call
    assert len(sent) == 1 and len(rows(card)) == 2


def test_b_and_n_are_sent_with_the_same_seed_and_their_own_words(card, monkeypatch):
    smoked(card)
    sent = fake_wan(monkeypatch)
    modal_wan.run_wan(only="saltwater", prompt="")
    by_prompt = {s["prompt"]: s["seed"] for s in sent}
    assert list(by_prompt) == [PROMPTS["D"], PROMPTS["B"], PROMPTS["N"]]
    assert by_prompt[PROMPTS["B"]] == by_prompt[PROMPTS["N"]] != by_prompt[PROMPTS["D"]]
    assert rows(card)[-1]["n"] == 3 and rows(card)[-1]["task"] == "2.4-wan"


def test_an_invalid_clip_is_kept_and_the_run_ends_as_an_error_line(card, monkeypatch):
    fake_wan(monkeypatch, frames=100)
    with pytest.raises(RuntimeError, match="not the expected one: 100 frames, expected 121"):
        modal_wan.run_wan(smoke=True)
    assert clips.video_path(ClipSpec("air", "wan22", "D", 5)).exists()
    assert rows(card)[-1]["status"] == "error" and rows(card)[-1]["n"] == 0


def test_a_failing_remote_call_still_leaves_a_spend_line(card, monkeypatch):
    smoked(card)
    fake_wan(monkeypatch, fail_on=2)
    with pytest.raises(RuntimeError, match="GPU call failed"):
        modal_wan.run_wan(only="air")
    last = rows(card)[-1]
    assert last["status"] == "error" and last["n"] == 1 and last["n_planned"] == 3 and last["phase"] == 2


def test_the_task_cap_stops_the_run_between_clips_and_is_cumulative(card, monkeypatch):
    smoked(card)
    clock = [1000.0]
    monkeypatch.setattr(modal_common.Meter, "_now", staticmethod(lambda: clock[0]))
    sent = fake_wan(monkeypatch, clock=clock, step_s=6000.0)         # each clip "takes" 6000 s: about $5.0
    with pytest.raises(SystemExit) as e:
        modal_wan.run_wan(only="air")
    assert "cap reached" in str(e.value.code) and len(sent) == 1
    line = rows(card)[-1]
    assert line["status"] == "cap" and line["n"] == 1 and line["phase"] == 2


def test_the_generation_stop_blocks_the_gpu_call(card, monkeypatch):
    with open(card / "runs" / "modal_spend.jsonl", "w") as fh:
        fh.write(json.dumps({"task": "old", "usd_upper": 31.0}) + "\n")    # GBP 24.80 already
    sent = fake_wan(monkeypatch)
    with pytest.raises(SystemExit) as e:
        modal_wan.run_wan(smoke=True)
    assert sent == [] and "cap reached" in str(e.value.code)
    assert rows(card)[-1]["status"] == "cap" and rows(card)[-1]["phase"] == 2


def test_a_run_is_refused_when_the_phase_total_would_pass(card):
    with open(card / "runs" / "modal_spend.jsonl", "w") as fh:
        fh.write(json.dumps({"task": "2.4-wan", "usd_upper": 5.4, "phase": 2}) + "\n")
    with pytest.raises(SystemExit) as e:
        modal_wan.run_wan(smoke=True)
    assert "Phase 2" in str(e.value.code)


# ---- the app definition, as for the other two apps ------------------------------------------------------

def test_every_class_and_function_sets_cpu_memory_and_timeout_and_the_gpu_is_pinned():
    dec = _decorated("modal_wan.py")
    assert set(dec) == {"WanI2V", "fetch_weights"}
    for name, (kw, _) in dec.items():
        assert {"cpu", "memory", "timeout"} <= set(kw), name
    assert "gpu" not in dec["fetch_weights"][0]
    src = (PIPELINE / "modal_wan.py").read_text()
    assert 'GPU = "A100-80GB"' in src and "gpu=GPU" in src and "cpu=(CPU, CPU)" in src
    assert "startup_timeout" in dec["WanI2V"][0] and "max_containers=1" in src
    assert modal_common.rate_per_s(modal_wan.GPU, modal_wan.CPU, modal_wan.MEM_GIB) > 2.5 / 3600


def test_timeouts_are_about_three_times_the_expected_time():
    exp = modal_wan.S_PER_CLIP + modal_wan.OVERHEAD_S
    assert 2.5 * exp <= modal_wan.CLIP_TIMEOUT_S <= 3.5 * exp + 30
    assert modal_wan.STARTUP_S >= 3 * modal_wan.LOAD_S - 30 and modal_wan.FETCH_DEADLINE_S == 1800
    assert modal_wan.FETCH_TIMEOUT_S >= 3 * modal_wan.FETCH_EXPECT_S - 30


def test_the_gpu_class_does_not_download_and_the_fetch_goes_through_the_deadline():
    src = (PIPELINE / "modal_wan.py").read_text()
    cls = src[src.index("class WanI2V"):src.index("# ---- local side")]
    assert "local_files_only=True" in cls and "gdown" not in cls
    assert "fetch_weights.remote" not in src and "call_with_deadline" in src


def test_the_weights_image_installs_every_top_level_import():
    src = (PIPELINE / "modal_wan.py").read_text()
    line = src[src.index("weights_image ="):].split("\n\n")[0]
    mods = _top_level_third_party(PIPELINE / "modal_wan.py")
    assert mods == set() or all(m.lower() in line.lower() for m in mods), mods


def test_image_packages_are_pinned_and_the_revision_matches_models_md():
    import ast
    tree = ast.parse((PIPELINE / "modal_wan.py").read_text())
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "pip_install":
            for a in node.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    assert "==" in a.value or "<" in a.value, a.value
                    n += 1
    assert n >= 10
    md = (PIPELINE / "MODELS.md").read_text()
    assert modal_wan.WAN_REV in md and modal_wan.WAN_REPO in md
    assert re.fullmatch(r"[0-9a-f]{40}", modal_wan.WAN_REV)


def test_the_grid_and_frame_count_are_the_plans():
    assert (modal_wan.WAN_W, modal_wan.WAN_H, modal_wan.WAN_FRAMES, modal_wan.WAN_FPS) == (1280, 704, 121, 24)
    assert clips.GRID["wan22"] == (1280, 704) or clips.GRID["wan22"] == SMALL


def test_no_prompt_text_is_retyped_in_the_wan_module():
    src = (PIPELINE / "modal_wan.py").read_text()
    assert all(t not in src for t in PROMPTS.values())


@pytest.mark.parametrize("args,code", [(["--dry-run"], 1), (["--dry-run", "--smoke"], 0),
                                        (["--dry-run", "--only", "air", "--prompt", "N"], 1)])
def test_dry_runs_work_offline_and_write_nothing(tmp_path, args, code):
    # a full run with no ok smoke line would be refused, so its dry run exits 1 like the real refusal; the smoke's exits 0
    r = _run_dry("modal_wan.py", *args, tmp_path=tmp_path)
    assert r.returncode == code, r.stderr[-2000:]
    assert "Wan clips to make; estimate $" in r.stdout and "cap $" in r.stdout and "Phase 2" in r.stdout
    assert not (tmp_path / "runs" / "modal_spend.jsonl").exists()


def test_paid_runs_are_refused_outside_modal_run(tmp_path):
    r = _run_dry("modal_wan.py", tmp_path=tmp_path)
    assert r.returncode != 0 and "modal run" in (r.stdout + r.stderr)


# ---- the reviewer's findings: Gate P, retakes, the hang guard, the projection from the smoke run -----------------

def test_the_full_run_waits_for_gate_p_but_the_smoke_does_not(card, monkeypatch):
    (card / "runs" / "gates.json").unlink()
    sent = fake_wan(monkeypatch)
    with pytest.raises(SystemExit, match="Gate P"):
        modal_wan.run_wan()
    assert sent == [] and rows(card) == []
    modal_wan.run_wan(smoke=True)
    assert len(sent) == 1


def test_an_invalid_file_is_never_regenerated_silently(card, monkeypatch):
    from synth_video import write_mp4
    spec = ClipSpec("air", "wan22", "D", 5)
    write_mp4(clips.video_path(spec), noise_frames(100, *SMALL))              # paid for, but 100 frames
    for args in ({}, {"smoke": True}, {"only": "air", "prompt": "D"}):
        with pytest.raises(SystemExit, match="retake it with --only"):
            modal_wan.plan_specs(**args)
    sent = fake_wan(monkeypatch)
    with pytest.raises(SystemExit, match="air__wan22__D__5s: 100 frames, expected 121"):
        modal_wan.run_wan(only="air")
    assert sent == [] and rows(card) == []


def test_a_wan_retake_retires_the_file_logs_the_reason_and_uses_the_next_seed(card, monkeypatch):
    smoked(card)
    from synth_video import write_mp4
    spec = ClipSpec("air", "wan22", "D", 5)
    write_mp4(clips.video_path(spec), noise_frames(100, *SMALL))
    sent = fake_wan(monkeypatch)
    with pytest.raises(SystemExit, match="exactly one clip"):
        modal_wan.plan_specs(retake_reason="why")
    modal_wan.run_wan(only="air", prompt="D", retake_reason="the first take was a still")
    assert sent[0]["seed"] == clips.seed_for(spec, 1) != clips.seed_for(spec)
    assert clips.check_clip(spec)["ok"] and len(list((card / "runs" / "wan22" / "retired").glob("*.mp4"))) == 1
    rec = json.loads((card / "runs" / "retakes.jsonl").read_text().splitlines()[0])
    assert (rec["clip"], rec["retake"], rec["reason"], rec["seed"]) == (spec.id, 1, "the first take was a still", clips.seed_for(spec, 1))
    assert clips.retake_count(spec) == 1
    seeds = [json.loads(t) for t in (card / "runs" / "wan22" / "seeds.jsonl").read_text().splitlines()]
    assert seeds[-1]["retake"] == 1
    # a retake of a valid clip is allowed too, with its own next seed
    modal_wan.run_wan(only="air", prompt="D", retake_reason="again")
    assert sent[1]["seed"] == clips.seed_for(spec, 2) and clips.retake_count(spec) == 2


class _SpawnRecorder:
    """A fake class whose generate is spawned and read with a deadline; records the deadline."""

    def __init__(self, hang=False):
        self.deadlines, self.hang = [], hang
        outer = self

        class Call:
            def get(self, timeout=None):
                outer.deadlines.append(timeout)
                if outer.hang:
                    raise TimeoutError()
                return modal_wan.encode_mp4(np.stack([f[..., ::-1] for f in noise_frames(121, *SMALL)])), 2.0

            def cancel(self):
                outer.cancelled = True

        class Gen:
            def spawn(self, *a):
                return Call()
        self.generate = Gen()


def test_every_gpu_call_has_a_deadline_and_the_first_adds_the_container_start(card, monkeypatch):
    smoked(card)
    rec = _SpawnRecorder()
    monkeypatch.setattr(modal_wan, "WanI2V", lambda: rec)
    monkeypatch.setattr(modal_wan, "fetch_weights", _Remote(lambda *a, **k: {}))
    modal_wan.run_wan(only="air")
    assert rec.deadlines == [modal_wan.STARTUP_S + modal_wan.CLIP_TIMEOUT_S] + [modal_wan.CLIP_TIMEOUT_S] * 2


def test_a_hung_gpu_call_ends_as_an_error_line_not_an_endless_bill(card, monkeypatch):
    import modal_common
    rec = _SpawnRecorder(hang=True)
    monkeypatch.setattr(modal_wan, "WanI2V", lambda: rec)
    monkeypatch.setattr(modal_wan, "fetch_weights", _Remote(lambda *a, **k: {}))
    with pytest.raises(modal_common.FetchDeadline):
        modal_wan.run_wan(smoke=True)
    last = rows(card)[-1]
    assert last["status"] == "error" and last["task"] == "2.4-wan-smoke" and last["phase"] == 2 and getattr(rec, "cancelled", False)


def _smoke_line(card, wall_s, n=1):
    with open(card / "runs" / "modal_spend.jsonl", "a") as fh:
        fh.write(json.dumps({"task": "2.4-wan-smoke", "status": "ok", "n": n, "wall_s": wall_s, "usd_upper": 0.5,
                             "gpu": "A100-80GB", "phase": 2}) + "\n")


def test_the_full_run_is_re_estimated_from_the_smoke_and_refused_when_it_does_not_fit(card, monkeypatch, capsys):
    sent = fake_wan(monkeypatch)
    _smoke_line(card, wall_s=60 + modal_wan.LOAD_S + 800)            # 800 s a clip: 15 clips would be about $10
    with pytest.raises(SystemExit) as e:
        modal_wan.run_wan()
    assert "does not fit" in str(e.value.code) and "no cap was raised" in str(e.value.code) and sent == []
    assert rows(card)[-1]["task"] == "2.4-wan-smoke"                 # nothing new was logged: not even the download started
    out = capsys.readouterr().out
    assert "re-estimated from the smoke run: 800.00 s a clip" in out


def test_a_smoke_that_fits_lets_the_run_go_and_the_dry_run_shows_the_projection(card, monkeypatch, capsys):
    sent = fake_wan(monkeypatch)
    _smoke_line(card, wall_s=60 + modal_wan.LOAD_S + 250)            # 250 s a clip: 15 clips about $3.4
    modal_wan.run_wan(only="air")
    assert len(sent) == 3 and "re-estimated from the smoke run: 250.00 s a clip" in capsys.readouterr().out
    modal_wan._dry(False, "saltwater", "", "")
    assert "projected at $" in capsys.readouterr().out


# ---- the re-review: no full run without an ok smoke line, and the per-call wall times are logged -------------------

def test_the_full_run_is_refused_when_no_ok_smoke_line_exists(card, monkeypatch, capsys):
    sent = fake_wan(monkeypatch)
    with pytest.raises(SystemExit) as e:
        modal_wan.run_wan(only="air")
    assert "no ok smoke run is logged" in str(e.value.code) and sent == [] and rows(card) == []
    with open(card / "runs" / "modal_spend.jsonl", "a") as fh:                  # an errored smoke is not an ok one
        fh.write(json.dumps({"task": "2.4-wan-smoke", "status": "error", "n": 0, "wall_s": 10, "usd_upper": 0.1, "phase": 2}) + "\n")
    with pytest.raises(SystemExit, match="no ok smoke run"):
        modal_wan.run_wan(only="air")
    assert sent == []


def test_the_dry_run_of_the_full_run_says_it_would_be_refused_without_a_smoke(card, capsys):
    with pytest.raises(SystemExit) as e:
        modal_wan._dry(False, "air", "", "")
    assert e.value.code == 1                                                      # the real refusal's code
    out = capsys.readouterr().out
    assert "Wan clips to make; estimate $" in out and "the full run would be refused" in out and "no ok smoke run" in out
    modal_wan._dry(True, "", "", "")                                              # the smoke itself is never refused
    assert "would be refused" not in capsys.readouterr().out


def test_each_gpu_calls_wall_time_is_logged_in_the_spend_line(card, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(modal_common.Meter, "_now", staticmethod(lambda: clock[0]))
    fake_wan(monkeypatch, clock=clock, step_s=100.0)
    modal_wan.run_wan(smoke=True)
    assert rows(card)[-1]["calls"] == [[100.0, 1]]


# ---- batch 2 review fixes ----------------------------------------------------------------------------------------

def test_a_capped_fetch_never_goes_on_to_the_gpu(card, monkeypatch):
    with open(card / "runs" / "modal_spend.jsonl", "w") as fh:        # the fetch's $0.15 cap is already spent
        fh.write(json.dumps({"task": "2.4-wan-fetch", "usd_upper": 0.20, "phase": 2}) + "\n")
    sent = fake_wan(monkeypatch)
    built = []
    monkeypatch.setattr(modal_wan, "WanI2V", lambda: built.append(1) or SimpleNamespace(generate=_Remote(lambda *a: None)))
    with pytest.raises(SystemExit, match=r"2\.4-wan-fetch: cap; the GPU was not started"):
        modal_wan.run_wan(smoke=True)
    assert sent == [] and built == []
    assert [r["task"] for r in rows(card)] == ["2.4-wan-fetch", "2.4-wan-fetch"]      # the old line and this run's cap line
    assert rows(card)[-1]["status"] == "cap"


def test_smoke_is_exactly_the_air_d_clip(card, monkeypatch):
    air_d = ClipSpec("air", "wan22", "D", 5)
    assert modal_wan.plan_specs(smoke=True) == [air_d]
    assert modal_wan.plan_specs(smoke=True, only="air", prompt="D") == [air_d]
    for bad in ({"only": "saltwater"}, {"prompt": "B"}, {"only": "saltwater", "prompt": "D"}):
        with pytest.raises(SystemExit, match="smoke clip is air, prompt D"):
            modal_wan.plan_specs(smoke=True, **bad)
    sent = fake_wan(monkeypatch)
    with pytest.raises(SystemExit, match="smoke clip is air, prompt D"):
        modal_wan.run_wan(smoke=True, only="air", prompt="B")
    assert sent == [] and rows(card) == []


def test_a_smoke_never_picks_another_clip_when_the_smoke_clip_is_done(card, monkeypatch):
    sent = fake_wan(monkeypatch)
    modal_wan.run_wan(smoke=True)
    assert len(sent) == 1
    assert modal_wan.plan_specs(smoke=True) == []                      # done: not air B, the next clip in the list
    modal_wan.run_wan(smoke=True)
    assert len(sent) == 1


def test_a_retake_of_the_smoke_clip_stays_allowed(card, monkeypatch):
    sent = fake_wan(monkeypatch)
    modal_wan.run_wan(smoke=True)
    spec = ClipSpec("air", "wan22", "D", 5)
    assert modal_wan.plan_specs(smoke=True, retake_reason="why") == [spec]
    modal_wan.run_wan(smoke=True, only="air", prompt="D", retake_reason="the smoke clip was a still")
    assert len(sent) == 2 and sent[1]["seed"] == clips.seed_for(spec, 1)


def test_a_retake_of_a_clip_that_is_not_on_disk_is_refused(card, monkeypatch):
    sent = fake_wan(monkeypatch)
    with pytest.raises(SystemExit, match="nothing to retake"):
        modal_wan.plan_specs(only="air", prompt="D", retake_reason="why")
    with pytest.raises(SystemExit, match="nothing to retake"):
        modal_wan.run_wan(smoke=True, retake_reason="why")
    assert sent == [] and rows(card) == [] and not (card / "runs" / "retakes.jsonl").exists()


def _smoke_calls_line(card, local_s):
    """An ok Wan smoke: one call of 450 s of GPU in 500 s of wall, then `local_s` of local transfer and check work."""
    with open(card / "runs" / "modal_spend.jsonl", "a") as fh:
        fh.write(json.dumps({"task": "2.4-wan-smoke", "status": "ok", "n": 1, "usd_upper": 0.0, "gpu": "A100-80GB", "phase": 2,
                             "gpu_s_in_calls": 450.0, "calls": [[500.0, 1]], "wall_s": 60 + 500 + local_s}) + "\n")


def test_the_wan_projection_adds_the_smokes_per_clip_transfer_and_check_time(card):
    _smoke_calls_line(card, local_s=10)
    quick = modal_wan._projection([None] * 14, "wan")
    _smoke_calls_line(card, local_s=120)
    slow = modal_wan._projection([None] * 14, "wan")
    assert quick["s_per_unit"] == slow["s_per_unit"] == pytest.approx(450.0)
    assert quick["per_clip_s"] == modal_wan.OVERHEAD_S and slow["per_clip_s"] == pytest.approx(120.0)
    assert slow["projected_usd"] - quick["projected_usd"] == pytest.approx(14 * (120 - 30) * modal_common.rate_per_s("A100-80GB", 4, 40))


def test_the_dry_run_exits_1_when_the_projection_does_not_fit_and_0_when_it_does(card, monkeypatch, capsys):
    _smoke_line(card, wall_s=60 + modal_wan.LOAD_S + 800)             # 800 s a clip: 15 clips would be about $10
    with pytest.raises(SystemExit) as e:
        modal_wan._dry(False, "", "", "")
    assert e.value.code == 1 and "no cap was raised" in capsys.readouterr().out + str(e.value)
    modal_wan._dry(True, "", "", "")                                  # the smoke is never refused
    with open(card / "runs" / "modal_spend.jsonl", "w") as fh:
        fh.write(json.dumps({"task": "2.4-wan-smoke", "status": "ok", "n": 1, "usd_upper": 0.0, "wall_s": 60 + 300 + 250, "phase": 2}) + "\n")
    modal_wan._dry(False, "saltwater", "", "")                        # 3 clips at 250 s fit: exits 0
    assert "projected at $" in capsys.readouterr().out
