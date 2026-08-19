---
date: 2026-08-19
status: accepted
---

# Steering as the boot loader

## Context
The OS needs a deterministic boot on every session: load working memory, open
loops, and lessons before doing any work. On Kiro IDE and CLI this is a
`SessionStart` hook, whose stdout is injected into context on exit 0. On Kiro Web
hooks do not run at all.

## Decision
Put the boot instruction in `.kiro/steering/00-kernel.md` with
`inclusion: always`, pointing at a single command (`bash bin/os boot`). Ship the
equivalent `SessionStart` hook in `.kiro/hooks/` for IDE and CLI users, calling
the same script. One entry point, two loaders.

## Tradeoff
What this costs us: the boot is *instructed*, not *enforced*. A sufficiently
distracted agent can skip it, where a hook is mechanical. Accepted because the
alternative on Web is no boot at all, and because an always-included steering
file has a compensating advantage — it is re-supplied every turn, so it survives
context compaction that would drop a hook's one-time output.

## Alternatives rejected
- **Hook only** — silently does nothing on Web, which is the primary surface here.
- **Inline the memory into steering** — puts the entire vault in the context
  window every turn. Defeats the layering and scales terribly.
- **A custom agent with `resources`** — custom agents are unavailable on Web.
