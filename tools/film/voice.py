#!/usr/bin/env python3
"""Narration for the film: the studio voice (Hume Octave), one batch read of the nine lines in tools/film/film.json.

Run under op run so the key never sits in a file (it reads HUME_API_KEY):
    op run --env-file=$HOME/projects/studio/tools/hume.env.op -- python3 tools/film/voice.py [--yes] [--retake N ...]

Without --yes it prints the characters it would send and stops (characters are what Hume bills). Reads land in film/vo/
(git-ignored; lines.json, the ids and durations, is tracked). A line already read is never read again, so re-running the
film build costs nothing; `--retake N` (1-based) reads line N again, replacing its wav (at most one retake per line, by hand).
Modelled on prototypes/stilldrawn-explorer/film/build/voice.py: same voice id, same acting direction, same delivery context.
"""
import base64, hashlib, json, os, sys, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CFG = json.loads((ROOT / "tools/film/film.json").read_text())
VO = ROOT / "film/vo"
API = "https://api.hume.ai/v0/tts"


def post(body):
    key = os.environ.get("HUME_API_KEY")
    if not key:
        sys.exit("HUME_API_KEY is not set: run under op run with the studio's tools/hume.env.op")
    req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST",
                                 headers={"X-Hume-Api-Key": key, "Content-Type": "application/json"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 4:  # a per-minute request quota, not a character limit
                time.sleep(15 * (attempt + 1)); continue
            sys.exit(f"Hume {e.code}: {e.read().decode(errors='replace')[:400]}")  # stop: no other voice, no fallback


def key_of(i, say):
    v = CFG["voice"]
    return f"{i:02d}-" + hashlib.sha1(json.dumps([say, v["id"], v["acting"], v["speed"]]).encode()).hexdigest()[:8]


def main():
    retake = {int(a) for a in sys.argv[sys.argv.index("--retake") + 1:] if a.isdigit()} if "--retake" in sys.argv else set()
    log_path = VO / "lines.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else {}
    todo = []
    for i, say in enumerate(CFG["lines"], 1):
        k = key_of(i, say)
        if i in retake or not (VO / f"{k}.wav").exists():
            todo.append((i, k, say))
    chars = sum(len(s) for *_, s in todo)
    print(f"{len(todo)} of {len(CFG['lines'])} lines to read: {chars} characters")
    if not todo:
        return
    if "--yes" not in sys.argv:
        print("not sent: add --yes to spend them"); return
    v = CFG["voice"]
    VO.mkdir(parents=True, exist_ok=True)
    for i, k, say in todo:
        utt = {"text": say, "voice": {"id": v["id"], "provider": "CUSTOM_VOICE"}, "description": v["acting"], "speed": v["speed"]}
        g = post({"utterances": [utt], "format": {"type": "wav"}, "context": {"generation_id": v["context_generation"]}})["generations"][0]
        (VO / f"{k}.wav").write_bytes(base64.b64decode(g["audio"]))
        log = {kk: vv for kk, vv in log.items() if vv.get("line") != i}   # a re-read line replaces its old entry
        log[k] = {"line": i, "text": say, "generation_id": g["generation_id"], "duration": g["duration"], "characters": len(say)}
        log_path.write_text(json.dumps(log, indent=1, ensure_ascii=False) + "\n")
        print(f"{i} {g['duration']:.2f} s  {say[:70]}")


main()
