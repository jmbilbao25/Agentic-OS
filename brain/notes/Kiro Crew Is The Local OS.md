---
created: 2026-08-19
tags: [kiro, crew, local, verified]
---

# Kiro Crew Is The Local OS

Every gap documented in [[Kiro Web Capability Matrix]] — no enforced boot, no cron,
no daemon, no custom agents — is closed by **Kiro Crew**, which is official,
open source, and runs on your own hardware. Installed and verified in the sandbox:
`kirocrew 0.2.0`, `kirocrew doctor` clean.

## What it actually is

An open-source personal agent that runs locally or remotely, persistent and
self-learning, reachable from a Mac/Linux desktop app, a web dashboard at
`localhost:5476`, a CLI, and channels like Slack, Discord, and Telegram.

It drives the LLM through **`kiro-cli` over the Agent Client Protocol** — that is
the *only* provider (`agent.provider = acp`, confirmed by `doctor`). So it runs on
your Kiro subscription and Kiro's models. No Anthropic key needed, see
[[Claude Code Cannot Use Kiro Models]].

## The subcommands that matter

Verified present in `kirocrew --help`:

| Command | Closes which gap |
|---|---|
| `cron` | scheduled jobs — the daemon Web could never have |
| `service install` | runs 24/7, survives logout, restarts on crash |
| `spawn` | background subagents |
| `run <spec>` | autonomous task from a spec file — unattended loops |
| `learn add/list/remove` | lessons as a first-class API |
| `memory`, `knowledge` | six-layer memory + curated document store |
| `snapshot` / `restore` | portable backup of all state |
| `cloud` | run it on your own EC2 |
| `agent`, `workspace`, `app` | custom agents, workspaces, installable apps |

## Its memory model vs. ours

Crew ships a genuinely more sophisticated memory system than `brain/`:

- Six layers — preferences, projects, tiered-decay history, semantic key-value in
  SQLite, episodic with FAISS vector search, and lessons.
- Episodic scoring is `cosine × (0.7 + 0.3 × importance) × exp(-0.03 × days)`, with
  MMR diversity reranking. 50% decay at ~23 days.
- Confidence gating: LLM writes need ≥ 0.8, user-explicit writes always win.
- Consolidation runs automatically at 30 messages and after 3h idle.
- Lessons cap at 50 entries and are injected as a distinct "always follow these"
  block — the same activation-based idea as `brain/lessons.md`, enforced by the
  runtime instead of by a steering file.
- Embeddings are local and automatic (~610 MB model, downloads on first start),
  with keyword fallback until it lands.

So Crew's memory supersedes hand-rolled recall. What it does *not* supersede is a
**human-readable, git-versioned, Obsidian-native vault**. Crew's state lives in
SQLite under `~/.kiro/crew/`; ours is diffable markdown reviewable in a PR. Those
are complementary, and Crew has the seam for it: the Knowledge Library ingests
**local folders recursively**, so point it at `brain/` and the vault becomes
searchable inside Crew without giving up git as the source of truth.

## Why this doesn't invalidate the vault

The vault stays the durable, portable, auditable layer — it survives Crew, works in
Obsidian, and reviews in a PR. Crew becomes the runtime that was missing: enforced
boot via hooks, a scheduler, a daemon, and a dashboard nobody had to hand-write.

Related: [[Kiro Web Capability Matrix]], [[Git Is The Disk]], [[Claude Code Cannot Use Kiro Models]], [[Ralph Loop]]
