---
created: 2026-08-30
tags: [doctor, draft]
---

# Long-Horizon Agent Harnesses Need Fresh Context, Durable State, and Independent Auditing

Agents that run across desktop apps and a CLI for extended periods degrade under three failure modes: context window saturation, lost task state across restarts, and unverifiable progress. The LongHorizon-Harness design prescribes three concurrent properties to avoid them. Fresh-context execution means each sub-task starts from a clean window so prior reasoning does not corrupt the current step. Durable verified state means task progress, file changes, and intermediate results survive crashes and context resets. Independent auditing means a second agent or human can replay or verify the work without owning the original context. All three are required — dropping any one turns long-horizon work into unreliable [[Ralph Loop]] iterations or untraceable drift. This extends the [[Harness Capability Matrix]] beyond single-session capability into sustained, recoverable operation.

Distilled from `2026-08-29 AI radar.md` by the doctor. Review before relying on it.
Related: 
