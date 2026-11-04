#!/usr/bin/env bash
# PUBLIC production deploy of the page to the personal Hobby team: divetwin.studionephele.com.
# Run only with Aaron's word for this deploy: GO_LIVE=yes tools/deploy/deploy-production.sh
# Needs two gitignored files (REDEPLOY.md): .env.local here (VERCEL_SCOPE) and the hub's tools/divetwin.env.op (VERCEL_TOKEN reference).
# The media is already on R2 (tools/deploy/media.py); this script ships only the page.
set -euo pipefail
[ "${GO_LIVE:-}" = yes ] || { echo "refusing: a production deploy is public; set GO_LIVE=yes only with Aaron's word" >&2; exit 2; }
here="$(cd "$(dirname "$0")/../.." && pwd)"
set -a; . "$here/.env.local"; set +a
: "${VERCEL_SCOPE:?set VERCEL_SCOPE in .env.local}"
"$here/tools/deploy/stage.sh"
cd "$here/deploy/production"
ENV_OP="${ENV_OP:-$HOME/projects/studio/tools/divetwin.env.op}"
run() { op run --env-file="$ENV_OP" -- "$@"; }
[ -f .vercel/project.json ] || run vercel link --yes --scope "$VERCEL_SCOPE" --project divetwin
run vercel deploy --yes --prod --scope "$VERCEL_SCOPE"
