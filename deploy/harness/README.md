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

The vault is **read-only to the harness process**, enforced by the unit's sandbox rather than by policy: `ReadWritePaths` lists the agent's scratch workspace and DSH's own state, and nothing else on the box. The only route that can change `brain/` is MCP — over loopback, through the jail, into a git commit.

That distinction matters, because DSH composes its own `bash`, `fs` and `str-replace-editor` tools. They reach the filesystem directly and know nothing about `server/authoring.py`. The first version of this unit used the repo as its working directory *and* put it in `ReadWritePaths`, so those tools could edit `brain/` and append to `AGENTS.md` straight past the jail — verified with a probe, not theorised. The jail was guarding a door that was no longer the only one.

`server/.env` is in `InaccessiblePaths`, so an agent with a shell cannot read your OpenRouter key, login hash or session secret out of it. `install-harness.sh` re-checks all of this on every run and warns loudly if a write succeeds.

**What is still reachable, honestly:** the agent runs with `OPENROUTER_API_KEY` and `AGENTOS_MCP_TOKEN` in its environment, because the provider route and the MCP header resolve them from there. Anything with a shell can read its own `/proc/self/environ`. The MCP token is not an escalation — it grants exactly the tools the agent already has — but the OpenRouter key is a real credential. If that is unacceptable, drop DSH's shell and filesystem tools; the vault tools do not depend on them:

```yaml
# add to jm-agentic-os.cordis.yml
- id: tool-bash
  config: { enabled: false }
- id: tool-fs
  config: { enabled: false }
```

## The pieces

| File | What it does |
|---|---|
| `jm-agentic-os.cordis.yml` | DSH patch overlay: loopback bind, the persona, the model, and the vault MCP row |
| `settings.yaml.example` | The OpenRouter provider route. Seeded to `$DSH_HOME/settings.yaml` |
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

`z-ai/glm-5.3-flash` by default. Three things to know:

- **The free tier is not the default, on purpose.** `z-ai/glm-5.2:free` is genuinely free and supports tools, and measured against a live key it returns `429 — temporarily rate-limited upstream` often enough to fail the *first* message of a session. A harness whose opening turn errors is indistinguishable from a broken install. Flash is $0.075 per million prompt tokens — pennies a month for a personal vault — and it answers.
- **Switching is one click.** The Models page writes your choice to `$DSH_HOME/settings.yaml` and needs no restart. Pick `GLM 5.2 (free)` if you would rather have the retries than the invoice.
- **Tool support is the hard requirement.** A model without it turns the harness into a chatbot that cannot see the vault. All three routes in `settings.yaml.example` support tools; that was verified, not assumed.

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
| `MISSING_CREDENTIAL` | `OPENROUTER_API_KEY` absent from `server/.env`. |
| `UNKNOWN_MODEL` | The `openrouter` route in `$DSH_HOME/settings.yaml` does not list the model in `agent-default-model`. |
| 429 every turn | Free-tier rate limit. Switch to `glm-5.3-flash`. |
| Harness OOM-killed | Both units oversubscribe a 1 GB box. Lower `MemoryHigh` in `agentos.service` to 420M. |
| Writes succeed, search misses them | Reindex failed after the write. The tool result says so in `searchable`. Check `journalctl -u agentos`. |
| Harness vanished after re-provisioning | `provision.sh` rewrites `/etc/caddy/Caddyfile` from `deploy/Caddyfile` alone. Re-run `install-harness.sh`. |
| `status=127` / `env: 'node': No such file or directory` | The unit's `PATH` has no nvm directory. Fixed in the shipped unit via `Environment=PATH=`; if you hand-edited it, put the node bin dir back. |
| Sync timer stopped, vault otherwise fine | Harness commits diverged the box from `origin` and `git pull --ff-only` now fails. See the section above. |
| Rate-limited every turn | You are on `glm-5.2:free`. Switch to `glm-5.3-flash` in the Models page. |
