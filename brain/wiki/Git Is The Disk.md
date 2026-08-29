---
created: 2026-08-19
updated: 2026-08-29
tags: [persistence, portability]
---

# Git Is The Disk

The documented sandbox lifecycle for hosted agent harnesses is: provision → clone repos
→ configure → execute → **tear down**. Elsewhere the same docs usually claim a session's
file state persists in the cloud. Those two statements are never reconciled, and sessions
get deleted on a timer regardless.

So the safe model, and the one this OS is built on: **the sandbox filesystem is a scratch
disk, and the git remote is storage.** A thought that isn't pushed didn't happen.

Practical consequences:

- `bin/os save` is part of the workflow, not a chore at the end. It runs after every
  durable decision.
- The vault lives *inside the repo* (`brain/`), not in a home directory or a config folder
  outside the clone. Anything outside the clone is presumed lost.
- Commit granularity is memory granularity: `git log brain/` is a legible history of what
  the agent learned and when. `git blame brain/lessons.md` shows when a lesson was learned
  and which session learned it.
- This is also the sync mechanism for humans: clone the repo, open `brain/` in Obsidian,
  and the Obsidian Git plugin round-trips edits back.

The upside of the constraint: memory is diffable, reviewable in a PR, and revertable. A
`brain/` change can be rejected in code review — a property no vector store has.

## This is also the portability argument

Git as the disk is what makes the OS survive a change of harness, not just a change of
session. The vault is markdown; the runtime is one shell script; storage is a protocol
every tool on earth speaks. Swap the agent, the model, the vendor, or the machine and the
memory is untouched.

Any component that wants to hold state somewhere other than git — a database, a vendor's
memory feature, a vector index — is welcome to, **as a cache**. The moment it becomes the
only copy, you have traded an auditable artifact for a dependency. See
[[Local Runtime Closes The Gaps]].

Related: [[Harness Capability Matrix]], [[Grep Beats Embeddings Here]], [[Local Runtime Closes The Gaps]]
