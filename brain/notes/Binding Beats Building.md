---
created: 2026-08-19
tags: [kiro, constraints, postmortem]
---

# Binding Beats Building

First cold-boot test failed. A fresh Kiro Web session asked "what are we doing?"
and answered "nothing — empty workspace, no prior context." The OS was fine. The
session was never bound to anything containing it.

Two independent causes, both about delivery rather than design:

1. **No repo selected.** Kiro Web clones repos server-side at session creation. No
   repo → no clone → no `.kiro/steering/` → no kernel → no boot. The kernel cannot
   bootstrap itself from a repo it was never given.
2. **Wrong branch even if selected.** Web clones the *default* branch and offers no
   branch picker. The OS lived on an unmerged branch, so `main` had no `.kiro/` at
   all. A repo-bound session would still have booted empty.

The general lesson: **a config-file OS is only as persistent as its delivery
mechanism.** Steering-as-kernel gives you persistence *within a bound repo*; it
gives you nothing in a session bound to nothing. Those are different guarantees
and it is easy to conflate them.

The fix is a second kernel at a scope above the repo. Kiro Web's **Cloud
configuration** (Settings → Cloud configuration) injects personal steering into
every web sandbox regardless of repo — confirmed by watching a repo-less session
log "Fetching your cloud config" and apply personal steering with an empty
workspace. That kernel has to be **self-bootstrapping**: it can't reference
`bin/os` because in a repo-less sandbox no such file exists yet. So it carries the
clone command and treats the brain as a sidecar repo with its own remote.

Verified: from a completely empty `/projects/sandbox`, a shallow clone of the
brain branch followed by `bin/os boot` reconstructs full working memory. One
command, no repo binding, ~2 seconds.

Corollary worth keeping: the sidecar model is *better* than the repo-resident
model for cross-project memory. A brain that lives in its own repo and is cloned
into whatever sandbox needs it accumulates lessons across every project, instead
of one silo per repo.

Related: [[Kiro Web Capability Matrix]], [[Git Is The Disk]], [[Steering as Boot Loader]]
