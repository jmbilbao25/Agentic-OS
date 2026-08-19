---
name: second-brain
description: Recall from and write to the persistent brain/ vault — search past sessions, decisions, lessons, and notes before acting, and record new knowledge after. Use when the user references earlier work, asks what was decided or why, asks you to remember something, or when starting work in an unfamiliar area of this project.
---

# Second brain: recall and write-back

The vault is markdown on disk. Retrieval is `grep`, not embeddings. This is
deliberate — a vector DB is a dependency, an index to keep fresh, and a thing
that breaks at 3am. Ripgrep over a few thousand notes is instant.

## Recall, cheapest first

1. `brain/STATE.md` — already in context from boot. Check it before searching.
2. Targeted grep — `rg -il "<term>" brain/` to find files, then read only the hits.
3. Widen with synonyms once. If two greps miss, the knowledge isn't there; say so
   and move on instead of spelunking.
4. `bin/os recall "<term>"` does 2 and 3 with grouped output.

Never read the whole vault. That's what you built the layers to avoid.

## Write-back

| What you learned | Command | Lands in |
|---|---|---|
| durable correction with a trigger | `bin/os lesson "When X → do Y. Because Z."` | `brain/lessons.md` |
| what happened this session | `bin/os log "..."` | `brain/journal/<today>.md` |
| a decision and its tradeoff | `bin/os decide "Title"` | `brain/decisions/` |
| a concept worth linking | `bin/os note "Title"` | `brain/notes/` |

Write during the work. "I'll summarize at the end" loses to a context limit
every time.

## Rewriting over appending

Before writing a new note, grep for an existing one on the same subject. If it
exists, **edit it** — fold in the new information, delete what's now wrong, keep
the filename so inbound `[[links]]` survive. Note the reconciliation in the
journal so the change is auditable.

## STATE.md is a budget, not a log

It is loaded into every future session. Six sections, hard ceiling ~60 lines:
current focus, active loops, open questions, recent decisions, environment
facts, next action. Anything else moves to a note. When it grows, prune it in
the same turn — nobody schedules cleanup later.

## Checks

`bin/os selftest` verifies the vault is well-formed (required files present,
loop ledgers parseable, no broken `[[links]]`). Run it after any structural
change to `brain/`.
