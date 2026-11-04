import pytest

from recordings import START_FRAMES, Recording, data_root, recordings

pytestmark = pytest.mark.skipif(not data_root().exists(), reason="DIVETWIN_DATA absent (public clone)")

RECS = recordings()


def test_five_recordings_resolve():
    assert len(RECS) == 5
    for r in RECS.values():
        assert r.exists(), r.dir


@pytest.mark.parametrize("cond", list(RECS))
def test_matched_frames_exist(cond):
    r = RECS[cond]
    assert len(r.matched_frames) >= 20
    assert all(0 <= f < r.n_frames for f in r.matched_frames)
    assert all(v > 0 for v in r.matched.values())


@pytest.mark.skipif(not START_FRAMES.exists(), reason="start_frames.json is written by task 1.2")
@pytest.mark.parametrize("cond", list(RECS))
def test_start_frame_is_hand_free_and_on_disk(cond):
    r = RECS[cond]
    info = r.start_info
    assert info["kind"] in ("empty", "quiet")
    assert r.left_path(r.start_frame).exists() and r.right_path(r.start_frame).exists()


@pytest.mark.parametrize("cond", list(RECS))
def test_calibration_loads(cond):
    c = RECS[cond].calibration
    assert c.fx == pytest.approx(1433.35, abs=0.01)
    assert c.baseline_mm == pytest.approx(62.97, abs=0.01)
    assert (c.width, c.height) == (2208, 1242)


# matched-frame counts per recording folder: the five current D1 recordings, then three substitutes that
# are not in RECORDING_NAMES yet (a Recording is just condition + folder name + data root)
MATCHED_COUNTS = {
    "Air_texBtl_recording_07052025_231523": 129,
    "Freshwater_texBtl_recording_08052025_015831": 81,
    "Freshwater-basicEnhance_texBtl_recording_09052025_154902": 110,
    "Saltwater_texBtl_recording_08052025_181147": 65,
    "Saltwater-pellets_texBtl_recording_08052025_190809": 46,
    "Freshwater-basicEnhance_smtBtl_recording_09052025_153536": 180,
    "Saltwater_medBtl_recording_08052025_182447": 133,
    "Saltwater-pellets_smtBtl-fill_recording_08052025_183311": 24,
}


@pytest.mark.parametrize("name, count", list(MATCHED_COUNTS.items()))
def test_matched_frame_count_per_recording(name, count):
    rec = Recording(name.split("_")[0], name, data_root())
    if not rec.dir.exists():
        pytest.skip(f"{name} not on disk")
    assert len(rec.matched_frames) == count


def test_current_recordings_are_among_the_pinned_counts():
    assert {r.name for r in RECS.values()} <= set(MATCHED_COUNTS)
