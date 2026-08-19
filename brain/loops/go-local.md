---
loop: go-local
status: open
check: kirocrew doctor
created: 2026-08-19
---

# Goal
Move AgentOS from a Kiro Web sandbox onto the user's own machine, where an agentic
OS can actually be persistent: a daemon that survives logout, a scheduler, enforced
session hooks, and a dashboard. Runtime is Kiro Crew driving `kiro-cli` over ACP;
the `brain/` vault stays the git-versioned, Obsidian-readable source of truth.

# Done when
`kirocrew doctor` reports `kiro-cli` found **and logged in**, the gateway runs as a
service, a cron job advances a loop unattended, and the `brain/` vault is ingested
into Crew's Knowledge Library while still pushing to git.

# Steps
- [ ] install kiro-cli on the PC and `kiro-cli login` (this is what gives Crew its model access)
- [ ] `curl -fsSL https://download.crew.kiro.dev/cli.sh | sh` — needs `openssl` present for signature verification
- [ ] `kirocrew setup` from the Agentic-OS clone so project dir is set, then `kirocrew doctor` until clean
- [ ] `kirocrew gateway`, open http://localhost:5476, confirm the dashboard loads
- [ ] `kirocrew service install` so it survives logout and restarts on crash
- [ ] install the Kiro CLI `SessionStart` hook so boot is *enforced*, not merely instructed
- [ ] `kirocrew knowledge` — ingest `brain/` as a local folder, verify search finds a note
- [ ] `kirocrew cron` — schedule `bin/os save` nightly so the vault pushes itself
- [ ] `kirocrew cron` — schedule one `bin/os loop next` advance, confirm unattended progress
- [ ] decide what `brain/lessons.md` keeps vs. what moves to `kirocrew learn add`
- [ ] `kirocrew snapshot` once, confirm restore works, then delete whatever AgentOS code Crew made redundant

# Notes
- Verified in the Kiro Web sandbox: Crew 0.2.0 installs and `doctor` runs. `doctor`
  showed `provider: acp`, `model: auto`, `kiro-cli: not found` — the sandbox has no
  signed-in CLI, which is exactly why this loop has to run on the PC.
- The installer aborts with "openssl is required to verify the signed manifest" if
  openssl is missing. Install it first rather than skipping verification.
- Windows: native support via CPython 3.12 venv and `python -m kiro_crew gateway`.
  The OS-level sandbox is Linux/macOS only; everything else works.
- 24/7 on a server or NAS instead: `ghcr.io/kirodotdev/kirocrew:stable` in Docker,
  or `kirocrew cloud` for your own EC2. A laptop that sleeps is a poor host for a
  scheduler.
- Do not delete anything from `brain/` until the last step. Crew's memory is
  better at recall; the vault is better at being auditable. Deleting early trades a
  durable artifact for a database you cannot diff.
