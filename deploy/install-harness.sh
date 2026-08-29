#!/usr/bin/env bash
# Install the JM Agentic-OS Harness beside an already-provisioned vault.
# Idempotent — safe to re-run after a git pull.
#
#   bash deploy/install-harness.sh
#
# Assumes deploy/provision.sh has already run (the app, the venv, the index and
# the agentos.service unit). This adds: Node 22, the DSH runtime from npm, an MCP
# token, the harness unit, and optionally an HTTPS front door with a password.
#
# Publishing it (off by default — read deploy/Caddyfile.harness first):
#   PUBLISH_HARNESS=1 HARNESS_PASSWORD='a long passphrase' bash deploy/install-harness.sh
set -euo pipefail

DIR="${DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# Pinned rather than @latest: DSH is pre-1.0 and the config shape this repo's
# patch overlay targets is the shape this version ships. Bump deliberately.
DSH_VERSION="${DSH_VERSION:-0.1.1-rc.2}"
NODE_VERSION="${NODE_VERSION:-22}"
PUBLISH_HARNESS="${PUBLISH_HARNESS:-0}"

say()  { printf '\n\033[1;33m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;31m!!\033[0m %s\n' "$*" >&2; }
die()  { warn "$*"; exit 1; }

cd "$DIR"
[ -f server/app.py ] || die "run this from the Agentic-OS checkout (no server/app.py in $DIR)"

# --------------------------------------------------------------- 1. Node 22
#
# Amazon Linux 2023 ships Node 18/20; DSH needs ^22.19 || >=24. nvm keeps this
# out of the system package set, so a distro Node upgrade cannot break it.
need_node() {
  command -v node >/dev/null || return 0
  node -e 'const [a,b]=process.versions.node.split(".").map(Number);
           process.exit((a>22||(a===22&&b>=19))?0:1)' 2>/dev/null && return 1 || return 0
}

if need_node; then
  say "installing Node ${NODE_VERSION} via nvm (DSH needs >=22.19; AL2023 ships 20)"
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  if [ ! -s "$NVM_DIR/nvm.sh" ]; then
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
  fi
  # shellcheck disable=SC1091
  . "$NVM_DIR/nvm.sh"
  nvm install "$NODE_VERSION" >/dev/null
  nvm alias default "$NODE_VERSION" >/dev/null
else
  say "node $(node -v) already satisfies DSH"
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" || true
fi

NODE_BIN="$(dirname "$(command -v node)")"
say "node: $(node -v) at $NODE_BIN"

# ----------------------------------------------------------------- 2. DSH
#
# The published package is prebuilt JavaScript, so this is a download rather than
# a pnpm workspace build — which matters, because building the monorepo on a
# t3.micro would exhaust the box.
if [ "$(dsh --version 2>/dev/null || echo none)" = "$DSH_VERSION" ]; then
  say "dsh $DSH_VERSION already installed"
else
  say "installing @deepseek-ai/dsh@$DSH_VERSION from npm"
  npm install -g --no-fund --no-audit "@deepseek-ai/dsh@$DSH_VERSION"
fi
command -v dsh >/dev/null || die "dsh is not on PATH after install"

# ------------------------------------------------------- 3. the MCP token
#
# This is what lets the harness reach the vault, and it is the only thing between
# a local process and write access to brain/. Generated once, then left alone.
touch server/.env
chmod 600 server/.env
if grep -q '^AGENTOS_MCP_TOKEN=..' server/.env 2>/dev/null; then
  say "AGENTOS_MCP_TOKEN already set, leaving it alone"
else
  say "generating AGENTOS_MCP_TOKEN"
  TOKEN="$(openssl rand -hex 32)"
  # Replace a blank/placeholder line if there is one, otherwise append.
  if grep -q '^AGENTOS_MCP_TOKEN=' server/.env; then
    sed -i "s|^AGENTOS_MCP_TOKEN=.*|AGENTOS_MCP_TOKEN=${TOKEN}|" server/.env
  else
    printf '\n# MCP endpoint for the JM Agentic-OS Harness. Absent = /mcp does not exist.\nAGENTOS_MCP_TOKEN=%s\n' "$TOKEN" >> server/.env
  fi
fi
grep -q '^AGENTOS_PORT=' server/.env || printf 'AGENTOS_PORT=8000\n' >> server/.env

if ! grep -q '^OPENROUTER_API_KEY=sk-or-' server/.env 2>/dev/null; then
  warn "OPENROUTER_API_KEY is not set in server/.env — the harness will start but"
  warn "every turn will fail with MISSING_CREDENTIAL. Get one at openrouter.ai/keys."
fi

# ------------------------------------------------------ 4. DSH settings
export DSH_HOME="${DSH_HOME:-$DIR/.dsh}"
mkdir -p "$DSH_HOME"
if [ -f "$DSH_HOME/settings.yaml" ]; then
  say "$DSH_HOME/settings.yaml exists, leaving it alone (delete it to re-seed)"
else
  say "seeding $DSH_HOME/settings.yaml with the OpenRouter route"
  cp deploy/harness/settings.yaml.example "$DSH_HOME/settings.yaml"
fi
# DSH_HOME holds sessions and a settings file with no secrets in it, but it is
# still machine state, not memory. Keep it out of git.
grep -qx '.dsh/' .gitignore 2>/dev/null || printf '\n# DSH runtime state for the harness (sessions, settings)\n.dsh/\n' >> .gitignore

# ------------------------------------------- 5. validate the composition
#
# --dump-config resolves the whole patch overlay without binding a port, so a
# malformed row is caught here rather than as a crash loop in systemd.
say "validating the cordis overlay"
if dsh web --patch "$DIR/deploy/harness/jm-agentic-os.cordis.yml" --dump-config >/tmp/dsh-config.txt 2>/tmp/dsh-config.err; then
  say "overlay composes cleanly ($(wc -l </tmp/dsh-config.txt) lines)"
  grep -q 'dsh-mcp-client' /tmp/dsh-config.txt \
    && say "the vault MCP row is present in the composed tree" \
    || warn "the MCP row is MISSING from the composed tree — check the overlay"
else
  warn "the overlay did NOT compose:"
  sed 's/^/    /' /tmp/dsh-config.err >&2
  die "fix deploy/harness/jm-agentic-os.cordis.yml before continuing"
fi

# ---------------------------------------------------------- 6. systemd
say "installing the jm-harness unit"
sed -e "s|__DIR__|$DIR|g" -e "s|__USER__|$USER|g" -e "s|__NODE_BIN__|$NODE_BIN|g" \
    deploy/systemd/jm-harness.service | sudo tee /etc/systemd/system/jm-harness.service >/dev/null
sudo systemctl daemon-reload

# The vault has to restart to pick up AGENTOS_MCP_TOKEN — /mcp is not registered
# at all in a process that started without it.
say "restarting agentos so /mcp is registered"
sudo systemctl restart agentos.service
sleep 4

TOKEN="$(grep '^AGENTOS_MCP_TOKEN=' server/.env | cut -d= -f2-)"
if curl -fsS --max-time 10 -X POST http://127.0.0.1:8000/mcp \
     -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
     -H 'accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"install","version":"1"}}}' \
     | grep -q 'agentos-vault'; then
  say "/mcp answered the handshake"
else
  warn "/mcp did not answer — journalctl -u agentos -n 40 --no-pager"
fi

say "starting the harness"
sudo systemctl enable -q --now jm-harness.service
sleep 6
if curl -fsS --max-time 8 -o /dev/null http://127.0.0.1:3080/; then
  say "harness is up on 127.0.0.1:3080"
else
  warn "harness did NOT come up — journalctl -u jm-harness -n 60 --no-pager"
fi

# ------------------------------------------------------- 7. optional HTTPS
if [ "$PUBLISH_HARNESS" = "1" ]; then
  command -v caddy >/dev/null || die "caddy is not installed; run deploy/provision.sh first"
  [ -n "${HARNESS_PASSWORD:-}" ] || die "set HARNESS_PASSWORD to publish the harness"
  IP="$(curl -fsS --max-time 5 https://checkip.amazonaws.com | tr -d '\n')"
  HHOST="${HARNESS_PUBLIC_HOST:-harness-${IP//./-}.sslip.io}"
  say "publishing the harness at https://$HHOST (password-protected)"
  HASH="$(caddy hash-password --plaintext "$HARNESS_PASSWORD")"

  # Rebuild the whole Caddyfile from both site definitions. provision.sh writes
  # this file from deploy/Caddyfile alone, so re-running provision.sh drops the
  # harness block — re-run this script afterwards to put it back.
  # Tell DSH that this public name is legitimately ours. Its Host/Origin fence
  # trusts loopback plus declared authorities only, so without this every /api
  # call from the proxied browser is a 403 and the UI reports transport failures
  # that look like the backend is down.
  say "declaring $HHOST to the /api trust fence"
  cat > deploy/harness/harness.env <<ENVEOF
# Generated by install-harness.sh. Not in git.
# Unbraced on purpose in the unit: systemd word-splits \$VAR into arguments.
DSH_EXTRA_ARGS=--trusted-host $HHOST
ENVEOF
  chmod 600 deploy/harness/harness.env

  VHOST="${AGENTOS_PUBLIC_HOST:-${NAME_PREFIX:-jm-agentic-os}-${IP//./-}.sslip.io}"
  {
    sed -e "s|__HOST__|$VHOST, ${IP//./-}.sslip.io|g" -e "s|__EMAIL__|admin@$VHOST|g" \
        deploy/Caddyfile
    printf '\n'
    sed -e "s|__HARNESS_HOST__|$HHOST|g" -e "s|__HARNESS_HASH__|$HASH|g" \
        deploy/Caddyfile.harness
  } | sudo tee /etc/caddy/Caddyfile >/dev/null

  if sudo caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1; then
    say "Caddyfile valid"
    sudo systemctl reload caddy || sudo systemctl restart caddy

    # harness.env was written after the unit started, so the trusted host is not
    # live yet. Restart, then prove the fence actually accepts the public name —
    # a 403 here is the difference between a working UI and one that loads and
    # then fails every request.
    say "restarting the harness so the trusted host takes effect"
    sudo systemctl restart jm-harness
    sleep 8
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 \
      -X POST "http://127.0.0.1:3080/api/llm.providers" \
      -H "Host: $HHOST" -H "Origin: https://$HHOST" \
      -H 'Content-Type: application/json' -d '{}' || echo 000)
    if [ "$code" = "403" ]; then
      warn "/api still 403 for $HHOST — the trust fence is rejecting it."
      warn "check: systemctl show jm-harness -p ExecStart | grep trusted-host"
    else
      say "/api accepts $HHOST (HTTP $code, anything but 403)"
    fi
    say "harness will be at https://$HHOST — user 'harness', the password you set"
  else
    warn "Caddyfile INVALID — not reloading. Check with: sudo caddy validate --config /etc/caddy/Caddyfile"
  fi
else
  cat <<EOF

The harness is loopback-only, which is the right default: the DSH web app has no
password of its own. Reach it from your laptop with an SSH tunnel:

    ssh -N -L 3080:127.0.0.1:3080 <user>@<this-host>
    open http://127.0.0.1:3080

To publish it over HTTPS with a password instead, read deploy/Caddyfile.harness,
then re-run:

    PUBLISH_HARNESS=1 HARNESS_PASSWORD='<a long passphrase>' bash deploy/install-harness.sh
EOF
fi

cat <<'EOF'

──────────────────────────────────────────────────────────────────────────
Verify it actually works, in this order:

1. The vault's tools are visible to the harness. In the harness UI, ask:
     "List your tools."
   Ten mcp__agentos__* tools should appear. If none do, the MCP client could
   not connect: journalctl -u jm-harness -n 60 --no-pager

2. Retrieval is wired, not just present:
     "What does my vault say about context rot? Cite the note ids."
   It must call mcp__agentos__search_vault and cite real ids.

3. Writing works and is attributed:
     "Log that the harness went live today."
   Then on the box:  git -C ~/Agentic-OS log --oneline -3
   You should see a `brain: log <date>` commit that you did not make by hand.

4. The jail holds. Ask it to:
     "Create a note called ../../etc/passwd"
   It must come back refused, and nothing outside brain/ may change.

Useful:
  journalctl -u jm-harness -f
  systemctl status jm-harness agentos
  dsh web --patch deploy/harness/jm-agentic-os.cordis.yml --dump-config | less
──────────────────────────────────────────────────────────────────────────
EOF
