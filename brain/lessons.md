---
updated: 2026-08-19
---

# Lessons

Activation-based: each line names the situation that should fire it. A lesson
without a trigger is a note. Wrong lessons get deleted, not archived.

- When starting any session in this repo → run `bash bin/os boot` before replying. Because the sandbox starts with no memory of the last session. _(2026-08-19)_
- When a session produces a decision, lesson, or finished step → `bin/os save` immediately. Because sandbox teardown discards uncommitted work silently. _(2026-08-19)_
- When work will outlive one context window → create a loop ledger instead of trusting the transcript. Because context compaction drops the middle of long sessions. _(2026-08-19)_
- When reaching for a hook, custom agent, or repo `mcp.json` on Kiro Web → stop, none of them load; use steering + skills + a shell script. Because Web only reads `.kiro/steering`, `.kiro/skills`, `.kiro/specs`. _(2026-08-19)_
- When about to add a note that overlaps an existing one → rewrite the existing note instead. Because two notes disagreeing is worse than one note being stale. _(2026-08-19)_
- When `gh pr create` or any `gh pr`/`gh issue` subcommand is tempting → use `gh api` REST instead. Because the GraphQL-backed subcommands always fail in this sandbox. _(2026-08-19)_
- When the same loop step fails twice → stop, write the blocker into the ledger's Notes, escalate. Because a third identical attempt produces confident garbage. _(2026-08-19)_
- When verifying a generated UI → load it headless and assert on the DOM, don't assume it renders. Because a template typo produces a blank page that looks fine in source. _(2026-08-19)_
- When a session starts with an empty workspace or no repo bound → the brain is not missing, it is unclone; run the sidecar clone from the global kernel before claiming no context exists. Because repo-resident steering cannot load in a session bound to no repo. _(2026-08-19)_
- When the brain needs to be reachable from any session → keep it in its own repo on the default branch, cloned by the global kernel to a fixed path. Because Kiro Web clones only the default branch of a bound repo and offers no branch picker. _(2026-08-19)_
