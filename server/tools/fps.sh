#!/usr/bin/env bash
# Frame rate per layout. The ring view was tuned to 60fps once already; a layout
# that quietly costs 20 of those frames is a regression whether or not it looks
# right in a still.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

SLOT=${SLOT:-8112}
BASE="http://127.0.0.1:$SLOT"
S=fps
export PATH="$(ls -d /root/.nvm/versions/node/*/bin 2>/dev/null | tail -1):$PATH"

PY=python3
for c in /projects/sandbox/.agentos-venv/bin/python .venv/bin/python; do
  [ -x "$c" ] && { PY=$c; break; }
done

USER=fps
PASS=$("$PY" -c 'import secrets;print(secrets.token_urlsafe(18))')
export AGENTOS_USER="$USER"
export AGENTOS_PASSWORD_HASH=$("$PY" -c '
import sys; sys.path.insert(0, ".")
from server.passwd import hash_password
print(hash_password(sys.argv[1]))' "$PASS")
export SESSION_SECRET=$("$PY" -c 'import secrets;print(secrets.token_hex(32))')

"$PY" -m uvicorn server.app:app --host 127.0.0.1 --port "$SLOT" \
  --log-level warning > /tmp/agentos-fps.log 2>&1 &
SRV=$!
cleanup() {
  agent-browser --session "$S" close >/dev/null 2>&1
  kill "$SRV" 2>/dev/null; wait "$SRV" 2>/dev/null
}
trap cleanup EXIT

for _ in $(seq 1 120); do
  curl -sf "$BASE/healthz" -o /dev/null 2>/dev/null && break
  kill -0 "$SRV" 2>/dev/null || break
  sleep 1
done

ab() { agent-browser --session "$S" "$@"; }
ab open "$BASE/auth/login" >/dev/null
ab fill '#u' "$USER" >/dev/null
ab fill '#p' "$PASS" >/dev/null
ab click 'button[type=submit]' >/dev/null
ab wait 2500 >/dev/null

for i in 1 2 3 4; do
  ab press "$i" >/dev/null
  ab wait 1500 >/dev/null                     # let the morph finish first
  echo -n "layout $i: "
  ab eval 'new Promise(res=>{let n=0;const t0=performance.now();
    const tick=()=>{n++;performance.now()-t0<1500?requestAnimationFrame(tick)
      :res(Math.round(n/((performance.now()-t0)/1000)))};
    requestAnimationFrame(tick)})'
done
