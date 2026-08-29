#!/usr/bin/env bash
# Provision the always-on box. Idempotent — safe to re-run after a git pull.
#
#   bash provision.sh
#
# Installs: swap, python + venv, the app, systemd units, Tailscale. Binds to
# loopback only and sets no password, so a freshly provisioned box admits nobody
# until you run setpass — an app that ships reachable-and-open is worse than one
# that ships closed.
set -euo pipefail

REPO="${REPO:-https://github.com/jmbilbao25/Agentic-OS.git}"
DIR="${DIR:-$HOME/Agentic-OS}"
BRANCH="${BRANCH:-main}"
SWAP_MB="${SWAP_MB:-2048}"

say() { printf '\n\033[1;33m==>\033[0m %s\n' "$*"; }

# ---------------------------------------------------------------- 1. swap
# 1 GB of RAM is enough to serve and to search, but not to embed a few hundred
# chunks at once. Swap turns a hard OOM during reindex into a slow reindex.
if ! swapon --show | grep -q /swapfile; then
  say "creating ${SWAP_MB}MB swap"
  sudo dd if=/dev/zero of=/swapfile bs=1M count="$SWAP_MB" status=none
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null
  sudo swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  # a small vault does not want aggressive swapping, only a safety net
  echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-agentos.conf >/dev/null
  sudo sysctl -q -p /etc/sysctl.d/99-agentos.conf
else
  say "swap already present"
fi

# ---------------------------------------------------------------- 2. packages
say "installing packages"
sudo dnf -y -q install git python3.11 python3.11-pip gcc sqlite ripgrep 2>/dev/null \
  || sudo dnf -y -q install git python3 python3-pip gcc sqlite
PY=$(command -v python3.11 || command -v python3)
say "python: $($PY -V)"

# ---------------------------------------------------------------- 3. the repo
if [ -d "$DIR/.git" ]; then
  say "updating $DIR"
  git -C "$DIR" fetch -q origin "$BRANCH" && git -C "$DIR" checkout -q "$BRANCH" \
    && git -C "$DIR" pull -q --ff-only
else
  say "cloning into $DIR"
  git clone -q --branch "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR"

# ---------------------------------------------------------------- 4. venv
say "creating venv + installing dependencies (a few minutes on a t3.micro)"
[ -d .venv ] || "$PY" -m venv .venv
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q -r server/requirements.txt

# ---------------------------------------------------------------- 5. config
if [ ! -f server/.env ]; then
  say "writing server/.env from the example — YOU MUST EDIT IT"
  cp server/.env.example server/.env
  SECRET=$(openssl rand -hex 32)
  sed -i "s|^SESSION_SECRET=.*|SESSION_SECRET=${SECRET}|" server/.env
  chmod 600 server/.env
else
  say "server/.env already exists, leaving it alone"
fi

# ---------------------------------------------------------------- 6. index
say "building the search index"
./.venv/bin/python -m server.index --full || say "index build failed — check the log above"

# ---------------------------------------------------------------- 7. systemd
say "installing systemd units"
for unit in agentos.service agentos-sync.service agentos-sync.timer; do
  sed -e "s|__DIR__|$DIR|g" -e "s|__USER__|$USER|g" \
      "deploy/systemd/$unit" | sudo tee "/etc/systemd/system/$unit" >/dev/null
done
sudo systemctl daemon-reload
sudo systemctl enable -q --now agentos.service
sudo systemctl enable -q --now agentos-sync.timer

sleep 3
if curl -fsS --max-time 5 http://127.0.0.1:8000/healthz >/dev/null; then
  say "app is up on 127.0.0.1:8000"
else
  say "app did NOT come up — journalctl -u agentos -n 40 --no-pager"
fi

# ---------------------------------------------------------------- 8. tailscale
if ! command -v tailscale >/dev/null; then
  say "installing Tailscale"
  sudo dnf -y -q config-manager --add-repo \
    https://pkgs.tailscale.com/stable/amazon-linux/2/tailscale.repo 2>/dev/null || true
  sudo dnf -y -q install tailscale || say "install Tailscale manually: https://tailscale.com/download/linux"
  sudo systemctl enable -q --now tailscaled || true
fi

cat <<'EOF'

──────────────────────────────────────────────────────────────────────────
Remaining steps.

1. Set the login password (required — until you do, the app admits nobody):

     cd ~/Agentic-OS
     .venv/bin/python -m server.tools.setpass
     # or, to have one invented for you:
     .venv/bin/python -m server.tools.setpass --generate

2. Add your inference key to ~/Agentic-OS/server/.env :

     OPENROUTER_API_KEY=sk-or-...        # free tier: openrouter.ai/keys

3. Publish over real HTTPS. Do NOT skip this — the password is sent on every
   request, and over plain HTTP it travels in the clear:

     sudo tailscale up
     sudo tailscale funnel --bg 8000
     tailscale funnel status             # note the https://<host>.ts.net URL

   Then set AGENTOS_BASE_URL=https://<host>.ts.net in server/.env

4. Restart and verify:

     sudo systemctl restart agentos
     curl -fsS https://<host>.ts.net/healthz

   Then sign in. Confirm a WRONG password is rejected and that repeated
   failures lock you out — that negative test is what proves auth works.

Useful:
  journalctl -u agentos -f            # app logs, including failed logins
  systemctl list-timers agentos-sync  # when the next pull+reindex runs
  .venv/bin/python -m server.tools.eval_retrieval
──────────────────────────────────────────────────────────────────────────
EOF
