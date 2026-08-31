---
created: 2026-08-30
tags: [doctor, draft]
---

# Test-Time Policy Optimization Removes the Ground-Truth Label Dependency

Standard post-training — RL and On-Policy Self-Distillation — drives reasoning gains but is gated on ground-truth labels, which makes test-time training impossible. TTPO derives the training signal from the model's own rollouts during inference, so the same optimisation loop that improves offline also improves online. This generalises the principle captured in [[Weak-model failure modes can guide RLVR exploration]]: a smaller or earlier-generation model's behaviour can stand in for ground truth. Removing the label boundary collapses the distinction between training and deployment into a single continuous adaptation process that runs whenever the model is asked a hard question.

Distilled from `2026-08-29 AI radar.md` by the doctor. Review before relying on it.
Related: 
