"""The film's clock, from the narration reads: where each line starts, where each caption chunk starts and ends, where each
shot's picture starts. Shared by capture.py and assemble.py. `python3 tools/film/timeline.py` prints it.

The voice sets the pace; the picture follows it. Each shot's picture starts 0.4 s before its line.
"""
import itertools, json, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CFG = json.loads((ROOT / "tools/film/film.json").read_text())
VO = ROOT / "film/vo"
FPS = 24
LEAD = 1.0                 # picture before the first word
GAP = 0.8                  # after a read's own trailing silence
EXTRA_GAP = {6: 1.0}       # after line 6 (the flare): a longer look at the plan view
LEAD_IN = 0.4              # a shot's picture starts this long before its line
TAIL = 2.6                 # the end card holds after the last word
SPLIT = {"16x9": 150, "9x16": 108}   # longest caption chunk, in characters


def line_files():
    log = json.loads((VO / "lines.json").read_text())
    by_line = {v["line"]: (k, v) for k, v in log.items()}
    return [(i, *by_line[i]) for i in range(1, len(CFG["lines"]) + 1)]


def silences(path, noise="-38dB", dur=0.12):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", f"silencedetect=n={noise}:d={dur}", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    out, start = [], None
    for m in re.finditer(r"silence_(start|end): ([\d.]+)", err):
        if m.group(1) == "start":
            start = float(m.group(2))
        elif start is not None:
            out.append((start, float(m.group(2)))); start = None
    if start is not None:
        out.append((start, None))
    return out


def chunks(text, maxchars):
    """Sentences; one longer than maxchars splits at the comma nearest its middle (repeatedly)."""
    def split(s):
        if len(s) <= maxchars or "," not in s:
            return [s]
        cs = [m.start() for m in re.finditer(",", s)]
        c = min(cs, key=lambda k: abs(k - len(s) / 2))
        return split(s[:c + 1].strip()) + split(s[c + 1:].strip())
    out = []
    for s in re.split(r"(?<=[.?!])\s+", text.strip()):
        out += split(s)
    return out


def build(aspect="16x9"):
    lines, t = [], LEAD
    for i, key, meta in line_files():
        path = VO / f"{key}.wav"
        dur = meta["duration"]
        sil = silences(path)
        end = dur - (dur - sil[-1][0] if sil and sil[-1][1] is None else 0) + 0.1   # speech ends where the trailing silence starts
        mids = [(a + (b if b is not None else dur)) / 2 for a, b in sil if b is not None and a > 0.2 and b < dur - 0.1]
        ch = chunks(meta["text"], SPLIT[aspect])
        total = sum(len(c) for c in ch)
        cum, guesses = 0, []
        for c in ch[:-1]:
            cum += len(c)
            guesses.append(end * cum / total)
        # the pauses the read itself made: pick, in order, the set nearest the by-characters guesses
        best = min(itertools.combinations(mids, len(guesses)), key=lambda cmb: sum(abs(m - g) for m, g in zip(cmb, guesses)), default=None) if guesses else ()
        bounds = list(best) if best is not None else guesses
        edges = [0.0] + bounds + [end + 0.2]
        caps = [{"text": c, "t0": t + edges[k], "t1": t + edges[k + 1]} for k, c in enumerate(ch)]
        lines.append({"i": i, "text": meta["text"], "file": f"{key}.wav", "start": t, "dur": dur, "speech_end": t + end, "captions": caps})
        t += dur + GAP + EXTRA_GAP.get(i, 0)
    total = lines[-1]["start"] + lines[-1]["dur"] + TAIL
    shots = []
    for k, L in enumerate(lines):
        t0 = 0.0 if k == 0 else L["start"] - LEAD_IN
        t1 = total if k == len(lines) - 1 else lines[k + 1]["start"] - LEAD_IN
        shots.append({"i": L["i"], "t0": t0, "t1": t1})
    return {"fps": FPS, "total": total, "lines": lines, "shots": shots}


if __name__ == "__main__":
    tl = build()
    print(f"total {tl['total']:.2f} s")
    for L, S in zip(tl["lines"], tl["shots"]):
        print(f"shot {S['i']}: {S['t0']:.2f}-{S['t1']:.2f}  line at {L['start']:.2f}, speech to {L['speech_end']:.2f}")
        for c in L["captions"]:
            print(f"     {c['t0']:.2f}-{c['t1']:.2f}  {c['text']}")
