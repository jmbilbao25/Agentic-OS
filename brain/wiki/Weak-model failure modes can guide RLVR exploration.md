---
created: 2026-08-30
tags: [doctor, draft]
---

# Weak-model failure modes can guide RLVR exploration

The existing note [[RLVR Collapses Policy Entropy and Degrades Pass@k Coverage]] establishes that reinforcement learning with verifiable rewards tends to narrow coverage. A complementary technique that emerged is to use a smaller model's failure distribution as an exploration signal for the larger model — its mistakes mark where reasoning coverage has gaps. This converts entropy collapse from a hidden regression into an externally visible map of under-explored states. The general claim: when a stronger policy is over-committing to a narrow solution set, the residual errors of a weaker peer are a useful proxy for where the search has not gone. Weak-to-strong critique thus serves two roles — a verifier of completed answers, and a generator of unexplored regions to push the stronger policy into.

Distilled from `2026-08-30 AI radar.md` by the doctor. Review before relying on it.
Related: 
