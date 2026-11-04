import json
from pathlib import Path

import pytest

from recordings import RECORDING_NAMES

SEEDS = Path(__file__).resolve().parent.parent / "seeds.json"
MAX_RESEEDS = 3    # call 39: later-frame prompts per object (each recorded with a reason); more needs Aaron


def _check_prompt(name, p):
    assert isinstance(p["frame"], int) and p["frame"] >= 0, (name, p)
    assert p["obj"] in ("bottle", "hand"), (name, p)
    assert "box" in p or "points" in p, (name, p)
    if "box" in p:
        x0, y0, x1, y1 = p["box"]
        assert 0 <= x0 < x1 <= 2208 and 0 <= y0 < y1 <= 1242, (name, p)
        assert (x1 - x0) * (y1 - y0) >= 400, (name, p)
    if "points" in p:
        assert len(p["points"]) == len(p["labels"]) >= 1, (name, p)
        assert all(v in (0, 1) for v in p["labels"]), (name, p)
        for x, y in p["points"]:
            assert 0 <= x < 2208 and 0 <= y < 1242, (name, p)


@pytest.mark.skipif(not SEEDS.exists(), reason="seeds.json is written by hand in task R1")
def test_seeds_cover_every_recording_with_a_bottle_and_a_hand():
    seeds = json.loads(SEEDS.read_text())
    assert set(seeds) == set(RECORDING_NAMES.values())
    for name, prompts in seeds.items():
        assert {p["obj"] for p in prompts} >= {"bottle", "hand"}, name
        for p in prompts:
            _check_prompt(name, p)


@pytest.mark.skipif(not SEEDS.exists(), reason="seeds.json is written by hand in task R1")
def test_every_object_starts_with_a_box_or_positive_point_and_every_reseed_says_why():
    for name, prompts in json.loads(SEEDS.read_text()).items():
        for obj in ("bottle", "hand"):
            mine = sorted((p for p in prompts if p["obj"] == obj), key=lambda p: p["frame"])
            first = mine[0]
            assert "box" in first or 1 in first.get("labels", []), (name, obj, "no conditioning prompt first")
            later = {p["frame"] for p in mine[1:]}
            assert len(later) <= MAX_RESEEDS, (name, obj, sorted(later))
            for p in mine[1:]:
                assert p.get("reason"), (name, obj, p["frame"], "a later prompt needs a one-line reason")
