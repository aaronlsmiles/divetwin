#!/usr/bin/env bash
# One command: tools/film/make-film.sh   (from anywhere). See tools/film/README.md.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CAP="$ROOT/film/.capture"
OUT="$ROOT/film/out"
mkdir -p "$CAP" "$OUT"

# 1. The narration: the nine reads must already exist (film/vo). Reading them is a paid call that needs a decision:
#    op run --env-file=$HOME/projects/studio/tools/hume.env.op -- python3 tools/film/voice.py --yes
python3 "$ROOT/tools/film/voice.py" | tee "$CAP/voice-check.txt"
grep -q "^0 of 9 lines to read" "$CAP/voice-check.txt" || { echo "narration is missing: run tools/film/voice.py --yes under op run (see its header)"; exit 1; }

# 2. The page, built against the real clips (/media/ is served from runs/assets by vite/media-dev.ts, preview included)
[ -d "$ROOT/web/node_modules" ] || npm --prefix "$ROOT/web" ci --no-audit --no-fund
(cd "$ROOT/web" && VITE_MEDIA_BASE=/media/ npx vite build --outDir "$CAP/dist" --emptyOutDir >/dev/null)
BUILD="$(ls "$CAP/dist/assets" | shasum | cut -c1-8)"   # the stills are cached under this id: a changed page is captured again

# 3. A free port that is not 5196 or 5199 (nor the dev ports of the page's tests)
PORT="$(python3 - <<'PY'
import socket
while True:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    if p not in (5196, 5199, 5173, 5299, 5393): print(p); break
PY
)"
(cd "$ROOT/web" && exec npx vite preview --outDir "$CAP/dist" --host 127.0.0.1 --port "$PORT" --strictPort >"$CAP/server.log" 2>&1) &
SRV=$!
trap 'kill $SRV 2>/dev/null || true; pkill -P $SRV 2>/dev/null || true' EXIT
for _ in $(seq 1 50); do curl -sf "http://127.0.0.1:$PORT/media/clips.json" >/dev/null && break; sleep 0.2; done
curl -sf "http://127.0.0.1:$PORT/media/clips.json" >/dev/null || { echo "the page's media is not being served (runs/assets missing?)"; exit 1; }

# 4. Capture every shot from the real page (one still per page frame), then assemble each cut
for A in 16x9 9x16; do
  python3 "$ROOT/tools/film/capture.py" "http://127.0.0.1:$PORT" "$CAP/$A" "$A" "$BUILD"
  python3 "$ROOT/tools/film/assemble.py" "$CAP/$A" "$OUT" "$A" "$BUILD"
done

# 5. The page's copy of the 16:9 cut (web/public/film/, tracked): the mp4 as it is, the poster as a high-quality JPEG
PUB="$ROOT/web/public/film"
mkdir -p "$PUB"
cp "$OUT/divetwin-16x9.mp4" "$PUB/divetwin-16x9.mp4"
ffmpeg -y -v error -i "$OUT/divetwin-16x9-poster.png" -q:v 2 "$PUB/divetwin-16x9-poster.jpg"

echo "done: $OUT (and the page's copy in $PUB)"
ls -la "$OUT" "$PUB"
