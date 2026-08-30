---
created: 2026-08-30
tags: [doctor, draft]
---

# Streaming tactile feedback closes contact-state staleness

The existing note [[Chunk-Based Action Prediction Stales Mid-Execution During Contact-Rich Manipulation]] describes why fixed action chunks go stale mid-execution. The complement is the fix: stream action generation conditioned on tactile feedback arriving during execution, so each new action is conditioned on the contact state the robot is in right now rather than the state when the chunk was predicted. Tactile feedback is the disambiguating signal for contact evolution. The general claim: when a model's predictions go stale inside an action horizon, the cheapest fix is rarely to predict more carefully at the start — it is to close the loop with a sensor that measures what actually changed. Streaming + mid-execution conditioning is the architectural shape of that fix.

Distilled from `2026-08-30 AI radar.md` by the doctor. Review before relying on it.
Related: 
