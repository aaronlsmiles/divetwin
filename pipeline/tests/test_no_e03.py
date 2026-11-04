"""Gate 0 (3 Nov): the earlier disparity and mask folders are never read by this pipeline."""
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent.parent
NEEDLE = "e03" + "_"  # split so this file never contains the substring itself


def test_no_pipeline_file_mentions_e03():
    offenders = []
    for p in PIPELINE.rglob("*.py"):
        if ".venv" in p.parts or p.resolve() == Path(__file__).resolve():
            continue
        if NEEDLE in p.read_text():
            offenders.append(str(p.relative_to(PIPELINE)))
    assert not offenders, offenders
