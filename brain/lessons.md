---
updated: 2026-08-29
---

# Lessons

Activation-based: each line names the situation that should fire it. A lesson
without a trigger is a note. Wrong lessons get deleted, not archived.

- When starting any session in this repo → run `bash bin/os boot` before replying. Because the sandbox starts with no memory of the last session. _(2026-08-19)_
- When a session produces a decision, lesson, or finished step → `bin/os save` immediately. Because sandbox teardown discards uncommitted work silently. _(2026-08-19)_
- When work will outlive one context window → create a loop ledger instead of trusting the transcript. Because context compaction drops the middle of long sessions. _(2026-08-19)_
- When about to rely on a harness feature (hooks, custom agents, repo-level MCP, global config) → verify it actually loads in *this* surface first. Because unsupported config fails silently rather than erroring, and you will debug the wrong layer for an hour. _(2026-08-19)_
- When about to add a note that overlaps an existing one → rewrite the existing note instead. Because two notes disagreeing is worse than one note being stale. _(2026-08-19)_
- When `gh pr create` or any `gh pr`/`gh issue` subcommand is tempting → use `gh api` REST instead. Because the GraphQL-backed subcommands always fail in this sandbox. _(2026-08-19)_
- When the same loop step fails twice → stop, write the blocker into the ledger's Notes, escalate. Because a third identical attempt produces confident garbage. _(2026-08-19)_
- When verifying a generated UI → load it headless and assert on the DOM, don't assume it renders. Because a template typo produces a blank page that looks fine in source. _(2026-08-19)_
- When a session starts with an empty workspace or no repo bound → the brain is not missing, it is uncloned; run the sidecar clone from the global kernel before claiming no context exists. Because repo-resident config cannot load in a session bound to no repo. _(2026-08-19)_
- When the brain needs to be reachable from any session → keep it in its own repo on the default branch, cloned by the global kernel to a fixed path. Because hosted harnesses clone only the default branch and offer no branch picker. _(2026-08-19)_
- When the user wants an agent that is persistent like a real OS (daemon, scheduler, survives reboot) → that is a machine they control, not a hosted sandbox. Because hosted surfaces have no cron and tear the sandbox down per task. _(2026-08-19)_
- When asked to run one vendor's models through another vendor's agent CLI → say no and explain the boundary. Because agent CLIs authenticate only against their own subscription, their own API key, or a cloud reseller, and vendor terms forbid third parties exposing consumer logins. _(2026-08-19)_
- When writing the kernel → put it in a neutral file (`AGENTS.md`) and generate per-vendor bindings from it. Because a kernel written directly into one vendor's config path binds the OS to that vendor, which is the same mistake as binding it to one repo. _(2026-08-29)_
- When adding semantic search to a markdown vault → keep markdown authoritative and treat the index as disposable, rebuildable from source. Because state you cannot diff or review in a PR stops being memory and becomes a dependency. _(2026-08-29)_
- When sizing a box to host a vault plus a search index → a `t3.micro` is enough, provided inference stays remote. Because the index and a quantised embedding model are small; only the LLM is heavy, and it does not need to live with the data. _(2026-08-29)_
- When a note's own stated revisit-condition comes true → rewrite that note with the reconciliation, keeping the filename. Because the honest record of "we said X, then X's exit condition fired" is more valuable than either a stale note or a silent overwrite. _(2026-08-29)_
- When an integration seems to need a paid subscription → check whether the software and the inference are separately licensed. Because open-source agents are usually free while the model calls behind them are not, and conflating the two leads to paying for the wrong thing. _(2026-08-29)_
- When a system is deployed for the first time → treat the deploy as a test and re-check every status the app reports about itself. Because two bugs here were invisible locally and immediate on the box: an index mode derived from per-run state rather than actual state, and a reverse-proxy log path the packaged systemd sandbox could not write. _(2026-08-29)_
- When TLS is needed on a bare public IP with no domain → use <dashed-ip>.sslip.io with Let's Encrypt HTTP-01. Because it resolves with no DNS account, no token, and no interactive login, which is less setup than both DuckDNS and Tailscale Funnel when 80/443 are already open. _(2026-08-29)_
- When an incremental index skips unchanged inputs → add an explicit backfill pass for outputs that are missing regardless of input change. Because change-detection alone cannot repair damage: a failed embed batch left chunks permanently vector-less, and only a full rebuild fixed it. _(2026-08-29)_
- When building an automation that gathers information → have it write only to the capture layer, never to the knowledge layer. Because an automation that promotes its own output produces a vault full of confident material nobody read, indistinguishable from material that was understood. _(2026-08-29)_
- When a JS module silently fails to execute → check for a duplicate 'const' in the same block before anything else. Because 'node --check' passes per-file but a block-scope redeclaration is a runtime SyntaxError that aborts module evaluation with no visible error, so the whole page just never initialises. _(2026-08-29)_
- When asked to make a UI feel alive → tie one animation to real provenance rather than adding ambient motion. Because hovering a citation to ignite the note it came from answers a question the user actually has, while decorative motion only costs attention. _(2026-08-29)_
