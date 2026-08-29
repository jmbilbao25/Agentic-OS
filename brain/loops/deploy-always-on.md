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
- [x] launch the instance (t3.micro, 30 GB gp3, AL2023)
- [x] provision the box — swap, python 3.11 venv, deps, clone, systemd units
- [x] set the login password with `python -m server.tools.setpass`
- [x] TLS: Caddy + Let's Encrypt on `<dashed-ip>.sslip.io`, certificate obtained
- [x] set `AGENTOS_BASE_URL` to the https host, restart, sign in over HTTPS from outside
- [x] confirm a wrong password is rejected and repeated failures return 429 (the security test, not a formality)
- [x] index built on the box — confirm FTS5 + vector row counts match the file count
- [x] load the orbit UI in a browser, search with `/`, open a note, confirm the preview renders
- [x] `sudo reboot`, then confirm it comes back with no manual intervention
- [x] `agentos-sync.timer` enabled — confirm an unattended git pull + reindex
- [x] put `OPENROUTER_API_KEY` in `server/.env` (openrouter.ai/keys) and restart
- [x] ask one RAG question, verify every citation points at a file that actually exists
- [ ] rotate the EC2 keypair and narrow the SSH source from 0.0.0.0/0 to one IP
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

## 2026-08-29 — deployed and verified

Live at `https://13-218-239-165.sslip.io`. Measured on the box, not assumed:

- 913 MB RAM, 2 vCPU, 30 GB disk. App uses **247 MB against a 700 MB systemd cap**;
  host sits at ~354 MB with 0 MB of swap touched. The 2 GB swap file was still worth
  creating — the `onnxruntime` install is the peak, not the steady state.
- Index: 15 docs / 63 chunks / **63 vectors**, hybrid. Full build took 42 s including
  the first-run model download.
- Reboot test: back in **~30 s** with `agentos`, `caddy`, and the sync timer all
  active, nothing started by hand.
- TLS: real Let's Encrypt certificate, `ssl_verify_result=0` verified from outside.
  `sslip.io` needs no DNS account and no token, which makes it strictly less work
  than DuckDNS *and* than Tailscale Funnel for a box that already has 80/443 open.
- Port 8000 confirmed **not** reachable publicly; Caddy is the only listener.

Two bugs the deploy found that local testing had not:

1. `meta.mode` was derived from how many chunks *that run* embedded, so the first
   incremental run by the sync timer relabelled a fully hybrid index as
   "keyword-only". The status pill was lying. Mode now describes the index.
2. Caddy's packaged systemd unit is sandboxed and cannot write `/var/log/caddy`, so
   a `log { output file … }` block makes the whole config fail to load. Journald only.

Lesson worth keeping: **a deploy is a test.** Both bugs were invisible in the
sandbox and immediate on the box.
