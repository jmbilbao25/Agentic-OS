---
created: 2026-08-30
tags: [doctor, draft]
---

# RLVR Collapses Policy Entropy and Degrades Pass@k Coverage

Reinforcement learning with verifiable rewards (RLVR) reliably raises mean accuracy on reasoning benchmarks, but it also drives policy entropy down, narrowing the distribution of reasoning paths the model explores. The visible win on pass@1 hides a loss on pass@k for large k: the same model, sampled many times, covers fewer distinct solutions than it did before training. This matters because downstream evaluation that only looks at pass@1 or mean score will miss the regression. Evaluation must explicitly track coverage metrics — pass@k, solution diversity, entropy — to detect the collapse. This is a concrete instance of [[Evals Before Vibes]]: a single accuracy number can be green while the underlying capability has thinned, and the eval framework must surface that. RLVR is not broken — it is a coverage-losing trade, and the eval must name the trade.

Distilled from `2026-08-29 AI radar.md` by the doctor. Review before relying on it.
Related: 
