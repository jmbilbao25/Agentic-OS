---
created: 2026-08-30
tags: [doctor, draft]
---

# Scaling World Models Requires Recursive Grounded Data Engines

Crawling more video and spending more compute is the default recipe for scaling world models, but it is inefficient because passively observed video carries no grounded reward signal. Code agents demonstrate the alternative: an agent acting inside an environment produces trajectories with verifiable outcomes, and those outcomes serve as supervision for the next generation. A recursive data engine — agent acts, outcomes are scored, scored trajectories retrain the model — gives world models the same grounded reward that RLVR gives reasoners. This addresses the broader entropy-collapse problem documented in [[RLVR Collapses Policy Entropy and Degrades Pass@k Coverage]]: passive data scales quantity without sharpening signal, while recursive engines scale both together.

Distilled from `2026-08-29 AI radar.md` by the doctor. Review before relying on it.
Related: 
