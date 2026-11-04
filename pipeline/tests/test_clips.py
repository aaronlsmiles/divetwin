import json

import pytest

import clips
from clips import ClipSpec, check_mp4, parse_clip_id, rebuild_clips_index, rebuild_probes_index, seed_for
from prompts import PROMPTS
from recordings import RECORDING_NAMES
from synth_video import noise_frames, write_mp4


@pytest.fixture
def runs(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path))
    return tmp_path


def test_ids_round_trip_for_every_clip_the_plan_asks_for():
    specs = []
    for cond in RECORDING_NAMES:
        specs += [ClipSpec(cond, "gen45", p, 2, "probe") for p in "DBN"]
        specs += [ClipSpec(cond, e, p, 5) for e in clips.ENGINES for p in "DBN"]
        specs.append(ClipSpec(cond, "gen45", "D", 10))
    specs += [ClipSpec("air", "gen45", "B", 5, "hunt", t) for t in range(1, 11)]
    ids = [s.id for s in specs]
    assert len(ids) == len(set(ids)) == 5 * 3 + 5 * 6 + 5 + 10        # 15 probes, 30 five-second finals, 5 long, 10 hunt
    for s in specs:
        assert parse_clip_id(s.id) == s
    assert ClipSpec("freshwater-basicEnhance", "wan22", "N", 5).id == "freshwater-basicEnhance__wan22__N__5s"


def test_a_probe_id_says_probe_and_can_never_equal_a_final_id():
    assert ClipSpec("air", "gen45", "D", 2, "probe").id == "air__gen45__D__probe2s"
    finals = {ClipSpec(c, "gen45", p, 5).id for c in RECORDING_NAMES for p in "DBN"}
    assert not any("probe" in i for i in finals)


@pytest.mark.parametrize("args", [
    ("air", "gen45", "D", 3), ("air", "gen45", "B", 10), ("air", "wan22", "D", 10), ("nowhere", "gen45", "D", 5),
    ("air", "sora", "D", 5), ("air", "gen45", "X", 5)])
def test_impossible_specs_are_refused(args):
    with pytest.raises(ValueError):
        ClipSpec(*args)


def test_probe_and_hunt_rules():
    for kw in ({"seconds": 5, "kind": "probe"}, {"engine": "wan22", "seconds": 2, "kind": "probe"}):
        with pytest.raises(ValueError):
            ClipSpec(**{"condition": "air", "engine": "gen45", "prompt": "D", **kw})
    with pytest.raises(ValueError):
        ClipSpec("air", "gen45", "D", 5, "hunt", 1)          # the hunt is prompt B word for word
    with pytest.raises(ValueError):
        ClipSpec("air", "gen45", "B", 5, "hunt", 11)         # at most ten takes
    with pytest.raises(ValueError):
        ClipSpec("air", "gen45", "B", 5, "hunt")             # a take number is needed
    for bad in ("air__gen45__D__2s", "air__gen45__D__probe5s", "air__gen45__D__5s__h1", "air_gen45_D_5s", "x"):
        with pytest.raises(ValueError):
            parse_clip_id(bad)


def test_seeds_are_fixed_matched_for_b_and_n_and_distinct_otherwise():
    for cond in RECORDING_NAMES:
        for eng in clips.ENGINES:
            b, n, d = (seed_for(ClipSpec(cond, eng, p, 5)) for p in "BND")
            assert b == n != d
    assert seed_for(ClipSpec("air", "gen45", "B", 2, "probe")) == seed_for(ClipSpec("air", "gen45", "N", 2, "probe"))
    allseeds = {seed_for(ClipSpec("air", "gen45", "B", 5, "hunt", t)) for t in range(1, 11)}
    assert len(allseeds) == 10 and seed_for(ClipSpec("air", "gen45", "B", 5)) not in allseeds
    base = ClipSpec("air", "gen45", "D", 5)
    assert len({seed_for(base, r) for r in range(5)}) == 5                     # a retake gets its own seed
    per_cond = {seed_for(ClipSpec(c, "gen45", "D", 5)) for c in RECORDING_NAMES}
    assert len(per_cond) == 5
    assert all(0 <= s < 2**32 for s in allseeds | per_cond)


def test_seed_values_are_pinned_so_they_never_drift():
    """The hash scheme is part of the record: B and N share the 'BN' arm."""
    assert seed_for(ClipSpec("air", "gen45", "D", 5)) == 639075550
    assert seed_for(ClipSpec("air", "gen45", "B", 5)) == seed_for(ClipSpec("air", "gen45", "N", 5)) == 1106145126


def test_expected_frames_and_grids():
    assert clips.expected_frames(ClipSpec("air", "gen45", "D", 2, "probe")) == 49
    assert clips.expected_frames(ClipSpec("air", "gen45", "D", 5)) == 121
    assert clips.expected_frames(ClipSpec("air", "gen45", "D", 10)) == 241
    assert clips.expected_frames(ClipSpec("air", "wan22", "D", 5)) == 121
    assert clips.GRID == {"gen45": (1280, 720), "wan22": (1280, 704)}


def test_check_mp4_counts_frames_and_size(tmp_path):
    p = write_mp4(tmp_path / "a.mp4", noise_frames(7, 64, 48))
    r = check_mp4(p, 7, (64, 48))
    assert r["ok"] and r["frames"] == 7 and r["size"] == (64, 48) and r["fps"] == 24.0
    assert not check_mp4(p, 8, (64, 48))["ok"] and "7 frames, expected 8" in check_mp4(p, 8)["reason"]
    assert "64x48, expected 32x32" in check_mp4(p, 7, (32, 32))["reason"]
    assert check_mp4(tmp_path / "missing.mp4")["reason"] == "missing or empty"
    (tmp_path / "bad.mp4").write_bytes(b"not a video at all")
    assert not check_mp4(tmp_path / "bad.mp4")["ok"]


def _fake_clip(spec, n=None):
    p = clips.video_path(spec)
    write_mp4(p, noise_frames(n or clips.expected_frames(spec), 64, 48))   # right count, wrong size on purpose


def test_the_index_is_the_section_5_schema_and_never_holds_a_probe(runs, monkeypatch):
    monkeypatch.setitem(clips.GRID, "gen45", (64, 48))
    monkeypatch.setitem(clips.GRID, "wan22", (64, 48))
    probe = ClipSpec("air", "gen45", "D", 2, "probe")
    final = ClipSpec("air", "gen45", "D", 5)
    hunt = ClipSpec("air", "gen45", "B", 5, "hunt", 3)
    wan = ClipSpec("saltwater-pellets", "wan22", "N", 5)
    for s in (probe, final, hunt, wan):
        _fake_clip(s)
    out = rebuild_clips_index()
    idx = json.loads((runs / "clips_index.json").read_text())
    assert set(idx) == {final.id, hunt.id, wan.id} and probe.id not in idx
    e = idx[hunt.id]
    assert set(e) == {"condition", "engine", "prompt", "seconds", "take", "video", "depth"}
    assert (e["condition"], e["engine"], e["prompt"], e["seconds"], e["take"]) == ("air", "gen45", "B", 5, 3)
    assert idx[final.id]["take"] is None and idx[wan.id]["engine"] == "wan22"
    assert e["video"].endswith(f"gen45/{hunt.id}.mp4") and e["depth"].endswith(f"da3/clips/{hunt.id}.npz")
    pidx = rebuild_probes_index()["index"]
    assert list(pidx) == [probe.id] and pidx[probe.id]["seed"] == seed_for(probe)
    assert json.loads((runs / "probes_index.json").read_text()) == pidx and out["invalid"] == []


def test_an_invalid_or_foreign_file_stays_out_of_the_index(runs, monkeypatch):
    monkeypatch.setitem(clips.GRID, "gen45", (64, 48))
    good, short = ClipSpec("air", "gen45", "D", 5), ClipSpec("freshwater", "gen45", "D", 5)
    _fake_clip(good)
    _fake_clip(short, n=100)                                           # 100 frames, not 121
    (runs / "gen45" / "notes.mp4").write_bytes(b"x")                   # not a clip id: ignored
    (runs / "gen45" / "retired").mkdir()
    (runs / "gen45" / "retired" / f"{good.id}.mp4").write_bytes(b"x") # a subfolder is never scanned
    out = rebuild_clips_index()
    assert list(out["index"]) == [good.id]
    assert out["invalid"] == [(short.id, "100 frames, expected 121")]


def test_prompt_text_has_one_source():
    import inspect
    src = inspect.getsource(clips)
    for text in PROMPTS.values():
        assert text not in src
