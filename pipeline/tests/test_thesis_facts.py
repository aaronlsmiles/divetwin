"""Clearance 6.1: THESIS.md (whose words also go on studionephele.com) against the page's own clips.json.

Every figure the thesis states is re-derived here from runs/assets/clips.json, the file the page reads; the publication rules the card
carries (nothing from unpublished research, millimetres only as "never millimetres", the dataset's Zenodo citation, the
camera, the licences) are held too. The data checks skip without runs/assets (gitignored); the word checks always run.
"""
import json
import os
import re
from pathlib import Path

import pytest

from recordings import runs_dir

REPO = Path(__file__).resolve().parent.parent.parent
THESIS = (REPO / "THESIS.md").read_text()
CLIPS = runs_dir() / "assets" / "clips.json"
FPS_RUN = 12            # web/src/lib/series.ts D_RUN: half a second at 24 fps
THRESHOLD = 3.0

ZENODO = ("Smiles, A., Farkhatdinov, I., & Oh, C. (2025). UW-TransStereo: Underwater Stereo Vision Dataset for Transparent Object "
          "Detection & Ranging [Dataset]. Zenodo. RiTA 2025, King's College London. https://doi.org/10.5281/zenodo.16753748")


def f2(x: float) -> str:
    """Two places, rounding half away from zero on the double's exact value, as the page's toFixed(2) does."""
    from decimal import ROUND_HALF_UP, Decimal
    return str(Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def test_no_paper_under_review_content():
    # Venue names are not listed in this public repo: set DIVETWIN_EXTRA_BANNED to a "|"-joined regex to check them locally.
    extra = [os.environ["DIVETWIN_EXTRA_BANNED"]] if os.environ.get("DIVETWIN_EXTRA_BANNED") else []
    for rx in [r"contour", r"refract", r"n_eff", r"\bMAE\b", r"under review", r"\bmm\b",
               r"ranging error", r"scales raw stereo depth", *extra]:
        assert not re.search(rx, THESIS, re.I), rx
    assert re.findall(r"millimet\w*", THESIS, re.I) == ["millimetres"]
    assert "never millimetres" in THESIS


def test_dataset_camera_and_licences():
    assert ZENODO in THESIS
    assert "ZED Mini" in THESIS
    assert "CC BY 4.0" in THESIS and "CC BY-NC-SA 4.0" in THESIS
    assert "Stereo Anywhere" in THESIS and "Depth Anything V2" in THESIS
    assert "the generated clips (Runway Gen-4.5, Wan 2.2) are the engines' output and are not under either licence" in THESIS


@pytest.fixture(scope="module")
def doc():
    if not CLIPS.exists():
        pytest.skip("runs/assets/clips.json is not here (gitignored); the thesis figures need it")
    return json.loads(CLIPS.read_text())


def _unverifiable(c, f):
    return c["unverifiable_from"] is not None and f >= c["unverifiable_from"]


def _sustained(D):
    n = 0
    for k, d in enumerate(D):
        n = n + 1 if d is not None and d > THRESHOLD else 0
        if n == FPS_RUN:
            return k - FPS_RUN + 1
    return None


def _by(doc, cid):
    return next(c for c in doc["clips"] if c["clip"] == cid)


def test_the_counts(doc):
    clips = doc["clips"]
    dep = [c for c in clips if _sustained(c["D"]) is not None]
    spike = [c for c in clips if c not in dep and any(d is not None and d > THRESHOLD and not _unverifiable(c, f) for f, d in enumerate(c["D"]))]
    ran = [c for c in clips if c not in dep and c not in spike and c["unverifiable_from"] is not None]
    under = [c for c in clips if c not in dep + spike + ran]
    assert len(clips) == 35 and "made 35 clips under three prompts" in THESIS
    assert len({c["prompt"] for c in clips}) == 3 and len({c["condition"] for c in clips}) == 5
    assert len(dep) == 3 and "Three of the 35 clips leave the tank" in THESIS
    assert len(spike) == 2 and "Two more clips spike past 3 without holding it for half a second" in THESIS
    assert len(under) == 25 and "25 stay under 3 for their whole length" in THESIS
    reasons = sorted(c["unverifiable_reason"] for c in ran)
    assert reasons == ["path lost"] + ["travel cap"] * 4
    assert all(c["condition"] == "saltwater-pellets" for c in ran if c["unverifiable_reason"] == "travel cap")
    cap = doc["recordings"]["saltwater-pellets"]["trusted_travel_su"]
    assert f"in five the check runs out first: one path is lost, and four pellets clips pass the {cap:.0f} su range" in THESIS


def test_the_clearest_departure(doc):
    c = _by(doc, "freshwater-basicEnhance__gen45__N__5s")
    f = _sustained(c["D"])
    assert f == c["first_D3"]
    peak = max((d, k) for k, d in enumerate(c["D"]) if d is not None)
    vmin = min(v for v in c["verified"] if v is not None)
    assert (f"D passes 3 at frame {f} ({f / c['fps']:.1f} s), {c['path'][f][2]:.0f} su along its path, and peaks at "
            f"{f2(peak[0])} at frame {peak[1]}, while V stays at {f2(vmin)}") in THESIS


def test_the_two_salt_water_wan_departures(doc):
    frames = sorted(_sustained(_by(doc, f"saltwater__wan22__{p}__5s")["D"]) for p in "BN")
    assert f"Two Wan clips in salt water leave too, at frames {frames[0]} and {frames[1]}" in THESIS


def test_v_cannot_see_a_dream_leave(doc):
    """The two Gen-4.5 clips whose far wall opens into new space (3.5's reading: the hatch and corridor, the duct) both pass D 3."""
    vs = []
    for cid in ("freshwater-basicEnhance__gen45__N__5s", "saltwater__gen45__N__5s"):
        c = _by(doc, cid)
        assert max(d for d in c["D"] if d is not None) > THRESHOLD
        vs.append(min(v for v in c["verified"] if v is not None))
    assert {f2(v) for v in vs} == {"1.00"}
    assert "The two Gen-4.5 clips whose far wall plainly opens into new space keep V at 1.00 from the first frame to the last" in THESIS


def test_a_tracked_actor_still_costs_the_tank(doc):
    c = _by(doc, "saltwater__wan22__B__5s")
    assert any(c["moving_track"])
    peak = max((d, k) for k, d in enumerate(c["D"]) if d is not None)
    assert f"D still climbs to {f2(peak[0])} (frame {peak[1]}) on the tank behind them" in THESIS


def test_the_floor_on_real_footage(doc):
    med = [r["null_dream_D"]["median"] for r in doc["recordings"].values()]
    assert f"D sits between {f2(min(med))} and {f2(max(med))} (the median per recording)" in THESIS
