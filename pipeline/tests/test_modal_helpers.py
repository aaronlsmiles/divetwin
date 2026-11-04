import json
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

import modal_common
from modal_common import Meter, jpg, npy_load, png

PIPELINE = Path(__file__).resolve().parent.parent


def test_png_roundtrip_is_lossless():
    img = np.random.default_rng(0).integers(0, 255, (31, 47, 3), dtype=np.uint8)
    assert np.array_equal(cv2.imdecode(np.frombuffer(png(img), np.uint8), cv2.IMREAD_COLOR), img)
    assert len(jpg(img)) > 0


def test_npy_load():
    import io
    buf = io.BytesIO()
    np.save(buf, np.arange(6, dtype=np.float16).reshape(2, 3))
    assert npy_load(buf.getvalue()).shape == (2, 3)


def test_meter_logs_an_upper_bound(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path))
    m = Meter("L40S", 1.0)
    assert not m.over() and 0 < m.usd() < 0.05  # the 60 s scaledown alone is about $0.03
    m.calls = 1
    line = m.log("test", "app", 3)
    text = (tmp_path / "modal_spend.jsonl").read_text()
    assert json.loads(text)["usd_upper"] == line["usd_upper"]
    assert line["status"] == "ok" and line["n"] == 3
    json.loads(text, parse_constant=lambda c: pytest.fail(f"non-strict constant {c}"))


def test_meter_writes_null_for_a_non_finite_field(tmp_path, monkeypatch):
    """M3: a NaN field must not stop the spend line being written (it used to raise)."""
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path))
    m = Meter("L40S", 1.0)
    m.gpu_s = float("nan")
    line = m.log("test", "app", 1)
    assert line["gpu_s_in_calls"] is None
    rows = [json.loads(t, parse_constant=lambda c: pytest.fail(c)) for t in (tmp_path / "modal_spend.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["gpu_s_in_calls"] is None and rows[0]["n"] == 1


def test_meter_bills_gpu_cpu_and_memory_and_keeps_the_components(tmp_path, monkeypatch):
    """I4: usd_upper covers GPU + CPU + memory at Modal's rates; the line carries each component."""
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path))
    assert modal_common.USD_PER_CPU_CORE_S == 0.0000131 and modal_common.USD_PER_GIB_S == 0.00000222
    per_s = 1.95 / 3600 + 4 * 0.0000131 + 16 * 0.00000222
    m = Meter("L40S", 5.0, cpu=4, mem_gib=16)
    assert m.rate_s == pytest.approx(per_s)
    assert m.run_usd() == pytest.approx(modal_common.SCALEDOWN_S * per_s, rel=1e-3)
    m.calls = 1
    line = m.log("t", "app", 2)
    assert line["rate_gpu_usd_h"] == 1.95 and line["rate_cpu_usd_core_s"] == 0.0000131
    assert line["rate_mem_usd_gib_s"] == 0.00000222 and line["cpu"] == 4 and line["mem_gib"] == 16
    assert line["usd_upper"] == pytest.approx(line["wall_s"] * per_s, abs=2e-3)


def test_estimate_uses_the_same_rates():
    per_s = 1.95 / 3600 + 4 * 0.0000131 + 16 * 0.00000222
    assert modal_common.estimate(10, 1.2, 90, "L40S", cpu=4, mem_gib=16) == pytest.approx((90 + 60 + 12) * per_s)


def _spend(tmp_path, *rows):
    (tmp_path / "modal_spend.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_meter_starts_from_the_logged_spend_of_the_same_task(tmp_path, monkeypatch):
    """I2: the cap is cumulative across re-runs of one task."""
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path))
    _spend(tmp_path, {"task": "1.3a", "usd_upper": 0.5}, {"task": "1.3a", "usd_upper": 0.7},
           {"task": "1.5-floor", "usd_upper": 1.0}, {"task": "1.3a", "usd_upper": None})
    with (tmp_path / "modal_spend.jsonl").open("a") as fh:
        fh.write("not json at all\n")
    m = Meter("L40S", 1.5, task="1.3a")
    assert m.baseline == pytest.approx(1.2)
    assert m.usd() == pytest.approx(1.2 + m.run_usd()) and m.usd() > 1.2
    assert not m.over()
    assert Meter("L40S", 1.2, task="1.3a").over()          # baseline plus scaledown passes a $1.20 cap
    assert Meter("L40S", 1.5, task="other").baseline == 0.0
    assert modal_common.phase_total_usd() == pytest.approx(2.2)


def test_phase_one_total_is_enforced(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path))
    assert modal_common.PHASE1_CAP_USD == 5.00
    _spend(tmp_path, {"task": "a", "usd_upper": 2.0}, {"task": "b", "usd_upper": 2.9})
    modal_common.check_phase_budget(0.09)                     # 4.99 total: fine
    with pytest.raises(SystemExit) as e:
        modal_common.check_phase_budget(0.2)
    assert e.value.code not in (0, None) and "Phase 1" in str(e.value.code) and "$5.00" in str(e.value.code)


def test_meter_remote_refuses_a_call_that_would_pass_the_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path))
    m = Meter("L40S", 0.10, cpu=4, mem_gib=16)               # about $0.038 spent by the scaledown term
    seen = []
    assert m.remote(lambda x: seen.append(x) or x, 7, est_s=60) == 7 and m.calls == 1   # +$0.038: fits
    with pytest.raises(modal_common.CapReached):
        m.remote(lambda x: seen.append(x), 8, est_s=600)      # +$0.38: does not
    assert seen == [7] and m.calls == 1


def test_section_logs_on_every_exit(tmp_path, monkeypatch):
    """I1: ok / cap / error / interrupted each leave one spend line with the true count."""
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path))

    def rows():
        return [json.loads(t) for t in (tmp_path / "modal_spend.jsonl").read_text().splitlines()]

    with Meter("L40S", 1.0, cpu=1, mem_gib=1).section("t", "app", n_planned=9) as m:
        m.calls, m.n_done = 1, 4
    assert rows()[-1]["status"] == "ok" and rows()[-1]["n"] == 4 and rows()[-1]["n_planned"] == 9

    with Meter("L40S", 1.0).section("t", "app") as m:         # a capped loop sets the status itself
        m.calls, m.n_done, m.status = 1, 2, "cap"
    assert rows()[-1]["status"] == "cap" and rows()[-1]["n"] == 2

    with Meter("L40S", 0.0).section("t", "app") as m:         # CapReached from the guard: logged, swallowed
        m.remote(lambda: None, est_s=1)
    assert rows()[-1]["status"] == "cap" and rows()[-1]["usd_upper"] == 0.0 and rows()[-1]["n"] == 0

    with pytest.raises(RuntimeError):
        with Meter("L40S", 1.0).section("t", "app") as m:
            m.calls, m.n_done = 1, 3
            raise RuntimeError("boom")
    assert rows()[-1]["status"] == "error" and rows()[-1]["n"] == 3 and rows()[-1]["usd_upper"] > 0

    with pytest.raises(SystemExit):
        with Meter("L40S", 1.0).section("t", "app") as m:
            m.calls = 1
            raise SystemExit("refused")
    assert rows()[-1]["status"] == "error"

    with pytest.raises(KeyboardInterrupt):
        with Meter("L40S", 1.0).section("t", "app") as m:
            m.calls, m.n_done = 1, 1
            raise KeyboardInterrupt
    assert rows()[-1]["status"] == "interrupted" and len(rows()) == 6


def test_estimate_counts_load_and_scaledown():
    assert modal_common.estimate(0, 1.0, 0, "L40S") == modal_common.SCALEDOWN_S / 3600 * 1.95


def test_stereo_frame_list():
    from modal_stereo import frames_needed

    class Rec:
        matched_frames = [14, 16, 300]
        start_info = {"start": 396, "tail": [386, 396]}
    assert frames_needed(Rec()) == [14, 16, 300] + list(range(386, 397))


def test_modal_apps_import_without_running():
    import modal_depth
    import modal_stereo
    assert modal_stereo.app.name == "divetwin-stereo" and modal_depth.app.name == "divetwin-depth"


def test_pins_follow_the_plan_and_models_md():
    import modal_depth
    import modal_stereo
    assert modal_stereo.SA_COMMIT == "c4aa114b8e4dbba97c41663efb80df95875eeb95"
    assert modal_stereo.DAV2_REV == "cbbb86a30ce19b5684b7a05155dc7e6cbc7685b9"
    assert modal_depth.DA3_REV == "f465978e618db8cc79c83b8bbf24964857db1875"
    assert modal_depth.SAM2_REV == "665f8e2ad61cf5f53d65644ff27c8ee525124610"
    assert modal_depth.CAPS == {"smoke": 0.25, "masks": 1.50, "floor": 0.75, "selftest": 0.50}
    assert modal_stereo.CAP_USD == 2.00 and modal_stereo.CAP_DYTEST_USD <= 0.25
    toml = (PIPELINE / "pyproject.toml").read_text()
    assert "modal==1.6.3" in toml
    src = (PIPELINE / "modal_stereo.py").read_text()
    assert "whl/cu121" in src and "torch==2.4.0" in src  # CUDA 12.1 wheels, as the authors' requirements pin


# ---- the vertical-offset test (R2 step 2b) -------------------------------------------------------------

def _blobs(h, w, seed):
    rng = np.random.default_rng(seed)
    x = cv2.GaussianBlur(rng.random((h, w)).astype(np.float32), (0, 0), 2.0)
    x = (x - x.min()) / (x.max() - x.min())
    return (np.dstack([x, np.roll(x, 5, 0), np.roll(x, 9, 1)]) * 255).astype(np.uint8)


def test_shift_vertical_is_a_pure_downward_translation_with_replicated_border():
    from modal_stereo import shift_vertical
    img = np.zeros((40, 30), np.uint8)
    img[:, :] = np.arange(40, dtype=np.uint8)[:, None] * 5       # a vertical ramp
    out = shift_vertical(img, 2.0)
    assert np.array_equal(out[2:], img[:-2])                      # content moved down by exactly 2 rows
    assert np.array_equal(out[0], img[0]) and np.array_equal(out[1], img[0])  # border replicated
    half = shift_vertical(img.astype(np.float32), 0.5)
    assert np.allclose(half[10], (img[9].astype(np.float32) + img[10]) / 2)  # INTER_LINEAR
    assert np.array_equal(shift_vertical(img, 0.0), img) and np.array_equal(shift_vertical(img, float("nan")), img)


class _PairRec:
    """A recording whose right view has every feature 3 px higher (smaller y) and 8 px further right in the left view than in the right."""

    def __init__(self, tmp_path):
        self.name = "fake"
        base = _blobs(420, 580, 1)
        self.left = base[10:410, 20:560]
        self.right = base[13:413, 28:568]                        # y_left - y_right = +3, x_left - x_right = +8
        cv2.imwrite(str(tmp_path / "l.png"), self.left)
        cv2.imwrite(str(tmp_path / "r.png"), self.right)
        self.p = tmp_path

    def left_path(self, f):
        return self.p / "l.png"

    def right_path(self, f):
        return self.p / "r.png"


def test_prepare_pair_shifts_the_right_view_by_its_measured_dy(tmp_path):
    from modal_stereo import ISCALE, prepare_pair
    from units import epipolar_dy
    rec = _PairRec(tmp_path)
    L0, R0, dy0, used0 = prepare_pair(rec, 0, shift_dy=False)
    L1, R1, dy1, used1 = prepare_pair(rec, 0, shift_dy=True)
    assert L0.shape == (200, 270, 3) and np.array_equal(L0, L1)  # half resolution, left untouched
    assert dy0 == pytest.approx(3.0, abs=0.7) and dy1 == dy0     # recorded the same way in both runs
    assert used0 == 0.0 and used1 == dy0
    assert not np.array_equal(R0, R1)
    before = epipolar_dy(L0[..., 1], R0[..., 1])["median_dy"]
    after = epipolar_dy(L1[..., 1], R1[..., 1])["median_dy"]
    assert before == pytest.approx(3.0 / ISCALE, abs=0.4) and abs(after) < 0.4


def test_shift_is_applied_before_the_half_resolution_resize(tmp_path, monkeypatch):
    """The order matters: shifting after the resize would interpolate twice and shift by half a pixel's grid."""
    import modal_stereo
    rec = _PairRec(tmp_path)
    order = []
    orig_shift, orig_resize = modal_stereo.shift_vertical, cv2.resize
    monkeypatch.setattr(modal_stereo, "shift_vertical", lambda im, dy: (order.append(("shift", im.shape[:2])), orig_shift(im, dy))[1])
    monkeypatch.setattr(modal_stereo.cv2, "resize", lambda im, *a, **k: (order.append(("resize", im.shape[:2])), orig_resize(im, *a, **k))[1])
    modal_stereo.prepare_pair(rec, 0, shift_dy=True)
    shifts = [o for o in order if o[0] == "shift"]
    assert shifts and shifts[0][1] == (400, 540)                  # the shift saw the full-resolution right view
    first_shift = order.index(shifts[0])
    assert any(o == ("resize", (400, 540)) for o in order[first_shift:])  # and a resize followed it


def test_job_lists_skip_finished_pairs(tmp_path, monkeypatch):
    import modal_stereo
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path))

    class Rec:
        name = "r"
        condition = "c"
        matched_frames = [5, 7, 9]
        start_info = None
    done = tmp_path / "disp" / "r"
    done.mkdir(parents=True)
    (done / "000007.npz").write_bytes(b"x")
    jobs = modal_stereo.plan_jobs({"c": Rec()}, smoke=False)
    assert [f for _, f, _ in jobs] == [5, 9]
    assert [f for _, f, _ in modal_stereo.plan_jobs({"c": Rec()}, smoke=True)] == [5]  # first 2, minus the done one: 5 only


def test_dytest_pair_spec():
    import modal_stereo

    class Rec:
        def __init__(self, n):
            self.name, self.condition, self.matched_frames = n, n, [3, 4, 5]
    recs = {"air": Rec("air"), "fw": Rec("fw")}
    assert modal_stereo.parse_pairs("air:4,fw:5", recs) == [(recs["air"], 4), (recs["fw"], 5)]
    with pytest.raises(SystemExit):
        modal_stereo.parse_pairs("air:99", recs)  # not a matched frame of that recording


# ---- the stereo run with a fake remote: the spend line, the caps, the guards ---------------------------

import io  # noqa: E402


def _npy(a):
    buf = io.BytesIO()
    np.save(buf, a)
    return buf.getvalue()


class _Remote:
    def __init__(self, fn):
        self.fn, self.n = fn, 0

    def remote(self, *a, **k):
        self.n += 1
        return self.fn(*a, **k)

    def spawn(self, *a, **k):
        """The fetch is spawned and read with a deadline: the call runs here, `.get` hands back its result."""
        result = self.remote(*a, **k)
        return type("Call", (), {"get": lambda self, timeout=None: result, "cancel": lambda self: None})()


class _FakeModal:
    """Stands in for the StereoAnywhere class and the CPU weights function; records the order of events."""

    def __init__(self, events, fail_on_batch=None, clock=None, batch_s=0.0, info_s=0.0):
        self.events, self.fail_on_batch, self.clock, self.batch_s, self.info_s = events, fail_on_batch, clock, batch_s, info_s
        self.batches = 0
        self.fetch = _Remote(self._fetch)
        self.info = _Remote(self._info)
        self.disparity = _Remote(self._disparity)

    def __call__(self):
        return self

    def _tick(self, s):
        if self.clock is not None:
            self.clock[0] += s

    def _fetch(self):
        self.events.append("remote:fetch")
        return {"x": "00"}

    def _info(self):
        self.events.append("remote:info")
        self._tick(self.info_s)
        return {"sha256": {"x": "00"}, "commit": "c", "args": {}}

    def _disparity(self, pairs):
        self.events.append("remote:disparity")
        self.batches += 1
        if self.fail_on_batch == self.batches:
            raise RuntimeError("the GPU call failed")
        self._tick(self.batch_s)
        return [_npy(np.full((621, 1104), 3.0, np.float16)) for _ in pairs], 1.0


class _StereoRec(_PairRec):
    def __init__(self, tmp_path, matched, start_info=None, name="fake", condition="air"):
        super().__init__(tmp_path)
        self.name, self.condition, self.matched_frames, self.start_info = name, condition, matched, start_info


_OK_INFO = {"start": None, "tail": None, "gate_s": None}      # a start_frames.json entry with nothing extra to run


def _stereo_env(tmp_path, monkeypatch, matched=(1, 2, 3, 4, 5, 6), batch=2, start_info=_OK_INFO, **fake_kw):
    import modal_stereo
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path / "runs"))
    events = []
    fake = _FakeModal(events, **fake_kw)
    monkeypatch.setattr(modal_stereo, "StereoAnywhere", fake)
    monkeypatch.setattr(modal_stereo, "fetch_weights", fake.fetch)
    monkeypatch.setattr(modal_stereo, "BATCH", batch)
    rec = _StereoRec(tmp_path, list(matched), start_info)
    return modal_stereo, {"air": rec}, fake, events


def _spend_rows(tmp_path):
    p = tmp_path / "runs" / "modal_spend.jsonl"
    return [json.loads(t) for t in p.read_text().splitlines()] if p.exists() else []


def test_stereo_run_writes_the_spend_line_when_a_remote_call_raises_mid_loop(tmp_path, monkeypatch):
    """I1 + M2: two batches of two done, the third raises: one line, status error, n = 4 (not the 6 planned)."""
    ms, recs, fake, _ = _stereo_env(tmp_path, monkeypatch, fail_on_batch=3)
    with pytest.raises(RuntimeError, match="GPU call failed"):
        ms._run_main(recs, smoke=False, dry_run=False)
    (row,) = _spend_rows(tmp_path)
    assert row["status"] == "error" and row["n"] == 4 and row["n_planned"] == 6 and row["task"] == "1.3a"
    assert row["cpu"] == ms.CPU and row["mem_gib"] == ms.MEM_GIB and row["usd_upper"] > 0
    assert len(list((tmp_path / "runs" / "disp" / "fake").glob("*.npz"))) == 4   # finished batches were kept


def test_stereo_run_ok_logs_the_count_done(tmp_path, monkeypatch):
    ms, recs, fake, _ = _stereo_env(tmp_path, monkeypatch)
    ms._run_main(recs, smoke=False, dry_run=False)
    (row,) = _spend_rows(tmp_path)
    assert row["status"] == "ok" and row["n"] == 6 and fake.disparity.n == 3 and fake.fetch.n == 1


def test_stereo_cap_stops_the_loop_before_a_call_that_would_pass_it(tmp_path, monkeypatch):
    """I3: the guard refuses the next batch; the line says cap with the count done; the exit is non-zero."""
    import modal_common
    clock = [1000.0]
    monkeypatch.setattr(modal_common.Meter, "_now", staticmethod(lambda: clock[0]))
    ms, recs, fake, _ = _stereo_env(tmp_path, monkeypatch, clock=clock, batch_s=100.0, info_s=90.0)
    monkeypatch.setattr(ms, "CAP_USD", 0.20)
    with pytest.raises(SystemExit) as e:
        ms._run_main(recs, smoke=False, dry_run=False)
    assert "cap" in str(e.value.code) and "cumulative" in str(e.value.code)
    (row,) = _spend_rows(tmp_path)
    assert row["status"] == "cap" and 0 < row["n"] < 6 and row["n"] % 2 == 0 and row["usd_upper"] <= 0.25


def test_stereo_cap_is_cumulative_across_reruns(tmp_path, monkeypatch):
    """I2: earlier spend on the task counts; the run refuses before any remote call."""
    ms, recs, fake, events = _stereo_env(tmp_path, monkeypatch)
    (tmp_path / "runs").mkdir(parents=True)
    _spend(tmp_path / "runs", {"task": "1.3a", "usd_upper": 1.99})
    with pytest.raises(SystemExit) as e:
        ms._run_main(recs, smoke=False, dry_run=False)
    assert "cumulative" in str(e.value.code) and events == []


def test_stereo_run_refuses_to_start_past_the_phase_total(tmp_path, monkeypatch):
    ms, recs, fake, events = _stereo_env(tmp_path, monkeypatch)
    (tmp_path / "runs").mkdir(parents=True)
    _spend(tmp_path / "runs", {"task": "other", "usd_upper": 4.99})
    with pytest.raises(SystemExit) as e:
        ms._run_main(recs, smoke=False, dry_run=False)
    assert "Phase 1" in str(e.value.code) and events == []


def test_stereo_prepares_every_pair_before_the_first_remote_call(tmp_path, monkeypatch):
    """M1: SIFT dy and the PNG encodes all happen first."""
    ms, recs, fake, events = _stereo_env(tmp_path, monkeypatch)
    orig = ms.prepare_pair
    monkeypatch.setattr(ms, "prepare_pair", lambda *a, **k: (events.append("prepare"), orig(*a, **k))[1])
    ms._run_main(recs, smoke=False, dry_run=False)
    first_remote = next(i for i, e in enumerate(events) if e.startswith("remote"))
    assert events[:first_remote] == ["prepare"] * 6 and "prepare" not in events[first_remote:]


def test_dytest_prepares_all_pairs_once_before_the_first_remote_call(tmp_path, monkeypatch):
    """M1: every pair's SIFT runs once (not once per mode) and before info.remote()."""
    import units
    ms, recs, fake, events = _stereo_env(tmp_path, monkeypatch, matched=(5, 6, 7))
    orig = units.epipolar_dy
    monkeypatch.setattr(units, "epipolar_dy", lambda *a, **k: (events.append("sift"), orig(*a, **k))[1])
    ms._run_dytest(recs, "air:5,air:6", dry_run=False)
    first_remote = next(i for i, e in enumerate(events) if e.startswith("remote"))
    assert events[:first_remote] == ["sift", "sift"] and "sift" not in events[first_remote:]
    (row,) = _spend_rows(tmp_path)
    assert row["task"] == "2b-dytest" and row["n"] == 4 and row["status"] == "ok"
    assert (tmp_path / "runs" / "disp_dytest" / "pairs.json").exists()


def test_dytest_adds_to_the_pair_manifest_instead_of_replacing_it(tmp_path, monkeypatch):
    """A second run (more frames per recording) keeps the first run's pairs; a repeated pair is not listed twice."""
    ms, recs, fake, _ = _stereo_env(tmp_path, monkeypatch, matched=(5, 6, 7))
    ms._run_dytest(recs, "air:5", dry_run=False)
    ms._run_dytest(recs, "air:6,air:7", dry_run=False)
    ms._run_dytest(recs, "air:6", dry_run=False)
    pairs = json.loads((tmp_path / "runs" / "disp_dytest" / "pairs.json").read_text())
    assert [p["frame"] for p in pairs] == [5, 6, 7]


def test_dytest_failure_still_logs(tmp_path, monkeypatch):
    ms, recs, fake, _ = _stereo_env(tmp_path, monkeypatch, matched=(5, 6, 7), fail_on_batch=1)
    with pytest.raises(RuntimeError):
        ms._run_dytest(recs, "air:5", dry_run=False)
    (row,) = _spend_rows(tmp_path)
    assert row["status"] == "error" and row["n"] == 0 and row["task"] == "2b-dytest"


def test_stereo_run_needs_start_frames_unless_smoke_or_dry(tmp_path, monkeypatch, capsys):
    """I6: a full run without start_frames.json would silently skip the tails."""
    ms, recs, fake, events = _stereo_env(tmp_path, monkeypatch, start_info=None)
    with pytest.raises(SystemExit) as e:
        ms._run_main(recs, smoke=False, dry_run=False)
    assert "start-frames" in str(e.value.code) and events == []
    ms._run_main(recs, smoke=False, dry_run=True)                 # a dry run only says so
    assert "start-frames" in capsys.readouterr().out
    ms._run_main(recs, smoke=True, dry_run=False)                 # smoke needs matched frames only
    assert fake.disparity.n == 1


def test_gate_s_failure_stops_the_stereo_plan(tmp_path, monkeypatch):
    ms, recs, fake, events = _stereo_env(tmp_path, monkeypatch, start_info={"start": 9, "tail": None, "gate_s": "no hand-free run"})
    with pytest.raises(SystemExit) as e:
        ms._run_main(recs, smoke=False, dry_run=False)
    assert "Gate S" in str(e.value.code) and "no hand-free run" in str(e.value.code) and events == []
    with pytest.raises(SystemExit):
        ms.frames_needed(recs["air"])
    ms._run_dytest(recs, "air:5", dry_run=True)                   # the dy-test only needs matched frames
    ms._run_main(recs, smoke=True, dry_run=False)                 # and so does the smoke


def test_recording_start_frame_refuses_after_a_gate_s_failure(tmp_path, monkeypatch):
    import recordings
    p = tmp_path / "start_frames.json"
    p.write_text(json.dumps({"n_ok": {"start": 5, "gate_s": None}, "n_bad": {"start": 5, "gate_s": "no tail"}}))
    monkeypatch.setattr(recordings, "START_FRAMES", p)
    ok = recordings.Recording("a", "n_ok", tmp_path)
    bad = recordings.Recording("b", "n_bad", tmp_path)
    assert ok.start_frame == 5
    with pytest.raises(RuntimeError, match="Gate S.*no tail"):
        bad.start_frame


def test_spend_line_when_the_smoke_assert_fails_and_before_sam2_when_over_cap(tmp_path, monkeypatch):
    """I1/M5 on the depth smoke: the asserts run after the line is owed; SAM 2 is not called once over the cap."""
    import modal_depth
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path / "runs"))
    ev = []

    class Da3:
        def __init__(self):
            self.inv_depth = _Remote(lambda imgs, w, h: (ev.append("da3"), (_npy(np.full((len(imgs), h, w), -1.0, np.float16)), 1.0))[1])

    class Sam:
        def __init__(self):
            self.track = _Remote(lambda *a: (ev.append("sam2"), ({}, 1.0))[1])
    fetch = _Remote(lambda *a, **k: ev.append("fetch"))
    monkeypatch.setattr(modal_depth, "Da3Mono", Da3)
    monkeypatch.setattr(modal_depth, "Sam2Video", Sam)
    monkeypatch.setattr(modal_depth, "fetch_weights", fetch)
    img = tmp_path / "f.png"
    cv2.imwrite(str(img), np.zeros((40, 60, 3), np.uint8))

    class Rec:
        name, n_frames = "fw", 12

        def left_path(self, k):
            return img
    monkeypatch.setattr("recordings.recordings", lambda: {"freshwater": Rec()})
    monkeypatch.setattr(modal_depth, "_seeds", lambda: {"fw": [{"frame": 5, "obj": "bottle", "box": [1, 2, 3, 4]}]})
    with pytest.raises(AssertionError):                           # inverse depth must be positive: the fake gives -1
        modal_depth.run_smoke()
    (row,) = _spend_rows(tmp_path)
    assert row["task"] == "smoke" and row["status"] == "error" and row["n"] == 1 and ev == ["fetch", "da3"]


def test_smoke_clamps_the_sam2_frames_and_checks_the_cap_first(tmp_path, monkeypatch):
    import modal_depth
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path / "runs"))
    sent = []

    class Da3:
        def __init__(self):
            self.inv_depth = _Remote(lambda imgs, w, h: (_npy(np.ones((len(imgs), h, w), np.float16)), 1.0))

    class Sam:
        def __init__(self):
            self.track = _Remote(lambda jp, pr: (sent.append(len(jp)), ({"bottle": _npy(np.packbits(np.ones((len(jp), 621, 1104), bool), axis=-1))}, 1.0))[1])
    monkeypatch.setattr(modal_depth, "Da3Mono", Da3)
    monkeypatch.setattr(modal_depth, "Sam2Video", Sam)
    monkeypatch.setattr(modal_depth, "fetch_weights", _Remote(lambda *a, **k: None))
    img = tmp_path / "f.png"
    cv2.imwrite(str(img), np.zeros((40, 60, 3), np.uint8))

    class Rec:
        name, n_frames = "fw", 12                                 # seed at 8: frames 8..17 run off the end

        def left_path(self, k):
            assert k < 12, k
            return img
    monkeypatch.setattr("recordings.recordings", lambda: {"freshwater": Rec()})
    monkeypatch.setattr(modal_depth, "_seeds", lambda: {"fw": [{"frame": 8, "obj": "bottle", "box": [1, 2, 3, 4]}]})
    modal_depth.run_smoke()
    assert sent == [4]                                            # clamped to frames 8..11
    # over the cap before SAM 2: a slow DA3 call uses the budget up, SAM 2 is never called, the line says cap
    import modal_common
    sent.clear()
    clock = [1000.0]
    monkeypatch.setattr(modal_common.Meter, "_now", staticmethod(lambda: clock[0]))
    slow = _Remote(lambda imgs, w, h: (clock.__setitem__(0, clock[0] + 250), (_npy(np.ones((len(imgs), h, w), np.float16)), 1.0))[1])
    monkeypatch.setattr(modal_depth, "Da3Mono", lambda: type("D", (), {"inv_depth": slow})())
    with pytest.raises(SystemExit):
        modal_depth.run_smoke()
    assert sent == [] and _spend_rows(tmp_path)[-1]["status"] == "cap" and _spend_rows(tmp_path)[-1]["n"] == 1


# ---- the depth entrypoints with a fake remote ---------------------------------------------------------

class _DepthRec:
    def __init__(self, tmp_path, name="fw", matched=range(30), n_frames=40):
        self.name, self.matched_frames, self.n_frames, self.condition = name, list(matched), n_frames, name
        self.p = tmp_path / f"{name}.png"
        cv2.imwrite(str(self.p), np.full((40, 60, 3), 90, np.uint8))

    def left_path(self, k):
        return self.p


def _depth_env(tmp_path, monkeypatch, fail_on_call=None, clock=None, call_s=0.0, recs=None):
    import modal_depth
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path / "runs"))
    calls = []

    def inv(imgs, w, h):
        calls.append(len(imgs))
        if fail_on_call == len(calls):
            raise RuntimeError("DA3 call failed")
        if clock is not None:
            clock[0] += call_s
        return _npy(np.ones((len(imgs), h, w), np.float16)), 1.0
    monkeypatch.setattr(modal_depth, "Da3Mono", lambda: type("D", (), {"inv_depth": _Remote(inv)})())
    monkeypatch.setattr(modal_depth, "fetch_weights", _Remote(lambda *a, **k: None))
    recs = recs or {"fw": _DepthRec(tmp_path)}
    monkeypatch.setattr("recordings.recordings", lambda: recs)
    return modal_depth, calls


def test_floor_logs_the_true_count_when_a_batch_raises(tmp_path, monkeypatch):
    md, calls = _depth_env(tmp_path, monkeypatch, fail_on_call=2)
    with pytest.raises(RuntimeError, match="DA3 call failed"):
        md.run_floor()
    (row,) = _spend_rows(tmp_path)
    assert row["task"] == "1.5-floor" and row["status"] == "error" and row["n"] == 24 and row["n_planned"] == 30
    assert not (tmp_path / "runs" / "da3" / "floor" / "fw.npz").exists()


def test_floor_ok_writes_and_logs(tmp_path, monkeypatch):
    md, calls = _depth_env(tmp_path, monkeypatch)
    md.run_floor()
    (row,) = _spend_rows(tmp_path)
    assert row["status"] == "ok" and row["n"] == 30 and calls == [24, 6]
    assert np.load(tmp_path / "runs" / "da3" / "floor" / "fw.npz")["inv"].shape == (30, 720, 1280)


def test_da3_batches_return_a_capped_flag_instead_of_raising(tmp_path, monkeypatch):
    """I1: the cap used to raise SystemExit, so floor and selftest logged nothing."""
    import modal_common
    clock = [1000.0]
    monkeypatch.setattr(modal_common.Meter, "_now", staticmethod(lambda: clock[0]))
    md, calls = _depth_env(tmp_path, monkeypatch, clock=clock, call_s=400.0)
    meter = Meter("L40S", 0.30, cpu=md.CPU, mem_gib=md.MEM_GIB)
    got, capped = md._da3_batches([b"x"] * 60, meter)
    assert capped is True and got is None and calls == [24] and meter.n_done == 24
    meter2 = Meter("L40S", 5.0, cpu=md.CPU, mem_gib=md.MEM_GIB)
    got, capped = md._da3_batches([b"x"] * 30, meter2)
    assert capped is False and got.shape == (30, 720, 1280)


def test_floor_cap_leaves_a_cap_line_and_a_non_zero_exit(tmp_path, monkeypatch):
    import modal_common
    clock = [1000.0]
    monkeypatch.setattr(modal_common.Meter, "_now", staticmethod(lambda: clock[0]))
    md, calls = _depth_env(tmp_path, monkeypatch, clock=clock, call_s=1200.0)
    with pytest.raises(SystemExit) as e:
        md.run_floor()
    assert "cap" in str(e.value.code)
    (row,) = _spend_rows(tmp_path)
    assert row["status"] == "cap" and row["n"] == 24 and row["usd_upper"] > 0.4


def test_selftest_logs_even_when_a_call_raises(tmp_path, monkeypatch):
    md, calls = _depth_env(tmp_path, monkeypatch, fail_on_call=1)
    d = tmp_path / "runs" / "selftest" / "fw"
    d.mkdir(parents=True)
    for i in range(49):
        (d / f"frame_{i:03d}.png").write_bytes(b"x")
    with pytest.raises(RuntimeError):
        md.run_selftest()
    (row,) = _spend_rows(tmp_path)
    assert row["task"] == "1.7-selftest" and row["status"] == "error" and row["n"] == 0


def test_masks_logs_the_frames_done_when_the_second_recording_fails(tmp_path, monkeypatch):
    import modal_depth
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path / "runs"))
    n = {"c": 0}

    def track(frames, prompts):
        n["c"] += 1
        if n["c"] == 2:
            raise RuntimeError("SAM 2 call failed")
        return {"bottle": _npy(np.packbits(np.ones((len(frames), 621, 1104), bool), axis=-1))}, 1.0
    monkeypatch.setattr(modal_depth, "Sam2Video", lambda: type("S", (), {"track": _Remote(track)})())
    monkeypatch.setattr(modal_depth, "fetch_weights", _Remote(lambda *a, **k: None))
    recs = {"a": _DepthRec(tmp_path, "a", n_frames=5), "b": _DepthRec(tmp_path, "b", n_frames=7)}
    monkeypatch.setattr("recordings.recordings", lambda: recs)
    monkeypatch.setattr(modal_depth, "_seeds", lambda: {k: [{"frame": 0, "obj": "bottle", "box": [1, 2, 3, 4]}] for k in recs})
    with pytest.raises(RuntimeError):
        modal_depth.run_masks()
    (row,) = _spend_rows(tmp_path)
    assert row["task"] == "1.2-masks" and row["status"] == "error" and row["n"] == 5 and row["n_planned"] == 12
    assert (tmp_path / "runs" / "masks" / "a.npz").exists() and not (tmp_path / "runs" / "masks" / "b.npz").exists()


# ---- what the Modal decorators and images say (read as source: nothing here touches Modal) ---------------

import ast  # noqa: E402


def _decorated(script):
    """name -> {keyword: ast node} for every @app.cls / @app.function."""
    tree = ast.parse((PIPELINE / script).read_text())
    out = {}
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            for d in node.decorator_list:
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ("cls", "function") \
                        and getattr(d.func.value, "id", "") == "app":
                    out[node.name] = ({k.arg: k.value for k in d.keywords}, d.func.attr)
    return out


@pytest.mark.parametrize("script,names", [("modal_stereo.py", {"StereoAnywhere", "fetch_weights"}),
                                          ("modal_depth.py", {"Da3Mono", "Sam2Video", "fetch_weights"})])
def test_every_modal_class_and_function_sets_cpu_memory_and_timeout(script, names):
    """I4: the Meter bills cpu and memory, so each must be explicit."""
    dec = _decorated(script)
    assert set(dec) == names, dec.keys()
    for name, (kw, kind) in dec.items():
        assert {"cpu", "memory", "timeout"} <= set(kw), (name, sorted(kw))
        if name == "fetch_weights":
            assert "gpu" not in kw                                 # CPU-only: a download failure never bills a GPU
        else:
            assert "gpu" in kw and "startup_timeout" in kw         # load time has its own, longer limit


def test_call_timeouts_follow_the_per_item_estimates():
    """I3: about 3x the expected call time, from the same per-item numbers the estimates use."""
    import modal_depth
    import modal_stereo
    assert modal_stereo.BATCH == 16 and modal_stereo.BATCH_TIMEOUT_S == 120
    assert modal_depth.DA3_BATCH == 24 and modal_depth.DA3_TIMEOUT_S == 120
    assert modal_depth.SAM2_TIMEOUT_S == 330 and modal_depth.SAM2_MAX_FRAMES >= 455
    for expected, n, per, over in [(modal_stereo.BATCH_TIMEOUT_S, 16, modal_stereo.S_PER_PAIR, modal_stereo.CALL_OVERHEAD_S),
                                   (modal_depth.SAM2_TIMEOUT_S, modal_depth.SAM2_MAX_FRAMES, modal_depth.SAM2_S_PER_FRAME,
                                    modal_depth.SAM2_OVERHEAD_S)]:
        assert 2.5 * (n * per + over) <= expected <= 3.5 * (n * per + over) + 30
    assert modal_stereo.STARTUP_S >= 3 * modal_stereo.LOAD_S - 30 and modal_depth.DA3_STARTUP_S >= 3 * modal_depth.DA3_LOAD_S - 30


def test_resources_are_explicit_and_shared_with_the_meter():
    import modal_depth
    import modal_stereo
    assert (modal_stereo.CPU, modal_stereo.MEM_GIB) == (4, 16)
    assert modal_depth.CPU == 4 and modal_depth.MEM_GIB >= 16     # SAM 2 offloads the video to host memory
    for script in ("modal_stereo.py", "modal_depth.py"):
        for name, (kw, _) in _decorated(script).items():
            assert isinstance(kw["memory"], (ast.BinOp, ast.Constant)) and "cpu" in kw


def test_image_packages_are_pinned_and_da3_installs_without_deps():
    """M4: no floating package in the image definitions; DA3's own install does not resolve its dependencies."""
    import re
    for script in ("modal_stereo.py", "modal_depth.py"):
        tree = ast.parse((PIPELINE / script).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "pip_install":
                for a in node.args:
                    if isinstance(a, ast.Constant) and isinstance(a.value, str):
                        v = a.value
                        assert "==" in v or "<" in v or "@ git+" in v, f"{script}: floating package {v!r}"
                        if "@ git+" in v:
                            assert re.search(r"@[0-9a-f]{40}", v)
    src = (PIPELINE / "modal_depth.py").read_text()
    assert re.search(r'depth-anything-3 @ git\+[^"]+"[^)]*extra_options="--no-deps"', src)
    for pkg in ("einops", "omegaconf", "addict", "imageio", "moviepy", "trimesh", "plyfile", "pycolmap", "evo"):
        assert pkg in src, pkg                                    # what DA3's inference path imports at module level
    assert "e3nn" not in src and "gsplat" not in src and "open3d" not in src
    st = (PIPELINE / "modal_stereo.py").read_text()
    for pin in ("kornia==", "opt_einsum==", "matplotlib==", "huggingface_hub==", "Pillow=="):
        assert pin in st, pin


def test_the_false_cap_comment_is_gone_and_the_wording_says_cumulative():
    st = (PIPELINE / "modal_stereo.py").read_text()
    assert "stops before projected spend" not in st and "a re-run resumes" not in st
    assert "cumulative" in st


def test_gpu_classes_do_not_download_weights():
    """I3: downloads live in the CPU function; the GPU classes only read the Volume."""
    for script in ("modal_stereo.py", "modal_depth.py"):
        tree = ast.parse((PIPELINE / script).read_text())
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                text = ast.get_source_segment((PIPELINE / script).read_text(), node)
                assert "gdown" not in text, node.name
                assert "local_files_only=True" in text or "hf_hub_download" not in text and "snapshot_download" not in text, node.name


# ---- dry runs touch neither Modal nor the GPU ----------------------------------------------------------

def _run_dry(script, *args, tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("MODAL")}
    env.update(HOME=str(tmp_path), DIVETWIN_RUNS=str(tmp_path / "runs"), MODAL_CONFIG_PATH=str(tmp_path / "none.toml"))
    return subprocess.run([sys.executable, "-I", str(PIPELINE / script), *args], capture_output=True, text=True,
                          env=env, cwd=tmp_path, timeout=300)


def _data_present():
    from recordings import recordings
    return all(r.exists() for r in recordings().values())


@pytest.mark.skipif(not _data_present(), reason="needs the dataset link")
@pytest.mark.parametrize("script,args,expect", [
    ("modal_stereo.py", ["--dry-run"], "pairs to run; estimate $"),
    ("modal_stereo.py", ["--dry-run", "--smoke"], "pairs to run; estimate $"),
    ("modal_stereo.py", ["--dry-run", "--dy-test"], "dy-test"),
    ("modal_depth.py", ["masks", "--dry-run"], "recordings,"),
    ("modal_depth.py", ["floor", "--dry-run"], "frames; estimate $"),
    ("modal_depth.py", ["selftest", "--dry-run"], "renders; estimate $"),
    ("modal_depth.py", ["smoke", "--dry-run"], "estimate $"),
])
def test_dry_runs_work_offline_and_write_nothing(tmp_path, script, args, expect):
    r = _run_dry(script, *args, tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr[-2000:]
    assert expect in r.stdout and "cap $" in r.stdout and "cumulative" in r.stdout and "Phase 1" in r.stdout
    assert not (tmp_path / "runs" / "modal_spend.jsonl").exists()


def test_paid_runs_are_refused_outside_modal_run(tmp_path):
    for script, args in [("modal_stereo.py", []), ("modal_depth.py", ["masks"])]:
        r = _run_dry(script, *args, tmp_path=tmp_path)
        assert r.returncode != 0 and "modal run" in (r.stdout + r.stderr)


def test_meter_cap_is_clamped_to_the_phase_one_headroom(tmp_path, monkeypatch):
    """Re-review of 1948f3d: the Phase 1 total binds while a run goes, not only before it starts."""
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path))
    _spend(tmp_path, {"task": "1.3a", "usd_upper": 0.50}, {"task": "other", "usd_upper": 4.00})
    m = modal_common.clamp_to_phase(Meter("L40S", 2.00, task="1.3a", cpu=4, mem_gib=16))
    assert m.baseline == pytest.approx(0.50)
    assert m.cap == pytest.approx(0.50 + 5.00 - 4.50)        # $0.50 of headroom left in Phase 1, not $1.50
    m2 = modal_common.clamp_to_phase(Meter("L40S", 0.75, task="1.3a", cpu=4, mem_gib=16))
    assert m2.cap == pytest.approx(0.75)                      # the task cap binds when it is lower


def test_stereo_smoke_has_its_own_small_cap():
    import modal_stereo as ms
    assert ms.CAP_SMOKE_USD == 0.25 and ms.CAP_SMOKE_USD < ms.CAP_USD


def test_gpu_classes_cap_cpu_at_the_billed_cores():
    """cpu=(request, limit): torch threads can't burst past what the meter bills."""
    for f in ("modal_stereo.py", "modal_depth.py"):
        src = open(f).read()
        lines = [l for l in src.splitlines() if l.startswith("@app.cls(")]
        assert lines, f
        for l in lines:
            assert "cpu=(CPU, CPU)" in l, (f, l[:80])


def _top_level_third_party(path: Path) -> set[str]:
    """Top-level imported modules of a script that are neither stdlib, local to the pipeline, nor modal itself."""
    import ast
    names = set()
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    local = {p.stem for p in PIPELINE.glob("*.py")}
    return {n for n in names if n not in sys.stdlib_module_names and n not in local and n not in ("modal", "__future__")}


# import name -> pip distribution name, for the few that differ
_PIP_NAME = {"cv2": "opencv-python-headless", "PIL": "Pillow"}


@pytest.mark.parametrize("script", ["modal_stereo.py", "modal_depth.py"])
def test_weights_image_installs_every_top_level_import(script):
    """Every container imports the whole script, so a module imported at its top must be pip-installed in
    the CPU-only weights image too (modal_stereo's fetch_weights crash-looped on `import cv2`)."""
    src = (PIPELINE / script).read_text()
    line = src[src.index("weights_image ="):].split("\n\n")[0]
    for mod in _top_level_third_party(PIPELINE / script):
        assert _PIP_NAME.get(mod, mod).lower() in line.lower(), (script, mod, line)


def test_the_weights_image_check_catches_a_missing_module():
    assert _top_level_third_party(PIPELINE / "modal_stereo.py") >= {"cv2", "numpy"}


class _FakeCall:
    def __init__(self, result=None, raises=None):
        self.result, self.raises, self.cancelled, self.timeout = result, raises, False, None

    def get(self, timeout=None):
        self.timeout = timeout
        if self.raises:
            raise self.raises
        return self.result

    def cancel(self):
        self.cancelled = True


class _FakeFn:
    def __init__(self, call):
        self.call, self.args = call, None

    def spawn(self, *args):
        self.args = args
        return self.call


def test_call_with_deadline_returns_the_result():
    call = _FakeCall(result={"ok": 1})
    fn = _FakeFn(call)
    assert modal_common.call_with_deadline(fn, 900, "a") == {"ok": 1}
    assert fn.args == ("a",) and call.timeout == 900 and not call.cancelled


def test_call_with_deadline_cancels_and_raises_when_it_hangs():
    import modal.exception
    for exc in (TimeoutError("x"), modal.exception.TimeoutError("x")):
        call = _FakeCall(raises=exc)
        with pytest.raises(modal_common.FetchDeadline):
            modal_common.call_with_deadline(_FakeFn(call), 5)
        assert call.cancelled


def test_a_hung_fetch_still_writes_a_spend_line(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path))
    m = Meter("L40S", 5.0, task="t")
    call = _FakeCall(raises=TimeoutError())
    with pytest.raises(modal_common.FetchDeadline):
        with m.section("t", "app", 2):
            m.remote(modal_common.call_with_deadline, _FakeFn(call), 5, est_s=1)
    line = json.loads((tmp_path / "modal_spend.jsonl").read_text())
    assert line["status"] == "error" and line["usd_upper"] > 0


def test_both_apps_fetch_through_the_deadline():
    assert "FETCH_DEADLINE_S = 900" in (PIPELINE / "modal_stereo.py").read_text()
    assert "FETCH_DEADLINE_S = 900" in (PIPELINE / "modal_depth.py").read_text()
    for f in ("modal_stereo.py", "modal_depth.py"):
        src = (PIPELINE / f).read_text()
        assert "fetch_weights.remote" not in src, f
        assert "call_with_deadline" in src, f
