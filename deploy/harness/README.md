# JM Agentic-OS Harness

The agent front end for this vault. Built on [DSH](https://github.com/deepseek-ai/deepseek-harness) — not affiliated with or endorsed by DeepSeek. The name deliberately avoids their trademark, which is what their brand guidance asks downstream projects to do.

The vault's own UI answers *"what do I know?"*. This answers *"do something with what I know."* It plans, researches against the vault, and writes back to it.

## How it fits together

```
browser ──► Caddy :443 ──► agentos :8000     the map, search, Ask, Gauntlet
                             (session cookie auth)

browser ──► SSH tunnel ──► jm-harness :3080   the agent UI  (no auth of its own)
                              │
                              │ MCP over Streamable HTTP, loopback,
                              │ Authorization: Bearer $AGENTOS_MCP_TOKEN
                              ▼
                           agentos :8000 /mcp
                              │
                              ▼
                           server/authoring.py   path jail + git commit per write
                              │
                              ▼
                           brain/*.md
```

The harness has **no filesystem access to `brain/`**. Its systemd unit could not write a note if it tried. Every change goes over MCP and through the jail, so there is exactly one code path that mutates the vault and one place to audit.

## The pieces

| File | What it does |
|---|---|
| `jm-agentic-os.cordis.yml` | DSH patch overlay: loopback bind, the persona, the model, and the vault MCP row |
| `settings.yaml.example` | The provider routes — OpenRouter, OrcaRouter, Gemini. Seeded to `$DSH_HOME/settings.yaml` |
| `../systemd/jm-harness.service` | The unit. Memory-capped, hardened, repo-only writes |
| `../Caddyfile.harness` | Optional HTTPS + password front door. Off by default |
| `../install-harness.sh` | Idempotent installer for all of the above |

## Install

`deploy/provision.sh` first, then:

```sh
bash deploy/install-harness.sh
```

It installs Node 22 via nvm (AL2023 ships 20; DSH needs ≥22.19), installs the prebuilt `@deepseek-ai/dsh` from npm, generates `AGENTOS_MCP_TOKEN`, validates the overlay with `--dump-config`, and starts the unit.

You need an OpenRouter key in `server/.env`:

```
OPENROUTER_API_KEY=sk-or-...
```

Optionally a second provider on an independent quota, which is the only thing that
helps once you have spent OpenRouter's daily free allowance (see *The model* below):

```
ORCAROUTER_API_KEY=sk-orca-...
```

Both are read by the unit through `EnvironmentFile=`, so a key added here needs
`sudo systemctl restart jm-harness` — unlike a model change, which is hot-reloaded.

## Reaching it

Loopback by default, and that is not laziness — **the DSH web app has no authentication**. No password, no token, no session. It assumes it is bound to localhost on a machine you control.

```sh
ssh -N -L 3080:127.0.0.1:3080 ec2-user@<host>
open http://127.0.0.1:3080
```

To publish it anyway, read `../Caddyfile.harness` and then:

```sh
PUBLISH_HARNESS=1 HARNESS_PASSWORD='a long passphrase' bash deploy/install-harness.sh
```

Use a different password from the vault UI's. They are different surfaces with different consequences.

## The model

Thirteen models across three routes. `agent-default-model` is
`nvidia/nemotron-3-ultra-550b-a55b:free`, and the interesting part is why a free
model is the default when the paid one is more reliable.

- **Tool support is the hard requirement, and the catalog lies about it.** A model
  that cannot call tools turns the harness into a chatbot that cannot see the
  vault. Several models advertising `tools` in OpenRouter's `supported_parameters`
  failed in practice, so every entry in `settings.yaml.example` was probed twice
  against a live key: once unforced, to see whether it *volunteers* a call rather
  than only obeying `tool_choice`, and once fed a completed tool result, to see
  whether it synthesises or re-calls in a loop. The rejects are listed in the file
  with their failure mode. Do not re-add one on the strength of its metadata.

- **The free ceiling is account-wide, which makes fallback chains misleading.**
  OpenRouter's free tier is 50 requests/day and 20/minute *across the account*,
  not per model — it rises to 1000/day after a one-time $10 credit purchase. One
  agent task burns 5–15 requests. So listing five free models buys real protection
  against any single one being throttled, and none at all against the daily cap:
  when the day's 50 are gone they all 429 together. This is the single most
  common way the harness looks broken when it is merely out of allowance.

- **A second vendor is the only fallback that beats a daily cap.** Hence the
  `orcarouter` route. Different account, different bucket. On a zero OrcaRouter
  balance exactly one model serves — `deepseek/deepseek-v4-flash-free`, verified
  to volunteer calls and round-trip results — while `orcarouter/auto` and the
  `fusion-*` ensembles are credit-gated and answer 402. The `orcarouter/free`
  auto-route works intermittently and returns no rate-limit headers, so there is
  nothing to plan against; it is listed second for that reason.

- **Paid escalation, when a free model visibly fumbles.** `z-ai/glm-5.3-flash` at
  $0.075/M prompt is pennies a month for a personal vault and it answers on the
  first try. `z-ai/glm-5.3` is ~19x that and worth it for architecture and long
  reasoning chains. Both are text+image on Flash, text-only on 5.3.

- **Switching is one click.** The Models page writes to `$DSH_HOME/settings.yaml`
  and needs no restart. Adding a *key*, on the other hand, means restarting the
  unit — the credential arrives through `EnvironmentFile=`.

- **`maxTokens` is 8192 everywhere, and that is a billing decision.** OpenRouter
  reserves `input_cost + maxTokens × output_price` *before* running the request.
  At 32768 the reservation exceeded a small balance and every turn failed with
  `402 — requires more credits, or fewer max_tokens`, while the turn itself would
  have cost a third of that. A ceiling you never reach is still one you pay to
  reserve. It matters on reasoning models for a second reason: reasoning tokens
  come out of the same budget, so too small a cap yields an empty `content` and
  `finish_reason: length`, which reads as a dead model.

## What the agent can and cannot do

**Can:** search, read any note (including the kernel and skills), create, edit, append, delete notes in `brain/`, append to the journal, read git history.

**Cannot:**

- Write outside `brain/`. Paths are sanitised, resolved through symlinks, then proved to be inside the vault.
- Touch `AGENTS.md`, `config/`, `server/` or `bin/`. Readable, unwritable. An agent that can edit its own instructions has no stable behaviour to reason about.
- Rewrite or delete the journal. Append-only: it is the record of what happened, including its own mistakes.
- Delete `brain/STATE.md` or `brain/lessons.md`.
- Write more than 60 times in one session, or a note over 512 KiB.
- Run shell commands against the vault. There is no such tool.

Every write is its own git commit (`brain: add …`, `brain: edit …`), staged by explicit path so it never sweeps up unrelated work. `git revert` is the undo; `note_history` shows the agent its own trail.

## Prompt injection

`brain/raw/` is, by design, text fetched from the internet — arXiv abstracts, HN titles, whole pages pulled by `os research --fetch`. An agent that reads a poisoned capture while holding `delete_note` is the actual threat, not a hypothetical one.

What is done about it:

- Content from `raw/` is returned inside an explicit `[UNTRUSTED DATA]` envelope naming its source, in both `read_note` and search excerpts.
- The envelope states that instructions inside it must not be followed, and the persona repeats it as an absolute rule.
- Damage is bounded by everything in the list above: no path escape, no self-modification, append-only journal, write caps, and a git commit per change.

None of this makes injection impossible. All of it makes the outcome bounded, visible and revertable. If you want a stronger guarantee, the honest one is to not give a web-exposed agent write access at all — drop the write tools from `TOOLS` in `server/mcp.py` and it becomes read-only.

## Commits pile up on the box — decide what happens to them

Every write is a local commit. That is the provenance story, and on an always-on box it has a consequence worth deciding deliberately rather than discovering:

`agentos-sync.service` runs `git pull --ff-only`. A box that cannot push accumulates harness commits, diverges from `origin`, and from then on **every sync fails** — quietly, because the timer's failure is not visible in the UI. The vault keeps working; it just stops pulling and stops reindexing on schedule.

A default EC2 checkout cloned over HTTPS has no push credential, so this is the likely state. Check:

```sh
git -C ~/Agentic-OS push --dry-run origin HEAD
# fatal: could not read Username for 'https://github.com'  <- diverges silently
```

Two honest resolutions. Pick one:

**Let the box push** — the vault genuinely becomes durable, and `bin/os save` starts working too (it has the same dependency).

```sh
# a fine-grained PAT with Contents:write on this repo only
git -C ~/Agentic-OS remote set-url origin \
  https://<user>:<token>@github.com/<user>/<repo>.git
chmod 600 ~/Agentic-OS/.git/config     # the token is now in there
```

**Or keep the box read-only against `origin`** and accept that harness writes live only on the box until you collect them by hand. If you choose this, make the sync tolerate divergence, or it will keep failing:

```sh
sudo systemctl edit agentos-sync.service
# [Service]
# ExecStart=
# ExecStart=/usr/bin/git pull --rebase --autostash --quiet
```

There is no third option where commits accumulate and `--ff-only` keeps working. Choosing nothing is choosing the second one, with a broken timer.

## Troubleshooting

| Symptom | Cause |
|---|---|
| No `mcp__agentos__*` tools | MCP client could not connect. `journalctl -u jm-harness -n 60`. Check `AGENTOS_MCP_TOKEN` is in `server/.env` **and** that `agentos` was restarted after it was added — `/mcp` is not registered in a process that started without a token. |
| `MISSING_CREDENTIAL` | The key named by that route's `apiKeyEnv` is absent from `server/.env` — `OPENROUTER_API_KEY`, `ORCAROUTER_API_KEY`, or `GEMINI_API_KEY` in `deploy/harness/harness.env`. Adding it needs a `systemctl restart jm-harness`; the unit reads credentials via `EnvironmentFile=`, so a hot reload will not pick one up. |
| `UNKNOWN_MODEL` | The route in `$DSH_HOME/settings.yaml` does not list the model in `agent-default-model`. Remember `$DSH_HOME` is `~/.dsh-harness` here, not `~/.dsh`. |
| Harness OOM-killed | Both units oversubscribe a 1 GB box. Lower `MemoryHigh` in `agentos.service` to 420M. |
| Writes succeed, search misses them | Reindex failed after the write. The tool result says so in `searchable`. Check `journalctl -u agentos`. |
| Harness vanished after re-provisioning | `provision.sh` rewrites `/etc/caddy/Caddyfile` from `deploy/Caddyfile` alone. Re-run `install-harness.sh`. |
| `status=127` / `env: 'node': No such file or directory` | The unit's `PATH` has no nvm directory. Fixed in the shipped unit via `Environment=PATH=`; if you hand-edited it, put the node bin dir back. |
| Sync timer stopped, vault otherwise fine | Harness commits diverged the box from `origin` and `git pull --ff-only` now fails. See the section above. |
| 429 on every turn, on every free model at once | The account's daily free allowance is spent, not the model's. OpenRouter's free cap is 50 requests/day and 20/minute *account-wide*, so switching between `:free` models changes nothing — they share one bucket. Either switch to a paid route (`glm-5.3-flash`), switch to the `orcarouter` route for a separate quota, or buy $10 of OpenRouter credit once to lift the cap to 1000/day. `curl -H "Authorization: Bearer $OPENROUTER_API_KEY" https://openrouter.ai/api/v1/key` shows whether you are still on the free tier. |
| 429 on one free model, others fine | That model is throttled upstream. This is what the free fallback list is for; pick another. `z-ai/glm-5.2:free` fails this way often enough that it is not a sensible primary. |
| 402 `insufficient_quota` on an OrcaRouter model | That model is credit-gated and the balance is $0. Only `deepseek/deepseek-v4-flash-free` serves on an empty balance; `orcarouter/auto` and `fusion-*` need credit. Check with `curl -H "Authorization: Bearer $ORCAROUTER_API_KEY" https://api.orcarouter.ai/v1/balance`. |
| 402 `free_quota_exhausted` on `orcarouter/free` | A rolling window, not a daily reset — it recovers on its own within minutes, and OrcaRouter sends no rate-limit headers to time it by. Use `deepseek/deepseek-v4-flash-free` directly if you need predictability. |
| Empty reply, `finish_reason: length` | A reasoning model spent the whole output budget thinking. Reasoning tokens draw on `maxTokens`. Raise it; do not go below ~1024 on these routes. |
