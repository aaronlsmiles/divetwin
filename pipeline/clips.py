"""Clip ids, seeds, mp4 checks and the two indexes (runs/clips_index.json, runs/probes_index.json).

One clip is one (condition, engine, prompt, length) generation. Its id is the file stem everywhere:
    runs/gen45/<id>.mp4   runs/wan22/<id>.mp4   runs/da3/clips/<id>.npz   runs/dive/<id>.json   runs/mapping/<id>.json
Id forms (condition names contain hyphens but never underscores, so '__' separates the parts):
    final   air__gen45__D__5s            5 s on either engine, or the 10 s Gen-4.5 dive (prompt D only)
    probe   air__gen45__D__probe2s       a 2 s Gen-4.5 probe: never a final, never in clips_index.json
    hunt    air__gen45__B__5s__h03       the invention hunt's 3rd take (Gen-4.5, prompt B, 5 s)
The prompt text itself lives only in prompts.PROMPTS."""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from recordings import RECORDING_NAMES, runs_dir

ENGINES = ("gen45", "wan22")
PROMPT_KEYS = ("D", "B", "N")
FPS = 24
GRID = {"gen45": (1280, 720), "wan22": (1280, 704)}
HUNT_MAX_TAKES = 10
_ID = re.compile(r"^(?P<cond>[A-Za-z]+(?:-[A-Za-z]+)*)__(?P<engine>gen45|wan22)__(?P<prompt>[DBN])__"
                 r"(?:probe(?P<probe>2)s|(?P<sec>5|10)s(?:__h(?P<take>\d{2}))?)$")


@dataclass(frozen=True)
class ClipSpec:
    condition: str
    engine: str
    prompt: str
    seconds: int
    kind: str = "final"          # "final" | "probe" | "hunt"
    take: int | None = None      # the hunt take number, 1..10 (hunt only)

    def __post_init__(self):
        bad = None
        if self.condition not in RECORDING_NAMES:
            bad = f"unknown condition {self.condition!r}"
        elif self.engine not in ENGINES or self.prompt not in PROMPT_KEYS:
            bad = f"unknown engine or prompt: {self.engine!r}, {self.prompt!r}"
        elif self.kind == "probe" and not (self.engine == "gen45" and self.seconds == 2 and self.take is None):
            bad = "a probe is Gen-4.5, 2 s, no take"
        elif self.kind == "final" and not (self.take is None and (
                self.seconds == 5 or (self.seconds == 10 and self.engine == "gen45" and self.prompt == "D"))):
            bad = "a final is 5 s on either engine, or the 10 s Gen-4.5 dive (prompt D); no take"
        elif self.kind == "hunt" and not (self.engine == "gen45" and self.prompt == "B" and self.seconds == 5
                                          and self.take is not None and 1 <= self.take <= HUNT_MAX_TAKES):
            bad = f"a hunt take is Gen-4.5, prompt B, 5 s, take 1..{HUNT_MAX_TAKES}"
        elif self.kind not in ("final", "probe", "hunt"):
            bad = f"unknown kind {self.kind!r}"
        if bad:
            raise ValueError(bad)

    @property
    def id(self) -> str:
        head = f"{self.condition}__{self.engine}__{self.prompt}__"
        if self.kind == "probe":
            return head + "probe2s"
        return head + f"{self.seconds}s" + (f"__h{self.take:02d}" if self.kind == "hunt" else "")

    @property
    def in_finals_index(self) -> bool:
        return self.kind in ("final", "hunt")


def parse_clip_id(cid: str) -> ClipSpec:
    m = _ID.match(cid)
    if not m:
        raise ValueError(f"not a clip id: {cid!r}")
    if m["probe"]:
        return ClipSpec(m["cond"], m["engine"], m["prompt"], 2, "probe")
    return ClipSpec(m["cond"], m["engine"], m["prompt"], int(m["sec"]), "hunt" if m["take"] else "final",
                    int(m["take"]) if m["take"] else None)


def seed_for(spec: ClipSpec, retake: int = 0) -> int:
    """The fixed seed for one clip, a pure function of its parts (0..2**32-1; Runway's range).

    Prompts B and N share one seed per (engine, condition, length) so the A/B differs in the words only
    (call 6); D has its own. A hunt take has its own seed per take; a retake (logged reason) its own per
    retake count."""
    arm = "BN" if spec.prompt in ("B", "N") else spec.prompt
    key = "/".join(["divetwin-seed-v1", spec.engine, spec.condition, arm, f"{spec.seconds}s", spec.kind,
                    str(spec.take or 0), str(retake)])
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:4], "big")


def expected_frames(spec: ClipSpec) -> int:
    """Gen-4.5 renders 24 fps and one frame more than the seconds (5 s = 121); Wan 2.2 is always 121."""
    return 121 if spec.engine == "wan22" else FPS * spec.seconds + 1


def video_dir(engine: str) -> Path:
    return runs_dir() / engine


def video_path(spec: ClipSpec) -> Path:
    return video_dir(spec.engine) / f"{spec.id}.mp4"


def depth_path(spec: ClipSpec) -> Path:
    return runs_dir() / "da3" / "clips" / f"{spec.id}.npz"


def depth_ready(spec: ClipSpec) -> bool:
    """A depth file exists for the clip (clipdepth.check_depth, task 3.1, says whether it is the contract's)."""
    return depth_path(spec).exists()


# ---- retakes: the one record both engines share --------------------------------------------------------

def retakes_path() -> Path:
    return runs_dir() / "retakes.jsonl"


def retake_count(spec: ClipSpec) -> int:
    """How many logged retakes this clip has had; its next seed is seed_for(spec, retake_count)."""
    p = retakes_path()
    if not p.exists():
        return 0
    return sum(1 for t in p.read_text().splitlines() if t.strip() and json.loads(t).get("clip") == spec.id)


def retire_existing(spec: ClipSpec) -> Path | None:
    """Move the clip's current mp4 to <engine dir>/retired/<id>__<time>.mp4 (kept, never deleted)."""
    p = video_path(spec)
    if not p.exists():
        return None
    dest = p.parent / "retired" / f"{spec.id}__{time.strftime('%Y%m%dT%H%M%S')}.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)
    p.rename(dest)
    return dest


def log_retake(spec: ClipSpec, n: int, reason: str, seed: int, retired: Path | None) -> None:
    retakes_path().parent.mkdir(parents=True, exist_ok=True)
    with open(retakes_path(), "a") as fh:
        fh.write(json.dumps({"clip": spec.id, "retake": n, "reason": reason, "seed": seed,
                             "retired": str(retired) if retired else None, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")


def check_mp4(path, frames: int | None = None, size: tuple[int, int] | None = None) -> dict:
    """Decode a clip and say whether it is the expected one: {'ok', 'frames', 'size', 'fps', 'reason'}.
    A missing or unreadable file is not ok (never an exception)."""
    import av
    out = {"ok": False, "frames": 0, "size": None, "fps": None, "reason": None}
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        out["reason"] = "missing or empty"
        return out
    try:
        with av.open(str(p)) as c:
            s = c.streams.video[0]
            out["fps"] = float(s.average_rate) if s.average_rate else None
            n, wh = 0, None
            for f in c.decode(video=0):
                n += 1
                wh = (f.width, f.height)
    except Exception as e:  # a truncated download is an expected failure, not a crash
        out["reason"] = f"unreadable: {type(e).__name__}: {str(e)[:120]}"
        return out
    out.update(frames=n, size=wh)
    if n == 0:
        out["reason"] = "no frames"
    elif frames is not None and n != frames:
        out["reason"] = f"{n} frames, expected {frames}"
    elif size is not None and wh != tuple(size):
        out["reason"] = f"{wh[0]}x{wh[1]}, expected {size[0]}x{size[1]}"
    else:
        out["ok"] = True
    return out


def check_clip(spec: ClipSpec) -> dict:
    return check_mp4(video_path(spec), expected_frames(spec), GRID[spec.engine])


def clip_entry(spec: ClipSpec) -> dict:
    """One clips_index.json entry: exactly the sub-plan A section 5 schema."""
    return {"condition": spec.condition, "engine": spec.engine, "prompt": spec.prompt, "seconds": spec.seconds,
            "take": spec.take, "video": str(video_path(spec)), "depth": str(depth_path(spec))}


def scan_clips(check: bool = True) -> tuple[list[ClipSpec], list[tuple[str, str]]]:
    """(valid clips, [(file stem, why not)]) under runs/gen45 and runs/wan22. Files that are not clip ids
    (and anything in a subfolder, such as retired/) are ignored."""
    good, bad = [], []
    for eng in ENGINES:
        for p in sorted(video_dir(eng).glob("*.mp4")):
            try:
                spec = parse_clip_id(p.stem)
            except ValueError:
                continue
            if spec.engine != eng:
                bad.append((p.stem, f"lives in runs/{eng}/ but is named for {spec.engine}"))
                continue
            r = check_clip(spec) if check else {"ok": True}
            (good if r["ok"] else bad).append(spec if r["ok"] else (p.stem, r["reason"]))
    return good, bad


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, allow_nan=False) + "\n")


def rebuild_clips_index(check: bool = True) -> dict:
    """runs/clips_index.json from the valid finals and hunt takes on disk. Probes are never in it."""
    good, bad = scan_clips(check)
    idx = {s.id: clip_entry(s) for s in good if s.in_finals_index}
    _write_json(runs_dir() / "clips_index.json", idx)
    return {"index": idx, "invalid": bad}


def rebuild_probes_index(check: bool = True) -> dict:
    """runs/probes_index.json: {id: {condition, prompt, seed, video}} for the valid 2 s probes."""
    good, bad = scan_clips(check)
    idx = {s.id: {"condition": s.condition, "engine": s.engine, "prompt": s.prompt, "seconds": 2,
                  "seed": seed_for(s), "video": str(video_path(s))} for s in good if s.kind == "probe"}
    _write_json(runs_dir() / "probes_index.json", idx)
    return {"index": idx, "invalid": bad}
