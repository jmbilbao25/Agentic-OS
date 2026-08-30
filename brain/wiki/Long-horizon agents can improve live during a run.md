---
created: 2026-08-30
tags: [doctor, draft]
---

# Long-horizon agents can improve live during a run

Most agent self-improvement processed accumulated experience only after execution completed, so lessons could not redirect the active trajectory. Live self-improvement inverts that: an in-flight run both contributes to and benefits from its own ongoing experience. Observed failures are validated immediately against the current state and applied to the rest of the same task, not just to future runs. This complements [[Long-Horizon Agent Harnesses Need Fresh Context, Durable State, and Independent Auditing]]: fresh context is what you consume, durable state is what you store, and live self-improvement is what you learn before the run ends. The durability implication is that lesson validators must run inside the harness, not after it.

Distilled from `2026-08-30 AI radar.md` by the doctor. Review before relying on it.
Related: 
