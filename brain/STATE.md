---
updated: 2026-08-19
---

# Working memory

Loaded on every boot. Hard ceiling ~60 lines — prune, don't append.

## Current focus
Running a persistent agentic OS inside Kiro Web: second brain in `brain/`,
kernel in `.kiro/steering/`, skills as programs, loops as the control system.

## Active loops
- `harden-agentos` — prove each subsystem survives a real session boundary

## Environment facts (Kiro Web, verified 2026-08-19)
- Sandbox is ephemeral; **git is the only durable layer**. Push or lose it.
- Works on Web: `.kiro/steering/`, `.kiro/skills/`, `.kiro/specs/`, bash, internet.
- Does NOT work on Web: hooks, custom agents, repo `.kiro/settings/mcp.json`,
  skill slash-commands, `~/.kiro` global scope. See [[Kiro Web Capability Matrix]].
- MCP on Web is configured in Settings → Agent, not in the repo.
- Sessions expire after 90 days; PRs and commits do not.

## Open questions
- Does anything outside the cloned repo survive sandbox teardown? Docs contradict
  themselves; treat the answer as "no" until measured.

## Where the brain lives
`jmbilbao25/Agentic-OS` (private), on `main`, cloned to
`/projects/sandbox/Agentic-OS`. Sidecar model — see [[Binding Beats Building]].
The earlier copy on `test-repo` branch `agentos` (PR #11) is superseded; ignore it.

## Blocked on the user
- Paste `cloud-config/00-agentos-global.md` into Settings → Cloud configuration.
  Until then, sessions with no repo selected still boot amnesiac.
- Enable GitHub Pages on `/docs` if the dashboard should be viewable in a browser
  (repo is private, so Pages needs a paid plan or making it public).

## Recent decisions
- [[2026-08-19 Steering as the boot loader]] — no SessionStart hook on Web, so the
  always-included kernel file carries the boot instruction instead.
- Grep over markdown instead of a vector DB. See [[Grep Beats Embeddings Here]].

## Next action
`bin/os loop next harden-agentos`
