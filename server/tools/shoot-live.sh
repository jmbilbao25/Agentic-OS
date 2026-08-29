#!/usr/bin/env bash
# Screenshot the deployed instance over the public URL. Same driving as shoot.sh,
# but against real TLS and the real credential, because "it works locally" has
# never once been the same claim as "it works".
#
# Usage: AGENTOS_URL=https://… AGENTOS_USER=… AGENTOS_PASSWORD=… bash server/tools/shoot-live.sh
set -uo pipefail

BASE=${AGENTOS_URL:?set AGENTOS_URL}
: "${AGENTOS_USER:?set AGENTOS_USER}"
: "${AGENTOS_PASSWORD:?set AGENTOS_PASSWORD}"
OUT=${OUT:-/projects/sandbox/.kiro/artifacts/screenshots}
S=${SESSION_ID:-live}
mkdir -p "$OUT"
export PATH="$(ls -d /root/.nvm/versions/node/*/bin 2>/dev/null | tail -1):$PATH"

ab() { agent-browser --session "$S" "$@"; }
trap 'ab close >/dev/null 2>&1' EXIT

echo "health: $(curl -s -o /dev/null -w '%{http_code}' "$BASE/healthz")"

ab open "$BASE/auth/login" >/dev/null
ab fill '#u' "$AGENTOS_USER" >/dev/null
ab fill '#p' "$AGENTOS_PASSWORD" >/dev/null
ab click 'button[type=submit]' >/dev/null
ab wait 3000 >/dev/null
ab eval 'document.querySelector("#stage")?"signed in":"LOGIN FAILED: "+location.href'

ab eval 'window.__err=[];addEventListener("error",e=>window.__err.push(e.message))' >/dev/null

shot() { ab wait "${2:-1600}" >/dev/null; ab screenshot "$OUT/$1.png" >/dev/null; echo "  $1.png"; }

ab eval 'localStorage.removeItem("agentos.layout")' >/dev/null
ab open "$BASE/" >/dev/null
shot live-01-rings 3200
ab press '2' >/dev/null; shot live-02-rank
ab press '/' >/dev/null; ab wait 500 >/dev/null
ab keyboard type 'context rot' >/dev/null
ab wait 1500 >/dev/null
ab press 'Escape' >/dev/null
shot live-03-rank-search 1800
ab press '4' >/dev/null; shot live-04-timeline

echo "layout control present: $(ab eval 'document.querySelectorAll(".layout-btn").length + " buttons"')"
echo "js errors: $(ab eval 'window.__err.length ? window.__err.join(" | ") : "none"')"
