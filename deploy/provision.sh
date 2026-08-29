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

# ---------------------------------------------------------------- 8. TLS
# Real certificate, no domain purchase, no interactive login: <dashed-ip>.sslip.io
# resolves to this host, and Let's Encrypt will issue for it over HTTP-01.
# Requires ports 80 and 443 open in the security group.
if [ "${TLS:-caddy}" = "caddy" ]; then
  IP="$(curl -fsS --max-time 5 https://checkip.amazonaws.com | tr -d '\n' || true)"
  HOST="${AGENTOS_PUBLIC_HOST:-${IP//./-}.sslip.io}"

  if [ -z "$IP" ]; then
    say "could not determine the public IP — skipping TLS. Set AGENTOS_PUBLIC_HOST and re-run."
  else
    say "TLS for https://$HOST"
    if ! command -v caddy >/dev/null; then
      sudo dnf -y -q install 'dnf-command(copr)' >/dev/null 2>&1 || true
      sudo dnf -y -q copr enable @caddy/caddy epel-9-x86_64 >/dev/null 2>&1 || true
      sudo dnf -y -q install caddy >/dev/null 2>&1 || true
    fi
    if command -v caddy >/dev/null; then
      sed -e "s|__HOST__|$HOST|g" -e "s|__EMAIL__|admin@$HOST|g" \
        deploy/Caddyfile | sudo tee /etc/caddy/Caddyfile >/dev/null
      sudo caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1 \
        && say "Caddyfile valid" || say "Caddyfile INVALID — check it before trusting TLS"
      sudo systemctl enable -q --now caddy
      sudo systemctl restart caddy

      say "waiting for certificate issuance (needs :80 and :443 open)"
      for _ in $(seq 1 45); do
        L=$(sudo journalctl -u caddy --since '-4min' --no-pager 2>/dev/null || true)
        case "$L" in
          *"certificate obtained successfully"*) say "certificate obtained"; break ;;
          *"could not get certificate"*|*"too many failed"*)
            say "issuance FAILED — is :80 open? journalctl -u caddy"; break ;;
        esac
        sleep 3
      done

      sed -i "s|^AGENTOS_BASE_URL=.*|AGENTOS_BASE_URL=https://$HOST|" server/.env
      sudo systemctl restart agentos
      sleep 4
      if curl -fsS --max-time 10 "https://$HOST/healthz" >/dev/null 2>&1; then
        say "HTTPS live: https://$HOST"
      else
        say "HTTPS not answering yet — journalctl -u caddy -n 30"
      fi
    else
      say "Caddy unavailable — the app is still loopback-only, so nothing is exposed."
    fi
  fi
fi

# Tailscale remains an alternative to Caddy: set TLS=tailscale to skip the above.
if [ "${TLS:-caddy}" = "tailscale" ] && ! command -v tailscale >/dev/null; then
  say "installing Tailscale"
  sudo dnf -y -q config-manager --add-repo \
    https://pkgs.tailscale.com/stable/amazon-linux/2/tailscale.repo 2>/dev/null || true
  sudo dnf -y -q install tailscale || say "install manually: https://tailscale.com/download/linux"
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

3. HTTPS is already set up by this script via Caddy + Let's Encrypt on
   <dashed-ip>.sslip.io. Verify it:

     curl -fsS https://$(curl -fsS https://checkip.amazonaws.com | tr . -).sslip.io/healthz

   If you later get your own domain, point it at this host and re-run with:
     AGENTOS_PUBLIC_HOST=notes.example.com bash deploy/provision.sh

4. Restart after any .env edit:

     sudo systemctl restart agentos

   Then sign in. Confirm a WRONG password is rejected and that repeated
   failures lock you out — that negative test is what proves auth works.

Useful:
  journalctl -u agentos -f            # app logs, including failed logins
  systemctl list-timers agentos-sync  # when the next pull+reindex runs
  .venv/bin/python -m server.tools.eval_retrieval
──────────────────────────────────────────────────────────────────────────
EOF
