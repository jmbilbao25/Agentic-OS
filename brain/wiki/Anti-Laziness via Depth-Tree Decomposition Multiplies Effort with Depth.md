---
created: 2026-08-30
tags: [doctor, draft]
---

# Anti-Laziness via Depth-Tree Decomposition Multiplies Effort with Depth

LLM agents often exhibit premature completion, underthinking, and laziness on multi-step tasks because the total effort budget is spent at the top level of the plan. The Depth Tree method splits a task N layers deep and gives every leaf the full time budget of the whole task, so total effort multiplies with depth rather than being amortised across all branches. Treating depth, not breadth, as the multiplier of reliable work fits the broader requirements for long-horizon harnesses — see [[Long-Horizon Agent Harnesses Need Fresh Context, Durable State, and Independent Auditing]] — where premature termination is the dominant failure mode and durable verified state at each leaf is what makes the depth pay off.

Distilled from `2026-08-29 AI radar.md` by the doctor. Review before relying on it.
Related: 
