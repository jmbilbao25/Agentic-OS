---
created: 2026-08-19
tags: [kiro, persistence]
---

# Git Is The Disk

Kiro Web's documented sandbox lifecycle is: provision → clone repos → configure →
execute → **tear down**. Elsewhere the docs say a session's file state persists in
the cloud. Those two statements are never reconciled, and sessions are deleted
after 90 days regardless.

So the safe model, and the one this OS is built on: **the sandbox filesystem is a
scratch disk, and the git remote is storage.** A thought that isn't pushed didn't
happen.

Practical consequences:

- `bin/os save` is part of the workflow, not a chore at the end. It runs after
  every durable decision.
- The vault lives *inside the repo* (`brain/`), not in a home directory or a
  config folder outside the clone. Anything outside the clone is presumed lost.
- Commit granularity is the memory granularity: `git log brain/` is a legible
  history of what the agent learned and when. `git blame brain/lessons.md` shows
  when a lesson was learned and which session learned it.
- This is also the sync mechanism for humans: clone the repo locally, open
  `brain/` in Obsidian, and the Obsidian Git plugin round-trips edits back.

The upside of the constraint: memory is diffable, reviewable in a PR, and
revertable. A `brain/` change can be rejected in code review — which is a
property no vector store has.

Related: [[Kiro Web Capability Matrix]], [[Grep Beats Embeddings Here]]
