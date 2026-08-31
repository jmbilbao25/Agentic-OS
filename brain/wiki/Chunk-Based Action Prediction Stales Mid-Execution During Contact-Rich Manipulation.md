---
created: 2026-08-30
tags: [doctor, draft]
---

# Chunk-Based Action Prediction Stales Mid-Execution During Contact-Rich Manipulation

Vision-language-action models that predict a complete chunk of actions from observations gathered before execution leave tactile and contact conditioning stale as soon as the chunk begins. In contact-rich manipulation — insertion, assembly, grasping with slip — the contact state can change substantially within a single action horizon: a part slips, a surface yields, a tool jams. A pre-computed chunk cannot respond to those mid-chunk changes, so its later actions are conditioned on a world that no longer exists. The fix is execution-time feedback: actions are sampled and conditioned continuously against the current tactile signal, not batched up-front. For agent design this means treating action sequences like STATE — observable and revisable mid-run — rather than like compiled instructions fired once. Chunking works when the world is slow relative to the chunk; it fails when contact dynamics are faster than the chunk window.

Distilled from `2026-08-29 AI radar.md` by the doctor. Review before relying on it.
Related: 
