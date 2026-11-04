# Redeploy

The page is static: `web/dist` plus `tools/deploy/vercel.json`, on Vercel's personal Hobby team (project `divetwin`), served at `https://divetwin.studionephele.com` (fallback alias `https://divetwin.vercel.app`). The media (306 files, 279,313,697 bytes) lives on R2 under `divetwin/v1/` and is served by `https://media.studionephele.com/`.

```bash
GO_LIVE=yes tools/deploy/deploy-production.sh
```

It runs `tools/deploy/stage.sh` (builds with `VITE_MEDIA_BASE=/media/`, stages `deploy/production/`, runs the identifier scan on exactly what ships), links the folder to the Vercel project `divetwin` once, and deploys to production. It refuses without `GO_LIVE=yes`: a production deploy is public, so it runs only on Aaron's word. Nothing here pushes to GitHub; the repo is public at `https://github.com/aaronlsmiles/divetwin`.

Needs two gitignored files:
- `.env.local` at this repo's root: `VERCEL_SCOPE=` the personal team's slug (never the company team). Copied from `prototypes/feelthedepth/.env.local`.
- `~/projects/studio/tools/divetwin.env.op` in the hub: `VERCEL_TOKEN=` as a 1Password secret reference (copied from `feelthedepth.env.op`). Never a raw value, never `--token`.

## Media (R2), once per media version

```bash
op run --env-file=$HOME/projects/studio/tools/stilldrawn-r2.env.op -- uv run tools/deploy/media.py upload
uv run tools/deploy/media.py check          # local files against media_manifest.json, no network
uv run tools/deploy/media.py verify         # HEAD every key on the public host (200, length, type, immutable cache)
op run --env-file=$HOME/projects/studio/tools/stilldrawn-r2.env.op -- uv run tools/deploy/media.py verify --r2   # HEAD on the bucket, with the sha256 metadata
```

Uploads exactly the keys in `runs/assets/media_manifest.json` (`MEDIA.md` and the manifest itself are not uploaded) to the `stilldrawn-media` bucket under `divetwin/v1/`, each with `Cache-Control: public, max-age=31536000, immutable`, its content type and its sha256 as metadata. Every file is hashed against the manifest first; one mismatch stops the run before a byte is sent. Re-runs skip objects whose size and sha256 match. The Runway `gen.mp4` files go up byte for byte (C2PA credentials intact). A changed file goes to a new prefix (`v2/`), never over `v1/`. The account id comes from the environment through `op run`; it is in no committed file.

## How `/media/` is served (`tools/deploy/vercel.json`, changed 4 Nov, hub call 90)

- **`.mp4` is a 308 redirect** to `https://media.studionephele.com/divetwin/v1/…`. The page's `<video>` elements load without `crossOrigin`, so no CORS is needed, and the media host answers Range requests itself.
- **JSON, PNG16 and JPEG media (203 files, 82 MB) ship as static files in the Vercel deployment**, under `/media/`, so the page's `fetch` and pixel reads are same-origin and need no CORS.
- **Why no rewrite to the media host (found 4 Nov):** Vercel's edge caches an external rewrite by URL and ignores `Range`, so the first range it sees is replayed to every later request (`content-range: bytes 0-1477784/1477785` for a `bytes=-4096` request on an mp4; 100 bytes of `clips.json` after a `curl -r 0-99`). The Runway `gen.mp4`, whose `moov` atom is at the end, failed with `MEDIA_ERR_NETWORK`. Do not probe with a Range request against a rewritten path.
- Anything else not a file falls back to `/` (the single page). `/assets/` is immutable for a year; `/film/` and `/media/` are one hour and must-revalidate.

## Domain (once; done)

`vercel domains add divetwin.studionephele.com divetwin --scope "$VERCEL_SCOPE"` (run outside the linked `deploy/production/` folder; inside it the CLI takes one argument and adds to the linked project). Done 4 Nov.

The CNAME is in place (4 Nov): `divetwin`, type CNAME, target `cname.vercel-dns.com`, **DNS only (grey cloud)** so Vercel issues the certificate, in the studionephele.com zone on Cloudflare. `https://divetwin.studionephele.com` answers 200. (Vercel also accepts an A record `76.76.21.21`, DNS only.) A production deploy also gets Vercel's default `divetwin.vercel.app`, kept as a fallback only: share the custom domain.

## Check, live (signed out)

- `curl -sIL https://divetwin.studionephele.com` → 200 (and `/?plain=1`); the fallback `https://divetwin.vercel.app` → 200 too
- `curl -sI https://divetwin.studionephele.com/media/clips.json` → 200, `content-type: application/json`
- `curl -sIL -H "Range: bytes=-4096" https://divetwin.studionephele.com/media/clips/freshwater-basicEnhance__gen45__N__5s/gen.mp4` → a 308, then a **206** from the media host with `content-range: bytes 1473689-1477784/1477785`, `accept-ranges: bytes` (the suffix range on the file with its `moov` at the end is the one that broke under the rewrite)
- one `/assets/` file → 200, `immutable`
- a fresh Chromium profile (not one that saw an earlier deploy) at 1440 and 390 px: the default clip loads, the three videos play, the relief draws (on a phone it is a still with an "Orbit the surfaces" button), no console errors, no "could not be loaded" line. Allowed notices: three.js's `THREE.Clock` deprecation and Chrome's one-off `GPU stall due to ReadPixels`.
- `tools/deploy/media.py verify` → all 306 keys answer correctly on the public host
