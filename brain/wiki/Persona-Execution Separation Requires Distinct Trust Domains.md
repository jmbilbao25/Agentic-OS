---
created: 2026-08-30
tags: [doctor, draft]
---

# Persona-Execution Separation Requires Distinct Trust Domains

A single trust domain cannot cheaply satisfy both the persona layer and the execution layer of an LLM agent. The persona — instructions, tone, self-presentation, behavioural policies — must evolve freely under operators, prompts, and feedback. Execution — stateful tool calls, file edits, persistent state changes — must stay traceable, replayable, and auditable. Hosting both in one domain forces either the persona to freeze (so audit holds) or the audit to drift (so persona can move). The fix is architectural separation: persona and execution live in different trust boundaries, connected by a narrow, inspectable interface. This is the same split that makes [[STATE]] reusable across many personas without re-onboarding, and it is consistent with the [[Harness Capability Matrix]] idea that the harness pins execution while steering files like [[Steering as Boot Loader]] can rotate.

Distilled from `2026-08-29 AI radar.md` by the doctor. Review before relying on it.
Related: 
