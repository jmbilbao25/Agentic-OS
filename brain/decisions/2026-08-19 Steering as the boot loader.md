---
date: 2026-08-19
updated: 2026-08-29
status: accepted
---

# Steering as the boot loader

## Context
The OS needs a deterministic boot on every session: load working memory, open loops,
and lessons before doing any work. Local IDEs and CLIs generally support a
session-start hook, whose stdout is injected into context on exit 0. Hosted
sandboxes generally do not run hooks at all — and that is the primary surface here.

## Decision
Put the boot instruction in an **always-included instruction file** pointing at a
single command (`bash bin/os boot`). Ship an equivalent session-start hook for
surfaces that support one, calling the same script. One entry point, many loaders.

The kernel text lives in `AGENTS.md`; per-harness bindings are generated from it by
`adapters/install.sh` rather than authored separately.

## Tradeoff
What this costs us: the boot is *instructed*, not *enforced*. A sufficiently
distracted agent can skip it, where a hook is mechanical. Accepted because the
alternative on a hosted surface is no boot at all, and because an always-included
file has a compensating advantage — it is re-supplied every turn, so it survives
context compaction that would drop a hook's one-time output.

Second cost, accepted 2026-08-29: generated bindings can drift from the kernel.
Mitigated by a `selftest` check that fails on drift and names `adapters/install.sh`
as the fix, rather than by trusting anyone to remember.

## Alternatives rejected
- **Hook only** — silently does nothing on hosted surfaces, which is where this runs.
- **Inline the memory into the kernel** — puts the entire vault in the context window
  every turn. Defeats the layering and scales terribly.
- **A custom sub-agent with preloaded resources** — unavailable on hosted surfaces,
  and vendor-specific everywhere else.
- **Author each harness's config by hand** — four copies of the same rules, drifting
  independently. This is the mistake `adapters/` exists to prevent.
