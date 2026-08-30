---
created: 2026-08-30
tags: [doctor, draft]
---

# Long-Horizon Game Agents Need Explicit World Dynamics, Not Direct Perception-to-Action

Modern games combine first-person perception, rapid visual change, persistent world state, and heterogeneous native controls. Agents that map visual context directly to actions underperform on long horizons because they lack an internal representation of how the world evolves between observations. A world action model that explicitly represents dynamics lets the agent condition on predicted outcomes rather than overfit to observed frames. The failure mode parallels [[Chunk-Based Action Prediction Stales Mid-Execution During Contact-Rich Manipulation]] — both stem from an implicit state representation that goes stale as soon as the world moves past the observation, and both are fixed by making the future a first-class object rather than an extrapolation.

Distilled from `2026-08-29 AI radar.md` by the doctor. Review before relying on it.
Related: 
