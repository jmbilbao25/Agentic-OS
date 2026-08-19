---
inclusion: always
---

# AgentOS Kernel

You are running with a persistent second brain stored in this repo at `brain/`.
The sandbox is ephemeral. **Git is the disk.** Nothing survives a session unless
it is committed and pushed.

## Boot (first tool call of every session, no exceptions)

```
bash bin/os boot
```

That one command prints working memory, open loops, and the lessons ledger.
Do it before answering anything, even "hi". If it fails, say so, don't improvise.

Kiro Web has no `SessionStart` hook — this steering file *is* the boot loader.
It is re-read every turn, so the rule holds even after a context compaction.

## Save (last tool call of every session)

```
bash bin/os save "<one-line summary of this session>"
```

`save` regenerates the dashboard, commits `brain/` + `docs/`, and pushes.
Also run it after any durable decision, not just at the end — an un-pushed
insight is a lost insight.

## Write-back rules

During work, not after:

- Learned a durable fact, preference, or gotcha → `bin/os lesson "..."`
- Made a decision with a tradeoff → `bin/os decide "<title>"`, then fill the file
- Finished a chunk of work → `bin/os log "..."`
- New concept worth linking → `bin/os note "<Title>"`, link it with `[[wikilinks]]`
- Working on a loop → tick the ledger in `brain/loops/<name>.md` as you go

Working memory lives in `brain/STATE.md`. Keep it under ~60 lines: it is loaded
every single boot. Anything colder belongs in `brain/notes/` and gets recalled
on demand with grep, not carried in context.

## Loops

Multi-session work runs as a **loop**, never as a conversation you hope to
remember. `bin/os loop next <name>` gives you the next unchecked step plus the
loop's fixed prompt. Do exactly that step, tick it, `save`, and stop. Fresh
context each iteration is the point — the ledger remembers, you don't.

## Precedence

Explicit user instruction > this kernel > `brain/lessons.md` > habit.
If a lesson is now wrong, edit or delete it. A stale brain is worse than none.
