# Adapters

`AGENTS.md` is the kernel. Everything in this directory exists to bind that one
file to a specific agent harness, because the industry has not agreed on a single
config location and probably never will.

```bash
adapters/install.sh --list      # what is bound right now
adapters/install.sh --detect    # bind only harnesses already present (default)
adapters/install.sh --all       # bind everything
adapters/install.sh kiro claude # bind specific harnesses
```

## What gets written

| Harness | Binding | Mechanism |
|---|---|---|
| agents.md standard | `AGENTS.md` | native — nothing generated |
| Claude Code | `CLAUDE.md`, `.claude/skills/*` | generated file + symlinks |
| Kiro (IDE/CLI/Web) | `.kiro/steering/`, `.kiro/skills/*`, `.kiro/hooks/` | generated + symlinks |
| Cursor | `.cursor/rules/agentos.mdc` | generated, `alwaysApply: true` |
| GitHub Copilot | `.github/copilot-instructions.md` | generated |
| Windsurf | `.windsurf/rules/agentos.md` | generated, `trigger: always_on` |
| Gemini CLI | `GEMINI.md` | generated |

Codex, Zed, Jules, Devin, opencode and a growing list read `AGENTS.md` directly,
so they need no adapter at all.

## Rules

1. **Never hand-edit a binding.** Every generated file carries a marker comment
   saying so. Edit `AGENTS.md` (behaviour) or `config/` (conventions and skills),
   then re-run the script.
2. **Bindings are committed on purpose.** A harness that clones this repo must find
   its config already present — it cannot run `install.sh` before reading its own
   kernel. Generated-and-committed is the same deal as `docs/index.html`.
3. **Never put logic in a binding.** Logic belongs in `bin/os`. A binding points;
   it does not decide.
4. `bin/os selftest` fails if a binding has drifted out of sync with `AGENTS.md`.
   The fix is always `adapters/install.sh`, never a manual patch.

## Adding a harness

Add an `install_<name>()` function and append the name to `ALL`. If the harness
wants frontmatter, pass it as the second argument to `emit`. If it wants a skills
directory, call `link_skills <dir>`. Three lines is a normal adapter.
