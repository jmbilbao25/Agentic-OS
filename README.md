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
server/              the visual second brain: hybrid search, RAG, orbit UI
deploy/              always-on provisioning for a $10/mo box
docs/index.html      generated static dashboard (GitHub Pages)
```

## The ARMS model

Four parts. This repo implements all four without depending on any one vendor.

| | Part | Where it lives |
|---|---|---|
| **A** | Applications — what the agent reaches | `server/` micro-app, `automations/` connectors to 6 keyless feeds |
| **R** | Routines — scheduled work | `systemd` timers: daily radar + digest, 15-min vault sync |
| **M** | Memory — workspace and context | `brain/` raw→wiki→output + the orbit UI |
| **S** | Skills — SOPs as commands | `config/skills/`: research, taste, skill-forge, loops, second-brain |

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

bin/os radar                    # 6 keyless feeds → brain/raw/
bin/os research "topic"         # gather on one topic → brain/raw/
bin/os distill                  # LLM triage of newest capture → brain/output/
bin/os brief                    # radar + distill in one step

bin/os dash                     # regenerate docs/index.html
bin/os save "summary"           # dash + commit + push
bin/os selftest                 # vault well-formed? bindings in sync?
```

## The visual second brain

`server/` is a small FastAPI app that renders the vault as an interactive orbit map —
concentric ARMS rings, category clusters, `/` to fuzzy-search, click to preview — and
answers questions over it with citations.

Retrieval is **hybrid**: SQLite FTS5 (BM25) for keywords, `sqlite-vec` for semantics,
fused with Reciprocal Rank Fusion. Embeddings are a quantised MiniLM running on CPU.
No Postgres, no vector service, no daemon — the index is a single file, rebuilt from
markdown and thrown away whenever you like.

```bash
cd server
cp .env.example .env      # then: python -m server.tools.setpass
pip install -r requirements.txt
python -m server.index    # build the index
uvicorn server.app:app --port 8000
```

Auth is a single username + password (PBKDF2, per-IP lockout). Set it with
`python -m server.tools.setpass`. See `server/README.md`.

## Always-on

`deploy/` provisions an EC2 `t3.micro` (~$10/mo) with swap, a venv, systemd units
for the app and a reindex timer, and **automatic TLS** — Caddy plus a real Let's
Encrypt certificate on `<dashed-ip>.sslip.io`, so you get trusted HTTPS with no
domain purchase and no interactive login. Inference stays remote on purpose: a box
that can hold a useful model costs ~10x one that can hold an index, and is worse
at it.

```bash
deploy/launch-ec2.sh      # from AWS CloudShell
# then, on the box:
deploy/provision.sh
```

See `deploy/README.md` and the `deploy-always-on` loop ledger.

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
