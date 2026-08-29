---
created: 2026-08-29
tags: [context, loops, reliability]
---

# Context Rot

Agent output quality degrades as the context window fills, and it degrades *before*
the window is full. A long session does not fail at the limit; it gets gradually
worse for a long time first, which is much harder to notice.

Three separable causes:

1. **Dilution.** Relevant instructions compete with accumulated irrelevance for
   attention. The instruction is still present and still ignored.
2. **Contradiction.** Early exploratory statements are still in the transcript when
   the conclusion contradicts them. Both are "context", and nothing marks the first
   as superseded.
3. **Compaction loss.** Summarising a long session drops the middle. What survives
   is the beginning and the recent — and the decisions usually happened in the
   middle.

## Why this argues for resetting rather than persisting

The instinct is to keep one long session so the agent "remembers". That is exactly
backwards. Externalise the state and reset ruthlessly:

- the **ledger** remembers, not the transcript — see [[Ralph Loop]]
- **git** is the disk, not the session — see [[Git Is The Disk]]
- the **kernel** is re-supplied every turn, so it survives compaction where a
  session-start hook's output does not — see [[Steering as Boot Loader]]

A fresh context window plus a good ledger beats a full context window plus a hopeful
transcript, every time.

## Symptoms, in order of appearance

1. Earlier instructions stop being followed precisely.
2. The agent re-derives something it already established.
3. Confident statements contradict decisions made earlier in the same session.
4. Ticking a step it did not actually complete. This one is the reliable alarm —
   it happened in this repo and the correction is preserved in the
   `harden-agentos` ledger deliberately.

## Practice

- One loop step per session where the work allows it. Tick, save, stop.
- Write conclusions to files *as they happen*, not at the end. "I'll summarise
  later" loses to a context limit.
- When a decision supersedes an earlier one, **rewrite** the earlier statement
  rather than appending the correction. Two versions in one context is a
  contradiction the model has to resolve, and it may resolve it wrongly.
- Treat "I'm deep in a long session" as a reason to save and stop, not as momentum
  worth protecting.

## The uncomfortable implication

Most of what feels like productive momentum in a long agent session is the
transcript getting worse. The instinct to keep going is the symptom.

Related: [[Ralph Loop]], [[Progressive Disclosure]], [[Git Is The Disk]], [[Steering as Boot Loader]]
