---
created: 2026-08-19
tags: [loops, pattern]
---

# Ralph Loop

Geoffrey Huntley's pattern, named after Ralph Wiggum: put a coding agent in a
`while true` loop that re-reads the *same* prompt file every iteration, and let
the filesystem and git carry memory between runs. Each iteration starts with a
clean context window.

Why it works: agent quality degrades as context fills. Rather than fighting that
with bigger windows or clever orchestration, you externalize state and reset
ruthlessly. The plan file, the todo list, and the git history are the memory;
the transcript is disposable.

Adapting it to Kiro Web, where the agent cannot re-invoke itself: **the ledger is
the loop counter and the session is the loop body.** `brain/loops/<name>.md` holds
the fixed goal, the exit condition, and the checkbox steps. One iteration = read
`bin/os loop next`, do exactly that step, append findings, tick it, save, stop. A
later session — possibly on another device — resumes with no re-explaining.

Two rules that keep it from degenerating:

1. **Steps must be externally verifiable.** "Fix auth" is not a step. "Extract
   `verifyToken` into `src/auth/token.ts`, tests still pass" is. Unverifiable
   steps get ticked optimistically and the loop drifts.
2. **Two identical failures ends the loop.** Write the blocker into Notes and
   escalate. Persistence past that point is just expensive hallucination.

Deterministic work still belongs in a real shell loop — `until npm test; do ...`
— because bash repeats for free and doesn't need judgement.

Related: [[Kiro Web Capability Matrix]], [[Git Is The Disk]]
