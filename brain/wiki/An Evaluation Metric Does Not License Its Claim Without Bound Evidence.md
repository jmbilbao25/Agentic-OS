---
created: 2026-08-30
tags: [doctor, draft]
---

# An Evaluation Metric Does Not License Its Claim Without Bound Evidence

An evaluation artifact specifies a forward computation — task, scorer, reported number. That artifact does not automatically license the claim attached to the metric, because the historical evidence (model artifact, weights, prompt, dataset version) and the alternative semantics (alternative scorings, normalisation, sample selection) needed to replay the claim may be unbound. A score of "92%" on a benchmark licenses nothing if the model checkpoint cannot be retrieved, the dataset cannot be reconstructed, or the scorer implementation has drifted. This is the eval analogue of [[Merged Is Not Merged]]: presence of a metric is not presence of a result. Licensing a claim requires binding the eval to a commit, model hash, and frozen scorer — the position [[Provenance Or It Didnt Happen]] already takes for facts, extended here to claims about model behaviour. Otherwise evals collapse into vibes ([Evals Before Vibes]).

Distilled from `2026-08-29 AI radar.md` by the doctor. Review before relying on it.
Related: 
