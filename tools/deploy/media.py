# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3==1.40.0"]
# ///
"""Upload Dive Twin's media (runs/assets/) to R2 under divetwin/v1/, and check it.

    op run --env-file=$HOME/projects/studio/tools/stilldrawn-r2.env.op -- uv run tools/deploy/media.py upload
    uv run tools/deploy/media.py check     # local files against the manifest, no network, no secrets
    uv run tools/deploy/media.py verify    # HEAD every key on the public host (no secrets needed)
    op run --env-file=... -- uv run tools/deploy/media.py verify --r2   # HEAD every key on the bucket itself, with the sha256 metadata

Exactly the keys in runs/assets/media_manifest.json (306), nothing else: MEDIA.md and media_manifest.json are not uploaded.
Every file is hashed against the manifest first; any mismatch stops the run before a byte is sent. The Runway gen.mp4 files are
sent as they are (never re-encoded or stripped: their C2PA credentials stay). Each object gets Cache-Control public, max-age=31536000,
immutable, its content type, and its sha256 as metadata. Re-runs skip objects whose size and sha256 metadata already match.

The R2 account id and keys come from the environment (op run); nothing here holds or prints a secret.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ASSETS = Path(os.environ.get("DIVETWIN_ASSETS") or Path(__file__).resolve().parents[2] / "runs" / "assets")
MANIFEST = ASSETS / "media_manifest.json"
CACHE = "public, max-age=31536000, immutable"
TYPES = {".mp4": "video/mp4", ".png": "image/png", ".jpg": "image/jpeg", ".json": "application/json"}


def load_items(assets: Path = ASSETS) -> tuple[dict, list[dict]]:
    m = json.loads((assets / "media_manifest.json").read_text())
    items = m["items"]
    for i in items:
        if not i["key"].startswith(m["prefix"]) or i["key"][len(m["prefix"]):] != i["path"]:
            raise ValueError(f"manifest key/path disagree: {i['key']} vs {i['path']}")
        want = TYPES.get(Path(i["path"]).suffix)
        if want != i["content_type"]:
            raise ValueError(f"unexpected content type for {i['path']}: {i['content_type']}")
    if len({i["key"] for i in items}) != len(items):
        raise ValueError("duplicate keys in the manifest")
    return m, items


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_local(items: list[dict], assets: Path = ASSETS, workers: int = 8) -> None:
    """Hash every file against the manifest; raise before anything is sent if one differs or is missing."""
    def one(i: dict) -> str | None:
        p = assets / i["path"]
        if not p.is_file():
            return f"missing: {i['path']}"
        if p.stat().st_size != i["bytes"]:
            return f"size differs: {i['path']} ({p.stat().st_size} != {i['bytes']})"
        if sha256_file(p) != i["sha256"]:
            return f"sha256 differs: {i['path']}"
        return None

    with ThreadPoolExecutor(workers) as ex:
        bad = [r for r in ex.map(one, items) if r]
    if bad:
        raise ValueError(f"{len(bad)} file(s) differ from media_manifest.json, e.g. {bad[0]}; nothing uploaded")


def r2_client():
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3", endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"], aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto", config=Config(retries={"max_attempts": 5, "mode": "standard"}, max_pool_connections=16))


def _missing(e: Exception) -> bool:
    return getattr(e, "response", {}).get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound")


def upload(items: list[dict], client, bucket: str, assets: Path = ASSETS, workers: int = 8, log=print) -> dict:
    check_local(items, assets, workers)
    log(f"{len(items)} files match the manifest; sending what is missing or changed")

    def one(i: dict) -> str:
        try:
            head = client.head_object(Bucket=bucket, Key=i["key"])
            if head["ContentLength"] == i["bytes"] and head.get("Metadata", {}).get("sha256") == i["sha256"]:
                return "skipped"
        except Exception as e:
            if not _missing(e):
                raise
        with open(assets / i["path"], "rb") as body:
            client.put_object(Bucket=bucket, Key=i["key"], Body=body, ContentType=i["content_type"],
                              CacheControl=i.get("cache_control") or CACHE, Metadata={"sha256": i["sha256"]})
        return "uploaded"

    stats = {"uploaded": 0, "skipped": 0}
    with ThreadPoolExecutor(workers) as ex:
        for n, r in enumerate(ex.map(one, items), 1):
            stats[r] += 1
            if n % 50 == 0 or n == len(items):
                log(f"{n}/{len(items)} {stats}")
    return stats


def verify_r2(items: list[dict], client, bucket: str, workers: int = 8) -> list[str]:
    """HEAD every key on the bucket: size, sha256 metadata, cache header and content type."""
    def one(i: dict) -> str | None:
        try:
            h = client.head_object(Bucket=bucket, Key=i["key"])
        except Exception as e:
            return f"{i['key']}: {'absent' if _missing(e) else type(e).__name__}"
        problems = []
        if h["ContentLength"] != i["bytes"]:
            problems.append("size")
        if h.get("Metadata", {}).get("sha256") != i["sha256"]:
            problems.append("sha256 metadata")
        if h.get("CacheControl") != CACHE:
            problems.append("cache-control")
        if h.get("ContentType") != i["content_type"]:
            problems.append("content-type")
        return f"{i['key']}: {', '.join(problems)}" if problems else None

    with ThreadPoolExecutor(workers) as ex:
        return [r for r in ex.map(one, items) if r]


def verify_public(items: list[dict], base: str, workers: int = 8) -> list[str]:
    """HEAD every key through the public host: 200, the right length and content type, the immutable cache header."""
    def one(i: dict) -> str | None:
        url = base + i["key"]
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "divetwin-verify"})
        try:
            with urllib.request.urlopen(req) as r:
                status, length, ctype, cache = r.status, r.headers.get("Content-Length"), r.headers.get("Content-Type"), r.headers.get("Cache-Control")
        except urllib.error.HTTPError as e:
            return f"{i['key']}: HTTP {e.code}"
        problems = []
        if status != 200:
            problems.append(f"status {status}")
        if length != str(i["bytes"]):
            problems.append(f"length {length}")
        if (ctype or "").split(";")[0] != i["content_type"]:
            problems.append(f"content-type {ctype}")
        if cache != CACHE:
            problems.append(f"cache-control {cache}")
        return f"{i['key']}: {', '.join(problems)}" if problems else None

    with ThreadPoolExecutor(workers) as ex:
        return [r for r in ex.map(one, items) if r]


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "check"
    m, items = load_items()
    total = sum(i["bytes"] for i in items)
    if cmd == "check":
        check_local(items)
        print(f"ok: {len(items)} files, {total} bytes, all match media_manifest.json")
    elif cmd == "upload":
        bucket = os.environ.get("R2_BUCKET", "stilldrawn-media")
        print(upload(items, r2_client(), bucket))
        print(f"{len(items)} keys under {m['prefix']}, {total} bytes")
    elif cmd == "verify":
        if "--r2" in argv:
            bad = verify_r2(items, r2_client(), os.environ.get("R2_BUCKET", "stilldrawn-media"))
            where = "bucket"
        else:
            bad = verify_public(items, m["public"])
            where = m["public"]
        print("\n".join(bad) if bad else f"ok: all {len(items)} keys answer correctly on {where} ({total} bytes)")
        return 1 if bad else 0
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
