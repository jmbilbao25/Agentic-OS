---
name: second-brain
description: Recall from and write to the persistent brain/ vault — search past sessions, decisions, lessons, and notes before acting, and record new knowledge after. Covers the raw/wiki/output layers and when to promote between them. Use when the user references earlier work, asks what was decided or why, asks you to remember something, or when starting work in an unfamiliar area of this project.
---

# Second brain: recall and write-back

The vault is markdown on disk. For an agent mid-task, retrieval is `grep` — not
embeddings. This is deliberate: keyword search is exact, instant, and its failure mode
is honest. Zero hits means zero hits, where a stale vector index quietly degrades.

(The web UI in `server/` *does* run hybrid semantic search, because a human browsing
searches by half-remembered concept. That index is a disposable cache over the same
markdown. Agents recall; humans browse.)

## Recall, cheapest first

1. `brain/STATE.md` — already in context from boot. Check it before searching.
2. Targeted grep — `rg -il "<term>" brain/` to find files, then read only the hits.
3. Widen with synonyms once. If two greps miss, the knowledge isn't there; say so and
   move on instead of spelunking.
4. `bin/os recall "<term>"` does 2 and 3 with grouped output.

Never read the whole vault. That's what you built the layers to avoid.

## The three layers

| Layer | Holds | When you write here |
|---|---|---|
| `brain/raw/` | unprocessed capture | dumping a source you haven't digested yet |
| `brain/wiki/` | atomic wikilinked knowledge | you understand it and can state it in one sentence |
| `brain/output/` | shipped artifacts | composing something for an audience |

**Never cite a `raw/` file as knowledge.** If a raw capture is load-bearing for what
you're about to say, distil it into `wiki/` first — that is the whole point of the
layer boundary. Promotion is rewriting, never moving.

## Write-back

| What you learned | Command | Lands in |
|---|---|---|
| durable correction with a trigger | `bin/os lesson "When X → do Y. Because Z."` | `brain/lessons.md` |
| what happened this session | `bin/os log "..."` | `brain/journal/<today>.md` |
| a decision and its tradeoff | `bin/os decide "Title"` | `brain/decisions/` |
| a concept worth linking | `bin/os note "Title"` | `brain/wiki/` |

Write during the work. "I'll summarize at the end" loses to a context limit every time.

## Rewriting over appending

Before writing a new note, grep for an existing one on the same subject. If it exists,
**edit it** — fold in the new information, delete what's now wrong, keep the filename so
inbound `[[links]]` survive. Note the reconciliation in the journal so the change is
auditable.

If a note stated its own revisit-condition and that condition has now fired, record the
reconciliation explicitly rather than silently overwriting. "We said X, then X's exit
condition fired, so now Y" is more valuable than either a stale note or a clean lie.

## STATE.md is a budget, not a log

It is loaded into every future session. Hard ceiling ~60 lines: current focus, active
loops, environment facts, open questions, recent decisions, next action. Anything else
moves to a note. When it grows, prune it in the same turn — nobody schedules cleanup
later.

## Checks

`bin/os selftest` verifies the vault is well-formed: required files present, loop ledgers
parseable, no broken `[[links]]`, `STATE.md` within budget, and harness bindings in sync
with `AGENTS.md`. Run it after any structural change to `brain/`.
