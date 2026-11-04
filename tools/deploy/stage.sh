#!/usr/bin/env bash
# Builds the page and stages deploy/production/: the static build plus vercel.json, nothing else.
# The build reads its media through the same-origin /media/ path. Everything but the mp4s (JSON, PNG16 atlases, JPEGs; about 82 MB)
# ships as static files under /media/: an external rewrite to the media host let Vercel's edge cache one byte range of a
# file and serve it to every later request (5 Nov: a range check left clips.json at 100 bytes for everyone). The mp4s
# redirect to the media host (vercel.json), which answers ranges properly; a <video> needs no CORS.
set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
out="$here/deploy/production"
(cd "$here/web" && VITE_MEDIA_BASE=/media/ npm run build --silent)
# Keep the Vercel link between deploys; replace everything else.
mkdir -p "$out"
find "$out" -mindepth 1 -maxdepth 1 ! -name .vercel -exec rm -rf {} +
cp -R "$here/web/dist/." "$out/"
cp "$here/tools/deploy/vercel.json" "$out/vercel.json"
(cd "$here/runs/assets" && find . -type f ! -name '*.mp4' ! -name MEDIA.md ! -name media_manifest.json -print0 \
  | while IFS= read -r -d '' f; do mkdir -p "$out/media/$(dirname "$f")"; cp "$f" "$out/media/$f"; done)
# The identifier scan must pass on exactly what ships: the build and vercel.json (not .vercel/, the local project link, which is kept between deploys and never uploaded as content).
"$HOME/projects/studio/tools/scan-identifiers.sh" "$here/web/dist" "$here/tools/deploy/vercel.json" "$out/media"
echo "staged: $out"
