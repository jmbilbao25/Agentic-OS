# AgentOS — a persistent agentic OS with a visual second brain

Give any AI coding agent a memory that survives the session, a vault you can read in
Obsidian, and a web UI that turns the whole thing into something you can actually look
at.

**Model-agnostic. Harness-agnostic. Vendor-agnostic.** The kernel is one markdown file;
bindings for Claude Code, Kiro, Cursor, Copilot, Windsurf, Gemini CLI and the
`AGENTS.md` standard are generated from it. Inference sits behind one environment
variable, so OpenRouter, OpenAI, Anthropic, or a local `ollama` are a URL change apart.

**It works because the repo is the disk.** Agent sandboxes are ephemeral and their
filesystems are not storage. Git is. Every durable thought is a commit.

```
AGENTS.md            the kernel — small, imperative, harness-neutral
bin/os               the runtime — boot, capture, recall, loops, save
config/              portable steering + skills, plus the global kernel
adapters/install.sh  generates per-harness bindings from AGENTS.md
brain/               the vault — raw → wiki → output, plus loops and journal
server/              the visual second brain: hybrid search, RAG, gauntlet, orbit UI
deploy/              always-on provisioning for a $10/mo box
docs/index.html      generated static dashboard (GitHub Pages)
```

## The ARMS model

Four parts. This repo implements all four without depending on any one vendor.

| | Part | Where it lives |
|---|---|---|
| **A** | Applications — what the agent reaches | `server/` micro-app + any MCP/CLI/API your harness has |
| **R** | Routines — scheduled work | `systemd` timers in `deploy/` |
| **M** | Memory — workspace and context | `brain/` + router files + the orbit UI |
| **S** | Skills — SOPs as commands | `config/skills/`, bound into every harness |

## Quickstart

```bash
git clone https://github.com/jmbilbao25/Agentic-OS.git
cd Agentic-OS
adapters/install.sh          # bind to whatever harnesses you have
bash bin/os boot             # load working memory
bash bin/os selftest         # verify the vault is well-formed
```

Then tell your agent: *run `bash bin/os boot` first thing every session.* That single
habit is the whole system.

### Bind it to your agent

```bash
adapters/install.sh --list   # what's bound
adapters/install.sh --all    # bind everything
adapters/install.sh cursor   # bind one
```

Bindings are **generated and committed** — a harness that clones the repo has to find
its config already there. Never hand-edit one; edit `AGENTS.md` and re-run. `bin/os
selftest` fails if a binding drifts.

### Make it follow you into every repo

Install `config/kernel-global.md` at your harness's user/global scope. It clones the
brain as a sidecar and boots it, so even a session bound to no repository has memory.
That file is self-bootstrapping on purpose — see `brain/wiki/Binding Beats Building.md`
for the postmortem that forced it.

## The vault

Three layers, and the boundaries are the point:

| Layer | Holds | Quality bar |
|---|---|---|
| `brain/raw/` | unprocessed capture — clippings, transcripts, dumps | none; capture beats curation |
| `brain/wiki/` | atomic wikilinked notes, one idea each | you can state it in a sentence |
| `brain/output/` | shipped artifacts | publishable |

Promote by **rewriting**, never by moving. A raw capture dragged into `wiki/` unedited is
still raw, just mislabelled. Supporting files: `STATE.md` (working memory, ~60 line
ceiling), `lessons.md` (activation-based corrections), `journal/` (append-only),
`decisions/` (one tradeoff each), `loops/` (task ledgers).

It is a plain Obsidian vault. Clone it, open `brain/`, and the graph works with no
plugins.

## Commands

```bash
bin/os boot                     # working memory + open loops + lessons
bin/os capture "Title" [url]    # → brain/raw/
bin/os note "Title"             # → brain/wiki/
bin/os ship "Title"             # → brain/output/
bin/os log "what happened"      # → brain/journal/<today>.md
bin/os lesson "When X → do Y."  # → brain/lessons.md
bin/os decide "Title"           # → brain/decisions/
bin/os recall "term"            # grep the vault
bin/os loop new|next|done|close|status
bin/os dash                     # regenerate docs/index.html
bin/os save "summary"           # dash + commit + push
bin/os selftest                 # vault well-formed? bindings in sync?
```

## The visual second brain

`server/` is a small FastAPI app that renders the vault as an interactive orbit map —
concentric ARMS rings, `/` to search, click to read, `j`/`k` to walk the link graph —
answers questions over it with citations, and runs a build-and-critique loop against a
real reference.

Four arrangements of the same notes, switched with `1`–`4`:

| | |
|---|---|
| **Rings** | The ARMS zones, orbiting. The default. Positions are deterministic, so spatial memory survives a reload. |
| **Rank** | A line ordered by relevance — search, and the dots line up best-first. Filtered-out notes drop to the tail rather than leaving holes, because a gap in a ranked line says nothing, where a gap in a timeline says "nothing survived that week". |
| **Grid** | Dense and alphabetical, for scanning by name. |
| **Timeline** | A line ordered by date. Pairs with the recency scrubber, which cuts a threshold this shows you the shape of. |

A layout is a pure function to target positions; the renderer owns motion and
interpolates from wherever the last layout left each node, which is what makes
switching an animation rather than a redraw. See `brain/wiki/Frame Beats Canvas.md`.

Retrieval is **hybrid**: SQLite FTS5 (BM25) for keywords, `sqlite-vec` for semantics,
fused with weighted Reciprocal Rank Fusion, plus a bounded nudge for queries that look
like they are *naming* a note — because neither half of a hybrid ranker can see a
title, which made "type the note's name" the search it was worst at. Embeddings are a
quantised BGE-small running on CPU. No Postgres, no vector service, no daemon — the
index is a single file, rebuilt from markdown and thrown away whenever you like.

```bash
pip install -r server/requirements.txt
cp server/.env.example server/.env
python -m server.passwd           # mint a username + password hash, paste into .env
python -m server.index --full
server/tools/devserve.sh          # http://127.0.0.1:8000
python -m server.tools.smoke      # 37 end-to-end checks
```

Auth is **one username and one password**, hashed with PBKDF2 from the standard
library. No registration, no reset, no second account — see `server/README.md` for the
threat model and what it does and does not defend against.

Everything worth tuning while looking at the result — provider, model, fallback chain,
temperature, retrieval weights, motion — is editable in the UI without a restart, and
the settings form is generated from the server's own schema so it cannot drift from the
backend. Bring an OpenRouter key and the model picker filters the whole live catalogue
with context length and price per million tokens.

## Always-on

`deploy/` provisions an EC2 `t3.micro` (~$10/mo) with swap, a venv, systemd units for
the app and a reindex timer, and TLS via Tailscale Funnel — no domain purchase, no
inbound port. Inference stays remote on purpose: a box that can hold a useful model
costs ~10x a box that can hold an index, and is worse at it.

```bash
deploy/launch-ec2.sh      # from AWS CloudShell
# then, on the box:
deploy/provision.sh
```

See `deploy/README.md` and the `deploy-always-on` loop ledger.

## The harness

The map answers *"what do I know?"*. The **JM Agentic-OS Harness** answers *"do
something with what I know"* — an agent that plans, researches against the vault, and
writes back to it. Built on [DSH](https://github.com/deepseek-ai/deepseek-harness),
running GLM 5.3 Flash through OpenRouter.

```bash
bash deploy/install-harness.sh                  # on the box, after provision.sh
ssh -N -L 3080:127.0.0.1:3080 <user>@<box>      # loopback-only on purpose
```

The vault **publishes itself** as ten MCP tools rather than the harness being taught
about it, so the same server works with Claude Desktop, Cursor or anything else that
speaks MCP. Implemented against Starlette directly, with no new dependency: the official
Python SDK needs 3.10 and Amazon Linux 2023 ships 3.9.

The vault is **read-only to the harness process**, enforced by the systemd sandbox
rather than by policy — `ReadWritePaths` covers the agent's scratch workspace and DSH's
own state, and nothing else on the box. That distinction is load-bearing: DSH composes
its own `bash` and `fs` tools, which reach the filesystem directly and know nothing
about the jail, so a jail alone would have been guarding a door that was not the only
one. Every change goes over MCP, through the jail, and lands as its own git commit. It
cannot escape `brain/`; cannot edit `AGENTS.md`, `config/`, `server/` or `bin/` (an
agent that can rewrite its own instructions has no stable behaviour left to reason
about); cannot rewrite the append-only journal; and is capped per session. The installer
re-proves all of that on every run, because a security property that is not tested is
just a comment.

`brain/raw/` is text fetched from the internet, so it reaches the model inside an
explicit untrusted-data envelope. That does not make prompt injection impossible — it
makes the damage bounded, visible and revertable. `deploy/harness/README.md` is honest
about where the line is.

## What this deliberately does not do

- **Enforce boot on hosted harnesses.** No session hooks there, so boot is *instructed*
  by an always-included kernel. Local harnesses get a real hook via `adapters/`.
- **Run inference locally on the small box.** 1 GB RAM holds an index, not a model.
- **Hold state anywhere but git.** Every database here is a cache. Delete
  `server/index.db` and it rebuilds; delete `brain/` and you have lost the OS.
- **Ship a vendor's memory feature.** Those are not diffable, not reviewable in a PR,
  and not readable in five years without the software that wrote them.

## Why it's built this way

The reasoning lives in the vault, which is the best demonstration that it works:

- `brain/wiki/Git Is The Disk.md` — why storage is a git remote
- `brain/wiki/Harness Capability Matrix.md` — how to audit a new harness
- `brain/wiki/Binding Beats Building.md` — a config OS is only as persistent as its delivery
- `brain/wiki/Grep Beats Embeddings Here.md` — keyword-first, and when that changed
- `brain/wiki/Model Access Is Not Transferable.md` — why the provider is one env var
- `brain/wiki/Steering as Boot Loader.md` — always-on instructions beat one-shot hooks
- `brain/wiki/Ralph Loop.md` — the loop pattern this borrows from
- `RESEARCH.md` — the findings behind the design
