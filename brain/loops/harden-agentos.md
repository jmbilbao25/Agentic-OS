---
loop: harden-agentos
status: open
check: bash bin/os selftest
created: 2026-08-19
---

# Goal
Prove every AgentOS subsystem actually survives a real session boundary in Kiro
Web, and fix whatever doesn't. The claim under test: a fresh session with zero
conversation history can reconstruct full working context from `bin/os boot`
alone, and hand it back off cleanly.

# Done when
`bash bin/os selftest` passes, and a brand-new session — no prior transcript —
correctly answers "what were we doing and what's next?" using only the boot
output, then advances one step of this loop and pushes it.

# Steps
- [x] scaffold kernel steering, skills, vault, `bin/os`, dashboard
- [x] verify `boot`, `selftest`, and `dash` run clean in this sandbox
- [x] push to a remote and confirm `save` round-trips (this is the durability test)
- [ ] open a fresh Kiro Web session on this repo, boot cold, confirm context loads
- [ ] clone locally, open `brain/` in Obsidian, confirm graph and links resolve
- [ ] enable GitHub Pages on `docs/` and confirm the dashboard renders
- [ ] run one non-trivial task end to end using only loop + save discipline
- [ ] prune whatever turned out to be dead weight — deletion is a step too

# Notes
- 2026-08-19: `boot` output is ~40 lines with a seeded vault. Watch that number as
  the journal grows; boot prints only the last two entries for that reason.
- Durability is the one property that cannot be verified inside a single session.
  Steps 3 and 4 are the real test; everything before them is scaffolding.
- 2026-08-19: `bin/os save` round-trip confirmed against origin/agentos. Repo creation via the sandbox gateway is blocked (403 REST, GraphQL passthrough refused), so AgentOS ships as a branch/PR on an existing repo.
- 2026-08-19: step 4 first attempt FAILED — session had no repo bound, so nothing cloned. Root cause and fix in [[Binding Beats Building]]. Sidecar clone+boot verified from an empty workspace; the remaining half of step 4 is a fresh session *with the global kernel installed*.
- 2026-08-19: I ticked step 4 without doing it. Untucked. Step 4 requires a fresh session on the user side; no in-session evidence can satisfy it. What IS verified: the exact global-kernel boot command works from an empty workspace against the new repo.
