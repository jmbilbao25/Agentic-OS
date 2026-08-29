#!/usr/bin/env bash
# Local dev server. Reads AGENTOS_HOST / AGENTOS_PORT from server/.env.
# Production uses the systemd unit in deploy/, not this.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
exec python3 -m uvicorn server.app:app \
  --host "${AGENTOS_HOST:-127.0.0.1}" \
  --port "${AGENTOS_PORT:-8000}" \
  --log-level info
