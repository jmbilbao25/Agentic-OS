---
created: 2026-08-30
tags: [doctor, draft]
---

# Jailbreaks in Execution Harnesses Carry Greater Risk Than Text-Only Jailbreaks

LLM-based agents deployed in product-level execution harnesses expose a larger attack surface than chat-only systems: a successful jailbreak can trigger harmful tool use and produce persistent state changes, not just unsafe text. Red-teaming for these harnesses must therefore evolve from static attack libraries into experience-driven skill evolution that keeps pace with the agent's growing capabilities. The trust-domain split described in [[Persona-Execution Separation Requires Distinct Trust Domains]] addresses the same surface: persona instructions and execution actions cannot share a trust boundary if the system is to remain auditable under adversarial pressure, because the cost of an execution-layer compromise persists across sessions.

Distilled from `2026-08-29 AI radar.md` by the doctor. Review before relying on it.
Related: 
