---
created: 2026-08-19
tags: [kiro, constraints]
---

# Kiro Web Capability Matrix

Kiro Web runs the same agent harness as the IDE and CLI, but only a subset of the
config surface loads — which dictates the entire design of this OS.

| Primitive | Kiro Web | Notes |
|---|---|---|
| `.kiro/steering/*.md` | ✅ | all four inclusion modes; arrives with the repo clone |
| `.kiro/skills/*/SKILL.md` | ✅ | activation works; slash-commands and import "coming soon" |
| `.kiro/specs/*/` | ✅ | wave-based parallel task execution, resumable |
| bash + runtimes + internet | ✅ | Python, Node, Go, Rust, etc.; open internet |
| built-in subagents | ✅ | context-gathering and general-purpose only |
| `.kiro/hooks/*.json` | ❌ | every trigger unsupported on Web |
| `.kiro/agents/*.json` | ❌ | built-in agents only |
| repo `.kiro/settings/mcp.json` | ❌ | configure MCP in Settings → Agent instead |
| `~/.kiro/` global scope | ❌ | no local filesystem; use Cloud configuration |

The consequences that matter:

1. **No `SessionStart` hook** → the boot sequence cannot be automated by the
   platform. An `inclusion: always` steering file is the substitute; it is
   re-read every turn, which makes it more compaction-proof than a hook anyway.
   See [[Steering as Boot Loader]].
2. **No custom agents** → no per-role tool restrictions or model routing on Web.
   Roles have to be skills the one agent loads, not separate agents.
3. **Sandbox is per-task and torn down** → [[Git Is The Disk]].
4. **Cloud configuration** (Settings → Cloud configuration) syncs personal
   steering and skills into every web sandbox, which is how the kernel follows
   you into repos that don't contain it.

Related: [[Steering as Boot Loader]], [[Git Is The Disk]], [[Ralph Loop]]
