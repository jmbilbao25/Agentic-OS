---
created: 2026-08-19
updated: 2026-08-29
tags: [pattern, portability]
---

# Steering as Boot Loader

An always-included instruction file is injected into context on every interaction. That
makes it the closest thing a hosted harness has to a session-start hook — and in one
respect it is strictly better.

A hook fires once, at session start. Its output sits in the transcript and can be dropped
by context compaction on a long session. An always-included instruction file is re-supplied
every turn, so the boot rule survives compaction, an explicit `/compact`, and a session
resumed on another device.

The pattern: keep the kernel **small and imperative**. It should not contain knowledge — it
contains the instruction to go get knowledge:

```markdown
Run `bash bin/os boot` as the first tool call of every session.
Run `bash bin/os save "<summary>"` as the last.
```

Knowledge lives behind one deterministic command. That keeps the always-on token cost near
zero while giving the agent a full memory load in a single tool call — progressive
disclosure applied to memory rather than to skills.

## The fallback ladder

Different surfaces support different loaders. Same entry point for all of them, so there is
never duplicated logic:

| Surface | Loader | Boot is |
|---|---|---|
| hosted sandbox | always-included instruction file | instructed |
| local IDE or CLI | session-start hook running `bin/os boot` | enforced |
| always-on server | `systemd` timer or `cron` | scheduled |
| any harness at all | the user typing `bin/os boot` | manual, still works |

Every rung calls the same script. That is the property that matters: adding a loader is
never a rewrite.

## Where the kernel actually lives

The kernel text belongs in a **neutral** file — `AGENTS.md` — and each harness's binding is
generated from it by `adapters/install.sh`. Writing the kernel directly into one vendor's
config path is the mistake [[Binding Beats Building]] describes, one level up: it binds the
OS to a tool instead of to a capability.

Related: [[Harness Capability Matrix]], [[Git Is The Disk]], [[Binding Beats Building]]
