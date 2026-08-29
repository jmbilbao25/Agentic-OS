---
created: 2026-08-29
tags: [reliability, testing, retrieval]
---

# Evals Before Vibes

If you cannot measure a system's quality, you cannot tell improvement from
regression — and you will confidently ship regressions, because a change you
believed in *feels* like an improvement.

This note exists because the first automated digest this repo produced observed that
its own capture contained nothing about evaluation or failure logging for personal
agents, and that this is "exactly where a personal OS will silently degrade". That
was correct, and it was a gap here too.

## The concrete case

Retrieval in this repo was tuned by measurement, not intuition, and every intuition
turned out to be wrong:

| Belief | Measurement |
|---|---|
| "hybrid search beats either half" | naive RRF scored **worse** than semantic alone |
| "the library handles query embedding" | `query_embed()` was a **no-op** — cosine 1.0000 vs `embed()` |
| "keyword search is a fine baseline" | stopwords buried the note literally titled *Git Is The Disk* |

None of those would have been found by using the system and feeling good about it.
All three took a ten-line benchmark. It lives at
`server/tools/eval_retrieval.py` and runs in seconds.

## What a minimum viable eval looks like

Not a framework. A file with ten cases and an expected answer.

- **Probes that share little vocabulary with their target**, so keyword matching
  cannot pass them by accident.
- **Plus exact-match probes** that keyword search must still win — otherwise you
  "improve" semantic recall by destroying filename lookup and never notice.
- **A single number** you can compare across runs.
- **Committed to the repo**, so a future change can be checked against the same bar.

## The rule that keeps it honest

> Add a probe whenever the system fails to find something you knew was there.

A benchmark containing only cases you already pass is decoration. Its score goes up
over time while the system does not improve, which is worse than having no benchmark
because it manufactures confidence.

## Beyond retrieval

The same argument applies to everything an agent OS does, and most of it is
unmeasured here — stated plainly rather than glossed:

| Subsystem | Measured? |
|---|---|
| retrieval quality | yes — `eval_retrieval.py` |
| vault well-formedness | yes — `bin/os selftest`, with both guards proven by negative test |
| auth negative paths | yes — wrong password, wrong user, lockout, stale session |
| index integrity | yes — coverage + partial flag, self-healing verified |
| **answer quality (RAG)** | **no** — citations are checked for existence, not for support |
| **digest usefulness** | **no** — no ground truth exists |
| **whether the OS makes work better** | **no**, and probably unmeasurable |

Naming the unmeasured parts is the point. An honest gap list is a roadmap; an
implied claim of full coverage is a lie that costs you later.

## Exit code is not evidence

A command exiting 0 proves it ran. Assert on the observable outcome: row counts,
HTTP status, rendered DOM, file contents, the actual number. This repo's own history
contains a step ticked without being done, preserved deliberately in the
`harden-agentos` ledger — the discipline working exactly once it was written down.

Related: [[Provenance Or It Didnt Happen]], [[Grep Beats Embeddings Here]], [[Signal Triage]]
