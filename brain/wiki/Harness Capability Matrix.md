---
created: 2026-08-19
updated: 2026-08-29
tags: [constraints, portability]
---

# Harness Capability Matrix

Every agent harness loads a *subset* of the config surface it documents, and which
subset decides the entire design of an agentic OS. Audit the surface before building
on it, because the failure mode is silent: an unsupported config file does not error,
it simply never loads.

## The primitives worth auditing

For any harness, ask which of these actually work — not which are documented:

| Primitive | Why it matters | Typical answer |
|---|---|---|
| always-on instruction file | the boot loader; without it there is no kernel | usually ✅ |
| skills / reusable procedures | SOPs as commands instead of re-prompting | often ✅ |
| session-start hook | makes boot *enforced* rather than merely instructed | ✅ local, ❌ hosted |
| scheduler / cron | routines that fire with the laptop shut | ❌ hosted, ✅ own machine |
| long-lived daemon | anything that must survive logout | ❌ hosted, ✅ own machine |
| custom sub-agents | per-role tool restrictions and model routing | inconsistent |
| repo-level MCP config | connectors that travel with the project | inconsistent |
| user/global config scope | a brain that follows you into any project | inconsistent |
| shell + internet | the escape hatch that makes everything else recoverable | almost always ✅ |
| filesystem durability | whether anything survives the session | **assume ❌** |

## The two conclusions that generalise

**1. Hosted sandboxes give you instructions, not enforcement.** No hook, no cron, no
daemon. So the boot sequence has to live in an always-included instruction file that
is re-supplied every turn — which is more compaction-proof than a hook anyway. See
[[Steering as Boot Loader]].

**2. The filesystem is a scratch disk.** Every hosted harness either tears the
sandbox down per task or expires sessions on a timer, and the docs are usually
self-contradictory about which. Treat durability as absent until measured. See
[[Git Is The Disk]].

Together those force the same architecture regardless of vendor: **a small imperative
kernel, a markdown vault, one shell entry point, and git as storage.** Nothing in
that list is proprietary, which is why the OS ports in an afternoon when the harness
changes.

## Auditing a new harness

1. Write the smallest possible always-on instruction file. Start a session. Did it
   load? That is your kernel slot.
2. Try a session hook. If it fires, promote boot from instructed to enforced.
3. Look for a scheduler. If there isn't one, routines need an always-on machine —
   see [[Local Runtime Closes The Gaps]].
4. Write a file outside the repo, end the session, come back. Assume it's gone; you
   are only checking whether you were pleasantly surprised.
5. Record the answers here, then delete whatever the harness made redundant.

Related: [[Steering as Boot Loader]], [[Git Is The Disk]], [[Local Runtime Closes The Gaps]], [[Ralph Loop]]
