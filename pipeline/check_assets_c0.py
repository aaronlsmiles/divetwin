"""Task C0's check on a built runs/assets: every derived video has a keyframe at least every GOP frames, every gen.mp4 is the engine's
own bytes (its sha256 equals the clip block's source_sha256 and the source file's), and the palette and relief blocks carry what the
page reads. Usage: uv run python check_assets_c0.py [clip id ...]   (no ids: all clips in clips.json). Exit 1 on any miss."""
import hashlib, json, sys

import av

import assets
import clips as clipmod
from clips import parse_clip_id


def keyframes(path):
    with av.open(str(path)) as c:
        s = c.streams.video[0]
        return [i for i, p in enumerate(p for p in c.demux(s) if p.size) if p.is_keyframe]


def main(ids):
    root = assets.assets_dir()
    doc = json.loads((root / "clips.json").read_text())
    bad = []
    heat = doc["heat"]
    if "floor_ramp" not in heat or "floor_means" not in heat:
        bad.append("heat lacks floor_ramp or floor_means")
    for c in doc["clips"]:
        if ids and c["clip"] not in ids:
            continue
        cid = c["clip"]
        before = len(bad)
        for k in ("fx", "fy", "cx", "cy"):
            if not isinstance(c["relief"].get(k), float):
                bad.append(f"{cid}: relief.{k} missing")
        for name in ("heat", "real"):
            p = root / c["assets"][name]
            kf = keyframes(p)
            n = c["n_frames"]
            gap = max(b - a for a, b in zip(kf, kf[1:] + [n]))
            if kf[0] != 0 or gap > assets.GOP:
                bad.append(f"{cid}: {name}.mp4 keyframes {kf[:6]}... largest gap {gap} (limit {assets.GOP})")
        src = hashlib.sha256(clipmod.video_path(parse_clip_id(cid)).read_bytes()).hexdigest()
        gen = hashlib.sha256((root / c["assets"]["gen"]).read_bytes()).hexdigest()
        if not (src == gen == c["provenance"]["source_sha256"]) or c["provenance"]["gen"] != "engine original, byte copy":
            bad.append(f"{cid}: gen.mp4 is not the engine's file byte for byte")
        if len(bad) == before:
            print(f"{cid}: heat and real keyframes every <= {assets.GOP}, gen.mp4 sha256 {gen[:12]} = source")
    for b in bad:
        print("MISS", b)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main(set(sys.argv[1:]))
