import json
import pytest

import modal_common
import spendguard as sg

@pytest.fixture
def card(tmp_path, monkeypatch):
    """An empty card: its own runs/ and Runway log."""
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path / "runs"))
    monkeypatch.setenv("DIVETWIN_RUNWAY_LOG", str(tmp_path / "spend.jsonl"))
    (tmp_path / "runs").mkdir()
    return tmp_path


def rw(card, *rows):
    with open(card / "spend.jsonl", "a") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def modal(card, *rows):
    with open(card / "runs" / "modal_spend.jsonl", "a") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def call(cid, est=60, tid=None, cost=None, status="SUCCEEDED", out=None):
    rows = [{"event": "pre", "call_id": cid, "label": "video:gen4.5", "our_estimate": est, "out": out}]
    if tid:
        rows.append({"event": "created", "call_id": cid, "task_id": tid, "estimated_cost_credits": est})
    if cost != "none" and tid:
        rows.append({"event": "final", "call_id": cid, "task_id": tid, "status": status, "cost_credits": cost,
                     "output_path": out})
    return rows


def test_the_rate_is_stated_and_slightly_pessimistic():
    assert sg.GBP_PER_USD == 0.80 and sg.GBP_PER_USD > 0.787
    assert (sg.GENERATION_STOP_GBP, sg.CARD_CAP_GBP) == (25.0, 30.0) and modal_common.PHASE1_CAP_USD == 5.00


def test_final_rows_set_the_cost_not_the_estimate(card):
    rw(card, *call("a", est=60, tid="t1", cost=55), *call("b", est=24, tid="t2", cost=24))
    assert sg.runway_usd() == pytest.approx(0.79)


def test_a_call_with_no_final_row_counts_at_the_larger_estimate(card):
    rw(card, {"event": "pre", "call_id": "a", "our_estimate": 60}, {"event": "created", "call_id": "a", "task_id": "t",
                                                                      "estimated_cost_credits": 120},
       {"event": "timeout", "call_id": "a", "task_id": "t"})
    assert sg.runway_usd() == pytest.approx(1.20)
    assert [c["state"] for c in sg.runway_calls()] == ["pending"]
    rw(card, {"event": "pre", "call_id": "b", "our_estimate": 70})          # crashed before any answer
    assert sg.runway_usd() == pytest.approx(1.90)


def test_a_fetch_row_finishes_a_timed_out_call_and_is_counted_once(card):
    rw(card, {"event": "pre", "call_id": "a", "our_estimate": 120}, {"event": "created", "call_id": "a", "task_id": "t",
                                                                       "estimated_cost_credits": 120},
       {"event": "timeout", "call_id": "a", "task_id": "t"},
       {"event": "fetch", "task_id": "t", "status": "SUCCEEDED", "cost_credits": 110, "output_path": "x.mp4"},
       {"event": "fetch", "task_id": "t", "status": "SUCCEEDED", "cost_credits": 110, "output_path": "x.mp4"})
    (c,) = sg.runway_calls()
    assert c["state"] == "finished" and c["counted"] == 110 and sg.runway_usd() == pytest.approx(1.10)


def test_a_rejected_submit_is_free_but_a_network_failure_is_not(card):
    rw(card, {"event": "pre", "call_id": "a", "our_estimate": 60},
       {"event": "submit_error", "call_id": "a", "status": 400, "error": "bad ratio"},
       {"event": "pre", "call_id": "b", "our_estimate": 60},
       {"event": "submit_error", "call_id": "b", "status": 0, "error": "timed out"},
       {"event": "pre", "call_id": "c", "our_estimate": 60},
       {"event": "submit_error", "call_id": "c", "status": 429, "error": "slow down"})
    states = {c["call_id"]: (c["state"], c["counted"]) for c in sg.runway_calls()}
    assert states == {"a": ("rejected", 0.0), "b": ("unknown", 60), "c": ("unknown", 60)}


def test_a_failed_task_without_a_cost_counts_its_estimate(card):
    rw(card, *call("a", est=60, tid="t", cost=None, status="FAILED"))
    assert [c["state"] for c in sg.runway_calls()] == ["failed"] and sg.runway_usd() == pytest.approx(0.60)


def test_a_zero_cost_is_zero(card):
    rw(card, *call("a", est=60, tid="t", cost=0))
    assert sg.runway_usd() == 0.0


GATE_T = [  # the card's own log after Gate T (3 Nov): the eval still (5 credits) and the eval clip (25 credits), paths shortened
    {"event": "pre", "call_id": "bd3599c8d20d", "label": "eval-image", "model": "gemini_2.5_flash", "our_estimate": 4, "seed": "first output", "out": "still.png"},
    {"event": "created", "call_id": "bd3599c8d20d", "task_id": "e29690f7", "estimated_cost_credits": 5},
    {"event": "final", "call_id": "bd3599c8d20d", "task_id": "e29690f7", "status": "SUCCEEDED", "cost_credits": 5, "output_path": "still.png"},
    {"event": "pre", "call_id": "8c8f51939202", "label": "eval-video", "model": "gen4_turbo", "our_estimate": 25, "seed": "first output", "out": "clip.mp4"},
    {"event": "created", "call_id": "8c8f51939202", "task_id": "a04f51a4", "estimated_cost_credits": 25},
    {"event": "final", "call_id": "8c8f51939202", "task_id": "a04f51a4", "status": "SUCCEEDED", "cost_credits": 25, "output_path": "clip.mp4"},
]


def test_the_gate_t_log_reads_as_30_credits(card):
    rw(card, *GATE_T)
    assert sg.runway_usd() == pytest.approx(0.30)


def test_modal_total_honours_corrections_and_all_phases(card):
    modal(card, {"task": "1.3a-smoke", "usd_upper": 0.652}, {"task": "1.3a-smoke", "status": "correction", "usd_upper": -0.648},
          {"task": "2.4-wan", "usd_upper": 1.5, "phase": 2}, {"task": "t", "usd_upper": None})
    with open(card / "runs" / "modal_spend.jsonl", "a") as fh:
        fh.write("torn li\n")
    assert sg.modal_usd() == pytest.approx(0.004 + 1.5)


PHASE_1_LINES = [  # runs/modal_spend.jsonl at the end of Phase 1 (3 Nov), usd_upper only; the correction is call 42's
    ("smoke", 0.094), ("1.2-masks", 0.225), ("1.2-masks", 0.08), ("1.2-masks", 0.083), ("1.2-masks", 0.081),
    ("1.3a-smoke", 0.652), ("1.3a-smoke", -0.648), ("1.3a-smoke", 0.067), ("2b-dytest", 0.06), ("2b-dytest", 0.063),
    ("1.3a", 0.491), ("1.5-floor", 0.313), ("1.7-selftest", 0.105)]


def test_the_phase_1_log_sums_to_the_status_figure(card):
    modal(card, *({"task": t, "usd_upper": u} for t, u in PHASE_1_LINES))
    assert sg.modal_usd() == pytest.approx(1.666, abs=0.002)        # STATUS: Modal Phase 1 $1.666
    rw(card, *GATE_T)
    assert sg.spent()["total_gbp"] == pytest.approx((1.666 + 0.30) * 0.80, abs=0.002)


def test_the_stop_refuses_a_call_that_would_pass_25_pounds(card):
    modal(card, {"task": "x", "usd_upper": 10.0})
    rw(card, *call("a", est=2000, tid="t", cost=2000))              # $20 of Runway: $30 = GBP 24.00
    s = sg.check_generation_cap(1.0)                                # GBP 24.80: fits
    assert s["after_gbp"] == pytest.approx(24.80) and s["total_gbp"] == pytest.approx(24.0)
    with pytest.raises(sg.GenerationStop) as e:
        sg.check_generation_cap(1.5)                                # GBP 25.20
    assert "25.00" in str(e.value) and "25.20" in str(e.value)
    assert sg.check_generation_cap(1.5, cap_gbp=30.0)["cap_gbp"] == 30.0
    with pytest.raises(sg.GenerationStop):
        sg.check_generation_cap(0.5, extra_usd=1.0)                  # a running section's unlogged bound counts


def test_the_stop_is_a_cap_reached_so_a_modal_section_logs_a_cap_line(card):
    modal(card, {"task": "x", "usd_upper": 31.0})                   # GBP 24.80
    m = sg.GuardedMeter("A100-80GB", 5.0, "2.4-wan", 2, cpu=4, mem_gib=40)
    with m.section("2.4-wan", "divetwin-wan", n_planned=1):
        m.remote(lambda: 1 / 0, est_s=3600)                          # $3: would pass GBP 25
    line = json.loads((card / "runs" / "modal_spend.jsonl").read_text().splitlines()[-1])
    assert line["status"] == "cap" and line["phase"] == 2 and line["usd_upper"] == 0.0 and line["n"] == 0


def test_guarded_meter_tags_clamps_and_checks(card):
    modal(card, {"task": "old", "usd_upper": 1.0},                   # Phase 1: not in Phase 2's sum
          {"task": "2.4-wan-smoke", "usd_upper": 4.8, "phase": 2})
    assert sg.phase_spent_usd(2) == pytest.approx(4.8) and sg.phase_spent_usd(1) == pytest.approx(1.0)
    m = sg.GuardedMeter("A100-80GB", 4.5, "2.4-wan", 2, cpu=4, mem_gib=40)
    assert m.phase == 2 and m.cap == pytest.approx(0.0 + sg.PHASE_TOTAL_USD[2] - 4.8)  # the phase total binds, not the task cap
    assert sg.GuardedMeter("A100-80GB", 0.1, "2.4-wan", 2).cap == pytest.approx(0.1)
    with pytest.raises(SystemExit) as e:
        sg.check_phase_total(2, 1.1)
    assert "Phase 2" in str(e.value.code) and "$5.80" in str(e.value.code)
    sg.check_phase_total(3, 1.9)
    with pytest.raises(SystemExit):
        sg.check_phase_total(3, 2.1)


def test_phase_one_machinery_is_untouched(card):
    modal(card, {"task": "a", "usd_upper": 2.0}, {"task": "b", "usd_upper": 2.9})
    assert modal_common.PHASE1_CAP_USD == 5.00 and modal_common.phase_total_usd() == pytest.approx(4.9)
    m = modal_common.Meter("L40S", 1.0, task="a", cpu=4, mem_gib=16)
    assert m.phase is None
    m.calls = 1
    line = m.log("a", "app", 1)
    assert "phase" not in line                                      # Phase 1 lines carry no tag


def test_a100_rate_is_pinned_for_the_wan_meter():
    assert modal_common.USD_PER_GPU_HOUR["A100-80GB"] == 2.50
    assert modal_common.rate_per_s("A100-80GB") == pytest.approx(2.50 / 3600)


# ---- the reviewer's findings: the projection from a smoke run, the check without a call, the reserve ---------------

def _smoke(card, task, n, wall_s, status="ok", phase=2):
    modal(card, {"task": task, "status": status, "n": n, "wall_s": wall_s, "usd_upper": 0.3, "phase": phase})


def test_projection_uses_the_last_ok_smoke_line_and_floors_the_marginal_at_zero(card):
    assert sg.projection_from_smoke("2.4-wan-smoke", 14, 300, 0.001) is None
    _smoke(card, "2.4-wan-smoke", 1, 9999, status="error")                # an errored smoke says nothing
    assert sg.projection_from_smoke("2.4-wan-smoke", 14, 300, 0.001) is None
    _smoke(card, "2.4-wan-smoke", 1, 60 + 300 + 400)                       # 400 s a clip
    p = sg.projection_from_smoke("2.4-wan-smoke", 14, 300, 0.001)
    assert p["s_per_unit"] == pytest.approx(400) and p["projected_usd"] == pytest.approx((300 + 60 + 14 * 400) * 0.001)
    _smoke(card, "2.4-wan-smoke", 1, 100)                                  # faster than the assumed load: not negative
    assert sg.projection_from_smoke("2.4-wan-smoke", 14, 300, 0.001)["s_per_unit"] == 0.0


def test_require_projection_fits_refuses_without_a_smoke_and_stops_for_aaron_when_it_does_not_fit(card, capsys):
    with pytest.raises(SystemExit) as e:                                     # no ok smoke line: the nominal estimate is not enough
        sg.require_projection_fits(None, task="2.4-wan", task_cap=4.5, baseline=0.0, phase=2, n_remaining=14, unit="clip")
    assert "no ok smoke run is logged" in str(e.value.code) and "nothing was started" in str(e.value.code).lower()
    ok = {"s_per_unit": 250.0, "projected_usd": 3.0, "smoke_usd": 0.5, "units": 1}
    sg.require_projection_fits(ok, task="2.4-wan", task_cap=4.5, baseline=0.0, phase=2, n_remaining=14, unit="clip")
    over = {**ok, "projected_usd": 4.6}
    with pytest.raises(SystemExit) as e:
        sg.require_projection_fits(over, task="2.4-wan", task_cap=4.5, baseline=0.0, phase=2, n_remaining=14, unit="clip")
    assert "Aaron's decision" in str(e.value.code) and "no cap was raised" in str(e.value.code)
    modal(card, {"task": "2.4-wan-smoke", "usd_upper": 2.0, "phase": 2})           # the phase total binds too
    with pytest.raises(SystemExit):
        sg.require_projection_fits({**ok, "projected_usd": 4.0}, task="2.4-wan", task_cap=4.5, baseline=0.0, phase=2,
                                   n_remaining=14, unit="clip")


def test_check_refuses_without_sending_anything(card):
    modal(card, {"task": "x", "usd_upper": 31.0})                           # GBP 24.80
    m = sg.GuardedMeter("A100-80GB", 4.5, "2.4-wan", 2, cpu=4, mem_gib=40)
    with pytest.raises(sg.GenerationStop):
        m.check(3600)
    assert m.calls == 0
    m2 = sg.GuardedMeter("A100-80GB", 0.05, "2.4-wan", 2, cpu=4, mem_gib=40)
    with pytest.raises(modal_common.CapReached):
        m2.check(3600)                                                      # over its own cap (and the stop is not the reason)


def test_the_depth_estimate_and_an_empty_reserve(card):
    assert sg.depth_est_usd(121, 1) == pytest.approx((90 + 20 + 60 + 121 * 0.25) * modal_common.rate_per_s("L40S", 4, 16))
    assert sg.depth_est_usd(4835, 35) > sg.depth_est_usd(4835, 35, 0.1)
    assert sg.depth_reserve_usd() == 0.0


# ---- the re-review: warm calls only, the smoke's measured rate in the reserve, no full run without a smoke ------------

def _smoke_calls(card, task, calls, n, wall_s, gpu_s=0.0, phase=3):
    modal(card, {"task": task, "status": "ok", "n": n, "wall_s": wall_s, "gpu_s_in_calls": gpu_s, "calls": calls,
                 "usd_upper": 0.1, "phase": phase})


def test_the_projection_takes_its_rate_from_the_warm_calls_so_a_wrong_load_time_cannot_make_it_low(card):
    # 120 frames in 5 calls of 24; the first carries the container start and the load, the rest are warm at 0.5 s a frame
    calls = [[95.0, 24], [12.0, 24], [12.0, 24], [12.0, 24], [12.0, 24]]
    _smoke_calls(card, "3.1-depth-smoke", calls, 120, wall_s=60 + 95 + 48)
    for assumed_load in (90, 400):             # an assumed load longer than the real one used to drive the figure to zero
        p = sg.projection_from_smoke("3.1-depth-smoke", 1000, assumed_load, 0.001)
        assert p["s_per_unit"] == pytest.approx(0.5)
        assert p["projected_usd"] == pytest.approx((assumed_load + 60 + 1000 * 0.5) * 0.001)


def test_a_call_with_no_units_is_not_the_load_call(card):
    calls = [[30.0, 0], [90.0, 24], [12.0, 24], [12.0, 24]]               # a CPU fetch first, then the call that loads DA3
    _smoke_calls(card, "3.1-depth-smoke", calls, 72, wall_s=999)
    assert sg.projection_from_smoke("3.1-depth-smoke", 10, 90, 0.001)["s_per_unit"] == pytest.approx(0.5)


def test_with_no_warm_call_the_rate_is_the_larger_of_the_gpu_time_and_the_old_formula(card):
    _smoke_calls(card, "2.4-wan-smoke", [[500.0, 1]], 1, wall_s=60 + 300 + 100, gpu_s=450.0, phase=2)
    assert sg.projection_from_smoke("2.4-wan-smoke", 14, 300, 0.001)["s_per_unit"] == pytest.approx(450.0)   # not the formula's 100
    _smoke_calls(card, "2.4-wan-smoke", [[500.0, 1]], 1, wall_s=60 + 300 + 400, gpu_s=200.0, phase=2)
    assert sg.projection_from_smoke("2.4-wan-smoke", 14, 300, 0.001)["s_per_unit"] == pytest.approx(400.0)


def test_the_hunts_reserve_uses_the_smokes_measured_rate_when_it_is_slower_than_the_nominal(card, monkeypatch):
    import clips
    from clips import ClipSpec
    monkeypatch.setitem(clips.GRID, "gen45", (64, 48))
    from synth_video import noise_frames, write_mp4
    write_mp4(clips.video_path(ClipSpec("air", "gen45", "D", 5)), noise_frames(121, 64, 48))
    nominal = sg.depth_reserve_usd()
    assert nominal == pytest.approx(sg.depth_est_usd(121, 1))
    _smoke_calls(card, "3.1-depth-smoke", [[95.0, 24], [24.0, 24], [24.0, 24]], 72, wall_s=60 + 143 + 10)   # 1.0 s a frame warm
    assert sg.depth_s_per_frame() == pytest.approx(1.0)
    assert sg.depth_reserve_usd() == pytest.approx(sg.depth_est_usd(121, 1, 1.0)) and sg.depth_reserve_usd() > nominal
    _smoke_calls(card, "3.1-depth-smoke", [[80.0, 24], [1.0, 24], [1.0, 24]], 72, wall_s=60 + 82 + 10)      # a faster smoke: never below nominal
    assert sg.depth_s_per_frame() == sg.DEPTH_S_PER_FRAME and sg.depth_reserve_usd() == pytest.approx(nominal)


def test_the_meter_logs_each_remote_calls_wall_time_and_units_on_phase_lines_only(card, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(modal_common.Meter, "_now", staticmethod(lambda: clock[0]))

    def work(step):
        clock[0] += step
        return step
    m = sg.GuardedMeter("L40S", 5.0, "3.1-depth-smoke", 3, cpu=4, mem_gib=16)
    with m.section("3.1-depth-smoke", "app", n_planned=3):
        m.remote(work, 30.0, est_s=1, units=0)
        m.remote(work, 12.0, est_s=1, units=24)
        m.remote(work, 6.0, est_s=1, units=12)
        m.n_done = 36
    line = json.loads((card / "runs" / "modal_spend.jsonl").read_text().splitlines()[-1])
    assert line["calls"] == [[30.0, 0], [12.0, 24], [6.0, 12]]
    p1 = modal_common.Meter("L40S", 1.0, task="a", cpu=4, mem_gib=16)
    p1.calls = 1
    assert "calls" not in p1.log("a", "app", 1)                          # Phase 1's line is exactly what it was


# ---- batch 2 review: the projection must not come out low (I2) -----------------------------------------------------

L40S = modal_common.rate_per_s("L40S", 4, 16)


def test_the_load_is_the_larger_of_the_assumed_one_and_what_the_first_work_call_shows(card):
    # the first work call took 200 s for 24 frames that run at 0.5 s warm: 188 s of it was container start and load
    calls = [[30.0, 0], [200.0, 24], [12.0, 24], [12.0, 24]]
    _smoke_calls(card, "3.1-depth-smoke", calls, 72, wall_s=60 + 30 + 224)
    p = sg.projection_from_smoke("3.1-depth-smoke", 1000, 90, 0.001)
    assert p["load_s"] == pytest.approx(188.0)
    assert p["projected_usd"] == pytest.approx((188 + 60 + 1000 * 0.5) * 0.001)
    assert sg.projection_from_smoke("3.1-depth-smoke", 1000, 400, 0.001)["load_s"] == 400      # never below the assumed load


def test_slow_local_work_in_the_smoke_projects_higher(card):
    # 120 frames of one clip: the calls add up to 143 s, but the wall minus scaledown is 243 s: 100 s of decode, encode,
    # median, savez and check_depth that the GPU meter pays for
    calls = [[95.0, 24], [12.0, 24], [12.0, 24], [12.0, 24], [12.0, 24]]
    _smoke_calls(card, "3.1-depth-smoke", calls, 120, wall_s=60 + 143 + 100)
    slow = sg.projection_from_smoke("3.1-depth-smoke", 1000, 90, L40S, n_clips=10)
    assert slow["per_clip_s"] == pytest.approx(100.0)
    assert slow["projected_usd"] == pytest.approx((90 + 60 + 1000 * 0.5 + 10 * 100) * L40S)
    _smoke_calls(card, "3.1-depth-smoke", calls, 120, wall_s=60 + 143 + 2)             # local work faster than the nominal 20 s
    fast = sg.projection_from_smoke("3.1-depth-smoke", 1000, 90, L40S, n_clips=10)
    assert fast["per_clip_s"] == sg.DEPTH_OVERHEAD_S                                   # the nominal is the floor
    assert slow["projected_usd"] > fast["projected_usd"]


def test_the_per_clip_term_counts_every_clip_still_to_do(card):
    calls = [[95.0, 24], [12.0, 24], [12.0, 24]]
    _smoke_calls(card, "3.1-depth-smoke", calls, 72, wall_s=60 + 119 + 60)
    one = sg.projection_from_smoke("3.1-depth-smoke", 100, 90, 0.001, n_clips=1)["projected_usd"]
    ten = sg.projection_from_smoke("3.1-depth-smoke", 100, 90, 0.001, n_clips=10)["projected_usd"]
    assert ten - one == pytest.approx(9 * 60 * 0.001)


def test_a_line_without_calls_has_no_measured_local_work_so_the_nominal_overhead_stands(card):
    _smoke_calls(card, "3.1-depth-smoke", [], 121, wall_s=60 + 90 + 121 * 0.5)
    p = sg.projection_from_smoke("3.1-depth-smoke", 100, 90, 0.001, n_clips=4)
    assert p["per_clip_s"] == sg.DEPTH_OVERHEAD_S and p["projected_usd"] == pytest.approx((90 + 60 + 100 * 0.5 + 4 * 20) * 0.001)


def test_wan_keeps_the_gpu_time_fallback_and_adds_a_per_clip_transfer_and_check_term(card):
    # one clip: 450 s on the GPU, 500 s call wall (transfer and container start), 90 s of local decode and check after it
    _smoke_calls(card, "2.4-wan-smoke", [[500.0, 1]], 1, wall_s=60 + 500 + 90, gpu_s=450.0, phase=2)
    p = sg.projection_from_smoke("2.4-wan-smoke", 14, 300, 0.001, n_clips=14, overhead_s=30)
    assert p["s_per_unit"] == pytest.approx(450.0)                                       # the fallback, unchanged
    assert p["per_clip_s"] == pytest.approx(90.0)
    assert p["projected_usd"] == pytest.approx((300 + 60 + 14 * 450 + 14 * 90) * 0.001)


def test_the_hunts_reserve_carries_the_same_per_clip_term_and_load(card, monkeypatch):
    import clips
    from clips import ClipSpec
    monkeypatch.setitem(clips.GRID, "gen45", (64, 48))
    from synth_video import noise_frames, write_mp4
    write_mp4(clips.video_path(ClipSpec("air", "gen45", "D", 5)), noise_frames(121, 64, 48))
    # 0.5 s a frame warm (slower than the nominal 0.25), a long load and slow local work (100 s a clip)
    calls = [[30.0, 0], [240.0, 24], [12.0, 24], [12.0, 24]]
    _smoke_calls(card, "3.1-depth-smoke", calls, 72, wall_s=60 + 30 + 240 + 24 + 100)
    assert sg.depth_s_per_frame() == pytest.approx(0.5)
    want = sg.depth_est_usd(121, 1, 0.5, load_s=228.0, overhead_s=100.0)
    assert sg.depth_reserve_usd() == pytest.approx(want)
    assert want > sg.depth_est_usd(121, 1, 0.5)


def test_projection_refusal_is_the_message_the_real_refusal_and_the_dry_run_share(card):
    kw = dict(task="2.4-wan", task_cap=4.5, baseline=0.0, phase=2, n_remaining=14, unit="clip")
    assert sg.projection_refusal(None, **kw) == sg.no_smoke_message("2.4-wan")
    ok = {"s_per_unit": 250.0, "projected_usd": 3.0, "smoke_usd": 0.5, "units": 1}
    assert sg.projection_refusal(ok, **kw) is None
    msg = sg.projection_refusal({**ok, "projected_usd": 4.6}, **kw)
    assert "Aaron's decision" in msg and "no cap was raised" in msg
    with pytest.raises(SystemExit) as e:
        sg.require_projection_fits({**ok, "projected_usd": 4.6}, **kw)
    assert str(e.value.code) == msg
