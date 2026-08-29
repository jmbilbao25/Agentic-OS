---
loop: deploy-always-on
status: open
check: curl -fsS https://$AGENTOS_HOST/healthz
created: 2026-08-19
updated: 2026-08-29
---

# Goal
Move AgentOS off ephemeral sandboxes and onto an always-on machine the user controls,
where an agentic OS can actually be persistent: a daemon that survives reboot, a
scheduler that fires with the laptop shut, hybrid search over the whole vault, and a
web UI reachable from anywhere behind a login. Host is an EC2 `t3.micro` inside the
credit-based free tier. The `brain/` vault stays the git-versioned, Obsidian-readable
source of truth; everything on the box is a disposable index in front of it.

# Done when
`https://<host>/healthz` returns 200 over real TLS; the password admits exactly one
user, wrong ones are rejected and repeated failures lock out; the orbit UI renders the live vault; a RAG answer
cites real note paths; a `systemd` timer has pulled from git and reindexed unattended
at least once; and the whole thing comes back by itself after `sudo reboot`.

# Steps
- [ ] launch the instance — `deploy/launch-ec2.sh` from CloudShell (t3.micro, 30 GB gp3, SG allows only 22 in)
- [ ] `deploy/provision.sh` on the box — swap, python venv, deps, clone, systemd units
- [ ] set the password with `python -m server.tools.setpass`, put `OPENROUTER_API_KEY` in `server/.env`
- [ ] `tailscale up` then `tailscale funnel 8000` — confirm the public HTTPS hostname resolves
- [ ] set `AGENTOS_BASE_URL` to the funnel hostname, restart, sign in over HTTPS
- [ ] confirm a wrong password is rejected and repeated failures return 429 (the security test, not a formality)
- [ ] `agentos-index` once — confirm FTS5 + vector row counts match the file count
- [ ] load the orbit UI in a browser, search with `/`, open a note, confirm the preview renders
- [ ] ask one RAG question, verify every citation points at a file that actually exists
- [ ] enable the `agentos-sync.timer`, wait for one unattended run, confirm git pull + reindex in the log
- [ ] `sudo reboot`, then re-run the `check` command with no manual intervention
- [ ] set a billing alarm at $20/mo and record the real observed cost in Notes

# Notes
- Inference stays **remote** on purpose. A box that can hold a useful model costs ~10x a
  box that can hold an index, and is worse. Only the embedding model is local
  (quantised MiniLM, CPU, ~90 MB). See [[Local Runtime Closes The Gaps]].
- Free tier here is **credit-based** ($100-class credit with an expiry), not the old
  always-free instance-hours. So cost is credit burn: t3.micro + 30 GB gp3 ≈ $10/mo.
  A t3.small doubles compute and halves the runway — not worth it for an index.
- 1 GB RAM is the real constraint. Hence SQLite FTS5 + sqlite-vec (no daemon) rather
  than Postgres + pgvector, and ONNX int8 rather than PyTorch. 2 GB swap for reindex
  headroom.
- Tailscale Funnel gives a real Let's Encrypt cert on a stable `*.ts.net` hostname with
  no domain purchase and no port 443 exposed to the world. The alternative (DuckDNS +
  Caddy DNS-01) also works and is documented in `deploy/README.md`.
- Security rule: the SG opens **22 only**. The app is never bound to a public interface
  directly — Funnel terminates TLS and forwards to localhost. A password sent over
  plain HTTP is sent in the clear on every request: not protected, decorated.
- Do not delete anything from `brain/` because the index can answer faster. The index is
  a cache; deleting the markdown trades an auditable artifact for a database you cannot
  diff. See [[Git Is The Disk]].
