# Deploy — the always-on box

The vault lives in git. This puts a **reader** of that vault on a machine with an
uptime, so search, the orbit UI, and scheduled reindexing keep working when your
laptop is shut. Nothing here authors memory; writing is still `bin/os`.

## What you get

| | |
|---|---|
| Host | EC2 `t3.micro`, 30 GB gp3, Amazon Linux 2023 |
| Cost | ~$10/month (≈$7.60 compute + ≈$2.40 disk) |
| TLS | Tailscale Funnel — real certificate, stable hostname, **no domain purchase** |
| Inbound ports | **22 only**, from your IP. The web app is never publicly bound. |
| Auth | one username + one PBKDF2-hashed password, with per-address lockout |
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

Then finish the three things a script cannot do for you: `tailscale up` +
`tailscale funnel --bg 8000`, run `python -m server.passwd`, and paste the
credentials into `server/.env`. The script prints the exact steps when it
finishes.

## Why these choices

**Why not run the model on the box?** A `t3.micro` has 1 GB of RAM. It holds an
index and a quantised embedding model comfortably; it cannot hold a useful LLM. An
instance that could costs roughly ten times as much and still answers worse than a
free-tier hosted model. So embeddings are local and inference is remote behind one
env var — see `brain/wiki/Model Access Is Not Transferable.md`.

**Why Tailscale Funnel over Caddy + a domain?** Funnel gives a real Let's Encrypt
certificate on a stable `*.ts.net` hostname without buying a domain and without
opening 443 to the internet. If you would rather own the hostname, the DuckDNS
alternative is below — the app is identical either way.

**Why SQLite and not Postgres?** No daemon, no second process competing for 1 GB,
and the index is one file you can delete as a repair step. See
`brain/wiki/Grep Beats Embeddings Here.md`.

**Why loopback-only binding?** A password-protected app served over plain
HTTP on a public IP, is decorated rather than protected. Funnel terminates TLS and
forwards to `127.0.0.1`, so there is no unencrypted public surface at any point.

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
`sslip.io` hit Let's Encrypt rate limits and are unreliable as published
targets.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Sign-in page says "no credentials set" | `AGENTOS_USER` / `AGENTOS_PASSWORD_HASH` are empty. Run `.venv/bin/python -m server.passwd`. An empty credential config denies everyone on purpose |
| `429 Too many attempts` | the per-address lockout engaged. It clears itself after `LOGIN_LOCKOUT_SECONDS` (default 15 min), and a correct password does not bypass it |
| Forgot the password | there is no reset by design. Re-run `python -m server.passwd`, replace the hash in `server/.env`, restart |
| Signed out after every restart | `SESSION_SECRET` is empty in `server/.env` |
| Status pill says `keyword`, not `hybrid` | `sqlite-vec` or `fastembed` missing: `.venv/bin/pip install -r server/requirements.txt`, then reindex |
| Reindex killed | swap missing. Re-run `provision.sh`, or `--full` less often |
| Ask says there is no inference key | set `OPENROUTER_API_KEY` in `server/.env`, or paste one into Settings in the UI |
| Ask returns a 429 from the provider | free-tier models rate-limit routinely. Set `LLM_FALLBACK_MODELS` |
| Search cannot find a note you can see on the map | run `python -m server.tools.eval_retrieval`, and add the query as a probe |
| Vault never updates | check `systemctl list-timers`; a non-fast-forward history stops the pull on purpose |
