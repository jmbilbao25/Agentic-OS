#!/usr/bin/env bash
# Screenshot harness. Brings the app up on a throwaway port, drives the real UI in
# a real browser, captures every layout, tears it all down.
#
# One script rather than a sequence of commands because the sandbox reaps
# background processes between invocations: the server has to be born, used and
# buried inside a single call or it is gone before the browser asks for it.
#
# Usage: bash server/tools/shoot.sh
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

OUT=${OUT:-/projects/sandbox/.kiro/artifacts/screenshots}
LOG=/tmp/agentos-shoot.log
SLOT=${SLOT:-8111}
BASE="http://127.0.0.1:$SLOT"
S=${SESSION_ID:-shoot}
mkdir -p "$OUT"
export PATH="$(ls -d /root/.nvm/versions/node/*/bin 2>/dev/null | tail -1):$PATH"

# Prefer a virtualenv if one is around: the sandbox's system python has no
# uvicorn, and installing into it on every run costs a minute for nothing.
PY=python3
for c in "${VENV:-}/bin/python" ../.agentos-venv/bin/python .venv/bin/python; do
  [ -x "$c" ] && { PY=$c; break; }
done
"$PY" -c 'import uvicorn' 2>/dev/null || {
  echo "no uvicorn for $PY — create a venv:"
  echo "  python3 -m venv /projects/sandbox/.agentos-venv"
  echo "  /projects/sandbox/.agentos-venv/bin/pip install -r server/requirements.txt"
  exit 1
}

# Mint a throwaway credential for this run instead of asking for the real one.
# load_dotenv does not override an existing variable, so exporting here wins over
# server/.env without editing it — the harness needs no secret and cannot leak one.
USER=shoot
PASS=$("$PY" -c 'import secrets;print(secrets.token_urlsafe(18))')
export AGENTOS_USER="$USER"
export AGENTOS_PASSWORD_HASH=$("$PY" -c '
import sys; sys.path.insert(0, ".")
from server.passwd import hash_password
print(hash_password(sys.argv[1]))' "$PASS")
export SESSION_SECRET=$("$PY" -c 'import secrets;print(secrets.token_hex(32))')

"$PY" -m uvicorn server.app:app --host 127.0.0.1 --port "$SLOT" \
  --log-level warning > "$LOG" 2>&1 &
SRV=$!
cleanup() {
  agent-browser --session "$S" close >/dev/null 2>&1
  kill "$SRV" 2>/dev/null; wait "$SRV" 2>/dev/null
}
trap cleanup EXIT

up=
for _ in $(seq 1 120); do
  curl -sf "$BASE/healthz" -o /dev/null 2>/dev/null && { up=1; break; }
  kill -0 "$SRV" 2>/dev/null || break
  sleep 1
done
[ -n "$up" ] || { echo "server never came up:"; tail -40 "$LOG"; exit 1; }
echo "server up on $BASE"

ab() { agent-browser --session "$S" "$@"; }

# Sign in through the form rather than by forging a cookie: it exercises the CSRF
# path too, so a broken login shows up here instead of in production.
ab open "$BASE/auth/login" >/dev/null
ab fill '#u' "$USER" >/dev/null
ab fill '#p' "$PASS" >/dev/null
ab click 'button[type=submit]' >/dev/null
ab wait 1500 >/dev/null
if ! ab eval 'document.querySelector("#stage") ? "ok" : "no-stage"' 2>/dev/null \
     | grep -q ok; then
  echo "login did not reach the app:"; ab eval 'location.href' ; exit 1
fi
echo "signed in"

# The map animates; give each transition longer than the 780ms morph to settle.
shot() {
  ab wait "${2:-1400}" >/dev/null
  ab screenshot "$OUT/$1.png" >/dev/null
  echo "  captured $1.png"
}

echo "errors: $(ab eval 'window.__err ? window.__err.join(" | ") : "none"')"
ab eval 'window.__err=[];addEventListener("error",e=>window.__err.push(e.message));
         addEventListener("unhandledrejection",e=>window.__err.push(String(e.reason)))' >/dev/null

echo "capturing layouts"
ab eval 'localStorage.removeItem("agentos.layout")' >/dev/null
ab open "$BASE/" >/dev/null
shot 01-rings 2600

ab press '2' >/dev/null;  shot 02-rank
ab press '3' >/dev/null;  shot 03-grid
ab press '4' >/dev/null;  shot 04-timeline
ab press '1' >/dev/null;  shot 05-back-to-rings

# The point of Rank: search, and the line reorders behind the finder.
ab press '2' >/dev/null;  ab wait 900 >/dev/null
ab press '/' >/dev/null;  ab wait 400 >/dev/null
ab keyboard type 'context' >/dev/null
shot 06-rank-search 1800
ab press 'Escape' >/dev/null
shot 07-rank-search-persists 1600

# …and the other half of the ask: a filter should promote what survives it, not
# leave the survivors scattered among ghosts.
ab eval 'const s=document.querySelector("#scrub");s.value=42;
         s.dispatchEvent(new Event("input",{bubbles:true}))' >/dev/null
shot 08-rank-recency-filter 1700
ab eval 'const r=document.querySelector("#scrub");r.value=100;
         r.dispatchEvent(new Event("input",{bubbles:true}))' >/dev/null

# Zoomed in, where the label budget opens up and collisions are most likely.
ab press '3' >/dev/null; ab wait 1200 >/dev/null
ab press '=' >/dev/null; ab press '=' >/dev/null
shot 09-grid-zoomed 1600

echo "js errors: $(ab eval 'Array.isArray(window.__err) && window.__err.length
  ? window.__err.join(" | ") : "none"')"
ls -la "$OUT" | grep -E '0[0-9]-'
