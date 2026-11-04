import json

import cv2
import pytest

import cli
import clips
from clips import ClipSpec
from recordings import RECORDING_NAMES
from synth_video import write_mp4
from test_probes import H, W, low_contrast, texture, zoom_clip


@pytest.fixture
def runs(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path))
    monkeypatch.setitem(clips.GRID, "gen45", (W, H))
    monkeypatch.setitem(clips.GRID, "wan22", (W, H))
    return tmp_path


def test_probe_sheet_command_writes_the_json_and_the_sheet_and_prints_the_counts(runs, capsys):
    cond = list(RECORDING_NAMES)[0]
    for p, total in (("D", 1.25), ("B", 1.0), ("N", 1.0)):
        write_mp4(clips.video_path(ClipSpec(cond, "gen45", p, 2, "probe")), zoom_clip(total, base=texture(3)))
    cli.main(["probe-sheet"])
    out = capsys.readouterr().out
    assert "prompt D: forward on 1 of 1 by SIFT" in out and "prompt B: moved on 0 of 1" in out and "read in reverse" in out and "forward direction" in out
    assert "a cross-check for the eye" in out
    assert (runs / "probes.json").exists() and (runs / "sheets" / "probes.jpg").exists()
    assert cv2.imread(str(runs / "sheets" / "probes.jpg")) is not None


def test_probe_sheet_with_no_probes_exits_with_the_next_step(runs):
    with pytest.raises(SystemExit) as e:
        cli.main(["probe-sheet"])
    assert "runway_calls.py probes" in str(e.value.code)


def test_clips_index_command_keeps_probes_out_and_reports_missing_depth(runs, capsys):
    write_mp4(clips.video_path(ClipSpec("air", "gen45", "D", 2, "probe")), zoom_clip(1.1, n=49))
    write_mp4(clips.video_path(ClipSpec("air", "wan22", "D", 5)), zoom_clip(1.1, n=121))
    cli.main(["clips-index"])
    out = capsys.readouterr().out
    assert "clips_index.json: 1 clips; probes_index.json: 1 probes" in out and "1 clips have no depth file yet" in out
    assert list(json.loads((runs / "clips_index.json").read_text())) == ["air__wan22__D__5s"]


def test_clip_sheet_command_writes_a_labelled_sheet_of_every_12th_frame(runs, capsys):
    spec = ClipSpec("air", "gen45", "B", 5, "hunt", 2)
    write_mp4(clips.video_path(spec), zoom_clip(1.1, n=121))
    cli.main(["clip-sheet", spec.id])
    assert f"{spec.id}: 121 frames" in capsys.readouterr().out
    img = cv2.imread(str(runs / "sheets" / f"{spec.id}.jpg"))
    assert img.shape[1] == 5 * 256 and img.shape[0] == 3 * 144          # frames 0, 12, ..., 120 and the last: 11 tiles, 5 per row
    with pytest.raises(SystemExit):
        cli.main(["clip-sheet", "air__gen45__D__5s"])                    # not generated: says so


def test_contact_sheet_always_ends_on_the_last_frame():
    import probes
    fr = zoom_clip(1.1, n=50)
    sheet = probes.contact_sheet(fr, every=12, cols=5, w=64)
    assert sheet.shape == (2 * 36, 5 * 64, 3)                            # frames 0, 12, 24, 36, 48 and 49


def test_probe_sheet_prints_the_unmeasured_counts_for_b_and_n_and_never_calls_them_held(runs, capsys):
    cond = list(RECORDING_NAMES)[0]
    write_mp4(clips.video_path(ClipSpec(cond, "gen45", "D", 2, "probe")), zoom_clip(1.25, base=texture(3)))
    for p in "BN":                                           # turbid: nothing to measure
        write_mp4(clips.video_path(ClipSpec(cond, "gen45", p, 2, "probe")), low_contrast(zoom_clip(1.25, base=texture(3)), 0.05, 2.0))
    cli.main(["probe-sheet"])
    out = capsys.readouterr().out
    for p in "BN":
        line = next(ln for ln in out.splitlines() if ln.startswith(f"prompt {p}:"))
        assert "moved on 0 of 1, 1 unmeasured" in line and "(1 unmeasured)" in line


def test_probe_sheet_with_only_invalid_probes_says_which_and_why(runs, capsys):
    cond = list(RECORDING_NAMES)[0]
    spec = ClipSpec(cond, "gen45", "D", 2, "probe")
    write_mp4(clips.video_path(spec), zoom_clip(1.1, n=20))            # 20 frames, not 49
    with pytest.raises(SystemExit) as e:
        cli.main(["probe-sheet"])
    out = capsys.readouterr().out
    assert spec.id in out and "frames" in out and "runway_calls.py probes" in str(e.value.code)


def test_clips_index_checks_the_probes_it_lists(runs, capsys):
    write_mp4(clips.video_path(ClipSpec("air", "gen45", "D", 2, "probe")), zoom_clip(1.1, n=20))     # invalid
    cli.main(["clips-index"])
    assert "probes_index.json: 0 probes" in capsys.readouterr().out
    assert json.loads((runs / "probes_index.json").read_text()) == {}
