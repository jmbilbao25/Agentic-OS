---
created: 2026-08-19
tags: [kiro, pattern]
---

# Steering as Boot Loader

A steering file with `inclusion: always` is injected into context on every
interaction. That makes it the closest thing Kiro Web has to a `SessionStart`
hook — and in one respect it is strictly better.

A hook fires once, at session start. Its output sits in the transcript and can be
dropped by context compaction on a long session. An always-included steering file
is re-supplied every turn, so the boot rule survives compaction, `/compact`, and
a session resumed on another device.

The pattern: keep the kernel file **small and imperative**. It should not contain
knowledge — it contains the instruction to go get knowledge:

```markdown
---
inclusion: always
---
Run `bash bin/os boot` as the first tool call of every session.
Run `bash bin/os save "<summary>"` as the last.
```

Knowledge lives behind one deterministic command. That keeps the always-on token
cost near zero while giving the agent a full memory load in a single tool call —
progressive disclosure applied to memory rather than to skills.

Fallback ladder for other surfaces: IDE and CLI *do* support hooks, so ship a
`SessionStart` hook that runs the same `bin/os boot` (stdout on exit 0 is
injected into context). Same entry point, two loaders, no duplicated logic.

Related: [[Kiro Web Capability Matrix]], [[Git Is The Disk]]
