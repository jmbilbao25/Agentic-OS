---
created: 2026-08-19
updated: 2026-08-29
tags: [constraints, postmortem, portability]
---

# Binding Beats Building

First cold-boot test failed. A fresh session asked "what are we doing?" and answered
"nothing — empty workspace, no prior context." The OS was fine. The session was never
bound to anything containing it.

Two independent causes, both about delivery rather than design:

1. **No repo selected.** Hosted harnesses clone repos server-side at session creation.
   No repo → no clone → no kernel file → no boot. A kernel cannot bootstrap itself from
   a repo it was never given.
2. **Wrong branch even if selected.** Hosted harnesses typically clone the *default*
   branch and offer no branch picker. The OS lived on an unmerged branch, so the default
   branch had no kernel at all. A repo-bound session would still have booted empty.

The general lesson: **a config-file OS is only as persistent as its delivery mechanism.**
A kernel-in-the-repo gives you persistence *within a bound repo*; it gives you nothing in
a session bound to nothing. Those are different guarantees and they are easy to conflate.

The fix is a second kernel at a scope **above** the repo — the harness's user/global
config slot, which is injected into every session regardless of what was cloned. That
kernel has to be **self-bootstrapping**: it cannot reference `bin/os`, because in a
repo-less sandbox no such file exists yet. So it carries the clone command itself and
treats the brain as a sidecar repo with its own remote. That file is
`config/kernel-global.md`.

Verified: from a completely empty workspace, a shallow clone of the brain followed by
`bin/os boot` reconstructs full working memory. One command, no repo binding, ~2 seconds.

Corollary worth keeping: the sidecar model is *better* than the repo-resident model for
cross-project memory. A brain that lives in its own repo and is cloned into whatever
sandbox needs it accumulates lessons across every project, instead of one silo per repo.

Second corollary, learned later: the same argument applies across *harnesses*, not just
repos. A kernel written for one vendor's config path is bound to that vendor. Keeping the
kernel in a neutral file and generating the vendor-specific bindings from it — see
`adapters/` — is the same "binding beats building" insight applied one level up.

Related: [[Harness Capability Matrix]], [[Git Is The Disk]], [[Steering as Boot Loader]]
