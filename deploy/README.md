# Deploy — the always-on box

The vault lives in git. This puts a **reader** of that vault on a machine with an
uptime, so search, the orbit UI, and scheduled reindexing keep working when your
laptop is shut. Nothing here authors memory; writing is still `bin/os`.

## What you get

| | |
|---|---|
| Host | EC2 `t3.micro`, 30 GB gp3, Amazon Linux 2023 |
| Cost | ~$10/month (≈$7.60 compute + ≈$2.40 disk) |
| TLS | Caddy + Let's Encrypt on `<dashed-ip>.sslip.io` — real certificate, **no domain purchase**, fully automatic |
| Inbound ports | 22, 80, 443. The app itself binds to `127.0.0.1` only — Caddy is the sole public listener. |
| Auth | single username + password, PBKDF2 hashed, per-IP lockout |
| Routines | `systemd` timer: `git pull` + incremental reindex every 15 min |
| Recovery | `systemd` restarts on crash and on reboot |

## Two commands

```bash
# 1. from AWS CloudShell (it already has your credentials)
bash deploy/launch-ec2.sh

# 2. on the box
scp -i agentos-key.pem deploy/provision.sh ec2-user@<ip>:
ssh -i agentos-key.pem ec2-user@<ip> 'bash provision.sh'
```

`provision.sh` is idempotent — re-run it after any `git pull`.

`provision.sh` does the TLS too: it derives `<dashed-ip>.sslip.io`, installs
Caddy, and waits for Let's Encrypt to issue. The only thing left for you is the
password (`python -m server.tools.setpass`) and an inference key in `server/.env`.

## Why these choices

**Why not run the model on the box?** A `t3.micro` has 1 GB of RAM. It holds an
index and a quantised embedding model comfortably; it cannot hold a useful LLM. An
instance that could costs roughly ten times as much and still answers worse than a
free-tier hosted model. So embeddings are local and inference is remote behind one
env var — see `brain/wiki/Model Access Is Not Transferable.md`.

**Why `sslip.io`?** It resolves `13-218-239-165.sslip.io` to `13.218.239.165`
with no DNS account, no token, and no interactive login, and Let's Encrypt issues
for it over HTTP-01. That is a genuinely trusted certificate for zero setup —
verified end to end here (`ssl_verify_result=0`). Point your own domain at the box
and re-run with `AGENTOS_PUBLIC_HOST=` when you have one; nothing else changes.

Tailscale Funnel is still supported (`TLS=tailscale`) and is the better choice if
you would rather not open 80/443 at all — it just needs an interactive login.

**Why SQLite and not Postgres?** No daemon, no second process competing for 1 GB,
and the index is one file you can delete as a repair step. See
`brain/wiki/Grep Beats Embeddings Here.md`.

**Why loopback-only binding?** A password sent over plain HTTP is sent in the
clear on every single request — that is not protected, it is decorated. Funnel
terminates TLS and forwards to `127.0.0.1`, so there is no unencrypted public
surface at any point. This matters more with a password than it did with OAuth.

## Operating it

```bash
journalctl -u agentos -f                  # app logs
systemctl list-timers agentos-sync        # next scheduled pull + reindex
systemctl restart agentos                 # after editing server/.env
sudo systemctl start agentos-sync         # force a pull + reindex now

~/Agentic-OS/.venv/bin/python -m server.index --full        # rebuild index
~/Agentic-OS/.venv/bin/python -m server.tools.eval_retrieval # score retrieval
```

**Cost control.** Stop the instance when you don't need it (disk still bills, and
the Funnel hostname survives):

```bash
aws ec2 stop-instances  --instance-ids <id>
aws ec2 start-instances --instance-ids <id>
```

Set the billing alarm. `launch-ec2.sh` prints the command; run it.

## Alternative: DuckDNS + Caddy

If you want your own hostname instead of Tailscale:

1. Sign in at [duckdns.org](https://www.duckdns.org) with Google, claim a
   subdomain, copy the token.
2. Open `443` and `80` in the security group.
3. Install Caddy with the DuckDNS DNS plugin and use:

```caddyfile
your-name.duckdns.org {
    tls { dns duckdns {env.DUCKDNS_TOKEN} }
    reverse_proxy 127.0.0.1:8000
}
```

DNS-01 means you never expose port 80 for the challenge. Set
`AGENTOS_BASE_URL` to the DuckDNS hostname and restart.

Free options that do **not** work here: Freenom is defunct; `nip.io` and
`sslip.io` hit Let's Encrypt rate limits.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Login page says no password is set | run `python -m server.tools.setpass`, then restart |
| 429 / "too many attempts" | per-IP lockout: 8 tries, 15 min. Restart the service to clear it |
| Logged out after changing the password | by design — sessions are bound to the credential |
| Signed out after every restart | `SESSION_SECRET` is empty in `server/.env` |
| Status pill says `keyword`, not `hybrid` | `sqlite-vec` or `fastembed` missing: `.venv/bin/pip install -r server/requirements.txt`, then reindex |
| Reindex killed | swap missing. Re-run `provision.sh`, or `--full` less often |
| Ask returns `[no inference key configured]` | set `OPENROUTER_API_KEY` |
| Vault never updates | check `systemctl list-timers`; a non-fast-forward history stops the pull on purpose |
