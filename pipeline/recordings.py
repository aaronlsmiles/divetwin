"""The five D1 recordings, resolved from the dataset on disk (never copied into the repo)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

# repo-root data/ is a gitignored link to the downloaded dataset; DIVETWIN_DATA overrides it
DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "data" / "export"


def data_root() -> Path:
    return Path(os.environ.get("DIVETWIN_DATA", DEFAULT_ROOT)).expanduser()


def runs_dir() -> Path:
    """Pipeline outputs (gitignored): repo-root runs/, or DIVETWIN_RUNS."""
    return Path(os.environ.get("DIVETWIN_RUNS", Path(__file__).resolve().parent.parent / "runs")).expanduser()


START_FRAMES = Path(__file__).resolve().parent / "start_frames.json"  # written by task 1.2 (cli.py start-frames)


# condition name -> recording folder
RECORDING_NAMES = {
    "air": "Air_texBtl_recording_07052025_231523",
    "freshwater": "Freshwater_texBtl_recording_08052025_015831",
    "freshwater-basicEnhance": "Freshwater-basicEnhance_smtBtl_recording_09052025_153536",
    "saltwater": "Saltwater_medBtl_recording_08052025_182447",
    "saltwater-pellets": "Saltwater-pellets_smtBtl-fill_recording_08052025_183311",
}


@dataclass(frozen=True)
class Calibration:
    fx: float
    cx: float
    cy: float
    baseline_mm: float
    width: int
    height: int


@dataclass(frozen=True)
class Recording:
    condition: str
    name: str
    root: Path

    @property
    def dir(self) -> Path:
        return self.root / self.name

    @property
    def left_dir(self) -> Path:
        return self.dir / "left"

    @property
    def right_dir(self) -> Path:
        return self.dir / "right"

    @property
    def frames_path(self) -> Path:
        return self.dir / "frames.parquet"

    @property
    def calibration_path(self) -> Path:
        return self.dir / "calibration.json"

    def exists(self) -> bool:
        return all(p.exists() for p in (self.left_dir, self.right_dir, self.frames_path, self.calibration_path))

    @cached_property
    def frames(self):
        return pq.read_table(self.frames_path).to_pydict()

    @property
    def n_frames(self) -> int:
        return len(self.frames["frame_idx"])

    @property
    def labelled_frames(self) -> list[int]:
        f = self.frames
        return [i for i, lab in zip(f["frame_idx"], f["is_labelled"]) if lab]

    @cached_property
    def matched(self) -> dict[int, float]:
        """Frames the published labels were matched to -> median Center_Distance of their label rows.
        Pause markers are skipped. Used for the stereo frame list and the private units cross-check only."""
        t = pq.read_table(self.root.parent / "tables" / "labels.parquet",
                          columns=["recording_id", "matched_frame_idx", "Center_Distance", "is_pause_marker"]).to_pydict()
        rid = self.name.replace("_recording_", "_detections_")
        acc: dict[int, list[float]] = {}
        for r, m, cd, pause in zip(t["recording_id"], t["matched_frame_idx"], t["Center_Distance"], t["is_pause_marker"]):
            if r != rid or pause or m is None or m != m or cd is None or cd != cd:
                continue
            acc.setdefault(int(m), []).append(float(cd))
        return {k: float(np.median(v)) for k, v in sorted(acc.items())}

    @property
    def matched_frames(self) -> list[int]:
        return list(self.matched)

    @property
    def start_info(self) -> dict | None:
        if not START_FRAMES.exists():
            return None
        return json.loads(START_FRAMES.read_text()).get(self.name)

    @property
    def start_frame(self) -> int:
        """The dive's start frame, chosen by task 1.2 from fresh SAM 2 masks (start_frames.json)."""
        info = self.start_info
        if info is None or info.get("start") is None:
            raise RuntimeError(f"no start frame for {self.name}; run task 1.2 (python cli.py start-frames)")
        if info.get("gate_s"):
            raise RuntimeError(f"{self.name} failed Gate S ({info['gate_s']}), so its start frame is not used; "
                               "settle Gate S first (python cli.py start-frames)")
        return int(info["start"])

    def left_path(self, frame_idx: int) -> Path:
        return self.dir / self.frames["left"][frame_idx]

    def right_path(self, frame_idx: int) -> Path:
        return self.dir / self.frames["right"][frame_idx]

    @cached_property
    def calibration(self) -> Calibration:
        c = json.loads(self.calibration_path.read_text())
        return Calibration(
            fx=float(c["fx"]), cx=float(c["cx"]), cy=float(c["cy"]),
            baseline_mm=float(c["baseline_mm"]), width=int(c["width"]), height=int(c["height"]),
        )


def recordings(root: Path | None = None) -> dict[str, Recording]:
    root = root or data_root()
    return {c: Recording(c, n, root) for c, n in RECORDING_NAMES.items()}
