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

Loopback by default, and that is not laziness — **the published DSH web app has no authentication**. No password, no token, no session. It assumes it is bound to localhost on a machine you control, and it enforces that assumption for anything that touches configuration or secrets: see [the configuration plane is loopback-only](#the-configuration-plane-is-loopback-only-and-no-setting-changes-that). Serving it publicly therefore gives you a working chat surface with a read-only settings surface, which is worth knowing before you decide the proxy is enough.

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

## The configuration plane is loopback-only, and no setting changes that

The single most surprising thing about running this behind a proxy. Over the public URL, the Models page fails with

```
Loading the provider directory failed: settings are unavailable in this browser
```

and the workspace picker cannot open a directory chooser. Nothing is broken. DSH gates a specific set of methods to a loopback `Host` **unconditionally** — `trustedHosts` and `--trusted-host` do not affect them, because the fence is a DNS-rebinding defence rather than authentication. Its own source says so:

> `trustedHosts` is a DNS-rebinding fence, explicitly not authentication, so the whole configuration plane stays loopback-same-origin until a real authentication layer exists.

Measured on this deployment, same socket, only the `Host` header differing:

| Method | via the public host | via `127.0.0.1` |
|---|---:|---:|
| `settings.describe` / `mutate` / `update` / `replace` | **403** | 200 |
| `credentials.describe` / `set` / `unset` | **403** | 200 |
| `llm.discoverModels` | **403** | 200 |
| `agentPreset.read` / `copy` / `remove` / `openDocument` | **403** | 200 |
| `host.pickDirectory` / `openPath` | **403** | 200 |
| `llm.providers` / `llm.models` | 200 | 200 |

The last row is why the model *list* renders but you cannot *add* one: reading the catalogue carries no endpoints or key state, so it is deliberately allowed, while everything that reads or writes configuration and secrets is not. `settings.describe` would expose every namespace's configuration and `credentials.describe` reports whether an arbitrary environment variable is set and where from — reconnaissance for an anonymous caller.

Note this is version-specific. The published `0.1.1-rc.2` has **no browser authentication at all**, which is exactly why the config plane is closed. Newer unreleased builds add a launch-token cookie, which is the "real authentication layer" that comment is waiting for; expect this restriction to relax once that ships.

### So how do you change settings?

**Either reach it over loopback** — an SSH tunnel makes the browser's `Host` `127.0.0.1`, and every pane above works, including Models, credentials, presets and the directory picker:

```sh
ssh -N -L 3080:127.0.0.1:3080 ec2-user@<host>
# then open http://127.0.0.1:3080  (no password — Caddy is not in the path)
```

**Or edit the file**, which is hot-reloaded and needs no restart. `$DSH_HOME/settings.yaml` is the same document the Models page writes:

```yaml
llm-pi-ai:
  providers:
    openrouter:
      api: openai-completions
      baseURL: https://openrouter.ai/api/v1
      apiKeyEnv: OPENROUTER_API_KEY
      models:
        - id: anthropic/claude-sonnet-4.5     # any OpenRouter model id
          name: Claude Sonnet 4.5
          contextWindow: 200000
          maxTokens: 8192
```

Adding a whole new provider is the same shape with a new route key — then set `provider:` on the `agent-default-model` row in the overlay, or pick it in the UI over the tunnel. A route the pi-ai catalogue does not ship needs `api`, `baseURL` and a non-empty `models` list, or it is refused where it is written.

## Where to put things

Everything the harness reads lives under two roots: `$DSH_HOME` (`~/.dsh-harness`) and the workspace (`~/harness-workspace`). Nothing here requires touching the repo.

| To add | Put it in | Takes effect |
|---|---|---|
| **A skill** for the agent | `~/.dsh-harness/skills/<name>/SKILL.md` | next model step — the root is watched |
| A skill only for one project | `~/harness-workspace/.dsh/skills/<name>/SKILL.md` | same |
| **A plugin** | `dsh plugin --profile web add <pkg>` → `~/.dsh-harness/profiles/web/` | restart |
| Mount a plugin that isn't a bundle | a row in `~/.dsh-harness/profiles/web/cordis.patch.yml` | restart |
| **Model / provider** changes | `~/.dsh-harness/settings.yaml`, or the Models page | immediately, hot-reloaded |
| **An agent preset** | `~/.dsh-harness/.agent-presets/<name>/` | restart |
| A skill bundled with a preset | `~/.dsh-harness/.agent-presets/<name>/skills/<skill>/SKILL.md` | restart |

### Skill roots, in the order DSH scans them

Lower rank wins when two roots define the same skill name. `<projectRoot>` is the nearest ancestor containing `.git`, or the working directory when there is none — here that is `~/harness-workspace`.

| Rank | Source | Path on this box | Writable by the agent |
|---:|---|---|---|
| 100 | `project-dsh` | `~/harness-workspace/.dsh/skills` | yes |
| 200 | `project-agents` | `~/harness-workspace/.agents/skills` | yes |
| 300 | `custom` | `~/Agentic-OS/config/skills` ← the OS's six | **no**, read-only |
| 400 | `user-dsh` | `~/.dsh-harness/skills` | yes |
| 500 | `user-agents` | `~/.agents/skills` | yes |

Rank 300 is set by `customSkillDirs` in `jm-agentic-os.cordis.yml`, which is what makes the OS's skills the agent's skills. It is deliberately read-only to the harness process: the agent can *use* `taste` and `skill-forge`, and cannot rewrite them. Authoring goes to rank 400; promoting into rank 300 is a human step.

**Skill file shape** — discovery is one level deep only, so `<root>/<name>/SKILL.md` or `<root>/<name>.md`. Nested `**/SKILL.md` is ignored.

```yaml
---
name: my-skill        # kebab-case, and must equal the directory name
description: What it does. Use when <the phrases a user would actually type>.
---

# My skill

Body. Loaded only once the description matches, so put the trigger words in the
description and the instructions here.
```

### Automations: not a DSH concept

There is no directory that turns a file into a scheduled job. Two different things get called "automation" here:

- **Agentic-OS automations** — `automations/<name>.py`, plus an entry in the allowlist in `server/app.py`, plus a `deploy/systemd/*.timer`. Three coupled places, all read-only to the agent, all requiring root for the timer. This is code that runs on a schedule with vault write access, so it stays a human change.
- **`dsh-schedule`** — session-local reminders delivered as chat messages, fixed-interval, no cron, and not composed in this deployment. It is not a substitute for a timer.

The closest thing the agent can create unaided is a **loop** in `brain/loops/`, which is a durable work ledger it can write over MCP and pick up in a later session.

## Plugins — no official marketplace, several community ones

DSH ships **no** marketplace. The built-in `Plugins` pane is `dsh-host-plugin-inventory`, whose own reference calls it a *"read-only projection of the current Cordis Loader plugin state"* that "owns no cache, history, provenance model, event stream, or mutation path." It shows what is loaded; it installs nothing.

**Community marketplaces do exist on npm**, and this deployment installs one: `dsh-plugin-marketplace`. It replaces the Plugins pane with a browsable catalogue of GitHub's `dsh-plugin` topic and installs from the UI.

Understand what that means before adding more. A DSH plugin is a Cordis plugin: it runs **in the harness process**, with the harness's environment — which includes `OPENROUTER_API_KEY` — and its access to the vault MCP tools. There is no plugin sandbox. `npm install` from a marketplace UI is `npm install` with your credentials in reach.

The one installed here was read before installing, and the notes are worth keeping as the bar for the next one:

| Check | `dsh-plugin-marketplace@0.2.8` |
|---|---|
| Provenance | MIT, real repo (`Scorp1o117/dsh-plugin-marketplace`), 692 weekly downloads — the most-used of ~10 |
| Size | 64 KB, 7 files, no build step |
| Install scripts | none (no `postinstall`) |
| Dependencies | one, `@deepseek-ai/schemastery` — DeepSeek's own |
| Environment read | `process.env.DSH_HOME` only. Not the API key |
| Network | `api.github.com` (topic search), `registry.npmjs.org`. Nothing else |
| Subprocesses | `execFile(node, [dshBin, "plugin", "--profile", p, "add", pkg])` — no shell, so no injection; package name regex-validated first; 5-minute timeout |
| Writes | only `$DSH_HOME/profiles/web/cordis.patch.yml` |

Alternatives, all third-party and all ~2 weeks old at the time of writing: `dsh-marketplace`, `untr-dsh-marketplace`, `@springbrand/dsh-plugin-marketplace`, `@w2112515/dsh-plugin-marketplace` (depends on `execa` — it spawns processes more freely), `@ruihuahe/dsh-plugin-marketplace`, `@starpivot/dsh-plugin-marketplace`, `@dshindex/dsh-plugin-marketplace`, `@webcasa/deepseek-harness-marketplace`.

**You probably already have what you need.** This deployment composes **136 plugins**, including the shell, filesystem, editor, web-fetch, web-search, subagents, plan mode, skills, todo, jobs, goals and the Ralph loop. Check with:

```sh
dsh web --patch deploy/harness/jm-agentic-os.cordis.yml --dump-config \
  | grep "^  name: '" | sort -u
```

**To add one**, `dsh plugin` forwards to pnpm inside the profile directory (`$DSH_HOME/profiles/web`, created on first boot):

```sh
export DSH_HOME=$HOME/.dsh-harness
dsh plugin --profile web add <npm-package>
```

What happens next depends on the package, and dsh tells you which case you are in:

- A package that declares `dsh.bundle` becomes a **profile layer automatically**.
- Anything else installs as a plain dependency and is *not loaded*. dsh warns: `declares no dsh.bundle — installed as a plain dependency, not a profile layer`. To actually mount it, add a row to `$DSH_HOME/profiles/web/cordis.patch.yml` — a persistent user patch layer applied after every bundle:

```yaml
- insert:
    - id: my-plugin
      name: '<npm-package>'
      config: {}
```

Then `sudo systemctl restart jm-harness`.

**One recommendation against.** `@deepseek-ai/dsh-tool-cordis` with `@deepseek-ai/dsh-cordis-host-runner` gives the model self-inspection over the live plugin graph, and DSH's own example config says to "treat this deployment like shell access, not as a security boundary." On a box holding your vault and your API key, that undoes the sandbox described above. Install it on something disposable, not here.

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
