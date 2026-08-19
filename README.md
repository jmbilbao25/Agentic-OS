# AgentOS — a persistent agentic OS that runs inside Kiro

A second brain, skills-as-programs, and file-backed loops that survive every
session boundary. Plain markdown, stdlib Python, one bash script. No database, no
daemon, no plugin.

**It works because the repo is the disk.** Kiro Web tears its sandbox down after
a task, so anything not committed is gone. AgentOS puts memory in the repo, boots
it with one command, and pushes it back before the session ends.

```
.kiro/steering/00-kernel.md   kernel — inclusion: always, boots the OS every session
.kiro/steering/10-*.md        vault conventions, loaded on demand (inclusion: auto)
.kiro/skills/*/SKILL.md       programs — recall/write-back, loop engineering
.kiro/hooks/agentos-boot.json automatic boot on IDE/CLI (Web ignores hooks)
bin/os                        the runtime: boot, save, loop, recall, dash, selftest
bin/osutil.py                 parsing, dashboard, self-check (stdlib only)
brain/                        the vault — open this folder in Obsidian
docs/index.html               generated dashboard (GitHub Pages)
```

## The vault

| Layer | Path | Lifetime |
|---|---|---|
| Working memory | `brain/STATE.md` | rewritten constantly, loaded every boot |
| Episodic | `brain/journal/YYYY-MM-DD.md` | append-only, never edited |
| Semantic | `brain/notes/*.md` | permanent, rewritten in place, `[[wikilinked]]` |
| Decisions | `brain/decisions/*.md` | permanent, superseded not deleted |
| Lessons | `brain/lessons.md` | activation-based, pruned when wrong |
| Loops | `brain/loops/*.md` | ledgers with checkboxes, archived when closed |

Only `STATE.md` is loaded every session. Everything else is recalled on demand
with grep. That's progressive disclosure applied to memory instead of to skills.

## Setup

**1. Use it as your brain repo.** Point a Kiro Web session at this repo and say
anything. The kernel boots it. Done.

**2. Drop it into an existing project** so the agent remembers *that* codebase:

```bash
git clone https://github.com/jmbilbao25/Agentic-OS /tmp/agentic-os
cp -r /tmp/agentic-os/{.kiro,bin,brain} your-project/
cd your-project && bash bin/os selftest && bash bin/os boot
```

Then empty `brain/STATE.md` down to the headings and let it fill up as you work.

**3. Make it follow you into every repo.** In Kiro Web open
**Settings → Cloud configuration** and add `00-kernel.md` and the two skills as
personal steering/skills. They then load in sandboxes for repos that don't
contain them. (Personal `~/.kiro/` files are not read on Web — cloud config is
the mechanism.)

## Obsidian

`brain/` is already a valid vault — no plugin needed to read it.

1. Clone the repo locally.
2. Obsidian → *Open folder as vault* → select `brain/`.
3. Graph view, backlinks, and `[[links]]` work immediately.
4. Two-way sync: install **Obsidian Git** and enable commit-and-sync. Your notes
   and the agent's notes land in the same history.

The agent edits the vault from the sandbox and pushes; you pull in Obsidian. Both
sides are editing plain files, so conflicts are ordinary git conflicts.

## Dashboard

`bin/os dash` regenerates `docs/index.html` — a single self-contained file with
working memory, loop progress bars, searchable notes, clickable wikilinks, and the
journal. `bin/os save` runs it automatically.

To view it: **Settings → Pages → deploy from `main` / `docs`**, then open
`https://<you>.github.io/Agentic-OS/`. Inside Kiro Web you can also read it in
the read-only file explorer.

## Commands

```
bin/os boot                    load memory + open loops + lessons  (first call, every session)
bin/os save "summary"          dash + commit + push                (last call, every session)
bin/os recall "term"           grep the vault, grouped output
bin/os log "what happened"     append to today's journal
bin/os lesson "When X → do Y." add an activation-based lesson
bin/os note "Title"            new atomic note
bin/os decide "Title"          new decision record with a tradeoff section
bin/os loop new|next|done|status|close
bin/os dash                    regenerate the dashboard
bin/os selftest                verify the vault is well-formed
```

`selftest` checks the things that silently break the OS: kernel frontmatter is
`inclusion: always`, skill `name` matches its folder, descriptions within limits,
`STATE.md` under its line budget, loop ledgers parseable, no broken wikilinks.

## Loops

Multi-session work goes in a ledger, not a conversation:

```bash
bin/os loop new refactor-auth      # write Goal, Done when, and Steps
bin/os loop next refactor-auth     # prints the fixed prompt + next unchecked step
# ... do exactly that step, append findings to # Notes ...
bin/os loop done refactor-auth 2
bin/os save "loop refactor-auth step 2"
```

Any later session — different tab, different device, zero shared transcript —
resumes from `bin/os loop next`. The ledger is the loop counter; the session is
the loop body. See `brain/notes/Ralph Loop.md`.

## What this cannot do on Kiro Web

Stated plainly, because every workaround below is a real constraint, not a
preference:

- **No hooks.** Boot is instructed by steering, not enforced by the platform. The
  hook in `.kiro/hooks/` covers IDE and CLI only.
- **No custom agents.** No per-role models or tool restrictions on Web. Roles are
  skills, not separate agents.
- **No cron, no daemon, no self-restart.** The sandbox dies with the task, so an
  unattended overnight loop needs an outside driver (GitHub Actions, or Kiro CLI
  locally in a `while` loop). Inside Web, one session advances one step.
- **No repo `mcp.json`.** Configure MCP in Settings → Agent.
- **Sessions expire after 90 days.** Commits don't. Push.

## Design choices worth arguing with

Grep instead of a vector store, markdown instead of a database, one script instead
of a framework. Reasoning is in `brain/notes/` and `brain/decisions/` — the vault
documents its own architecture, which is the point.

Findings and sources behind the design: [RESEARCH.md](RESEARCH.md).
