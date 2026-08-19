---
name: loop-engineering
description: Run multi-session or long-horizon work as a file-backed loop with a ledger instead of relying on conversation memory. Use when a task is too large for one context window, spans sessions, needs unattended repetition until a check passes, or when the user says loop, keep going, overnight, or resume.
---

# Loop engineering

A conversation is not a control system. When work outlives a context window,
move the state to disk and make each iteration start clean. This is the Ralph
loop (Geoffrey Huntley): fixed prompt, external state, fresh context, repeat.
The filesystem and git are the memory — not the transcript.

## Anatomy

`brain/loops/<name>.md`:

```markdown
---
loop: refactor-auth
status: open
check: npm test
created: 2026-08-19
---

# Goal
One paragraph. Stable across every iteration. This is the fixed prompt.

# Done when
Observable exit condition. `npm test` green and no `any` left in src/auth.

# Steps
- [x] map current call sites
- [ ] extract token verifier
- [ ] delete legacy middleware

# Notes
Append findings here. Next iteration reads this instead of re-deriving.
```

## Iterating

```
bin/os loop new <name>      # scaffold a ledger
bin/os loop next <name>     # prints goal + next unchecked step
bin/os loop done <name> 2   # tick step 2
bin/os loop status          # all open loops
bin/os loop close <name>    # archive
```

One iteration = read `next`, do **exactly that step**, append findings, tick it,
`bin/os save`. Then stop. Resisting the urge to do steps 3-7 while you're "in
there" is the whole discipline: a half-finished step 5 with no ledger entry is
invisible to the next session.

## Two kinds of loop

**Agent loop** (needs judgement): one iteration per turn or per session. The
ledger carries state across context resets. This is what you use in Kiro Web —
the agent cannot re-invoke itself, so *you* are the loop body and the ledger is
the loop counter. A new session picks up mid-loop with zero re-explaining.

**Shell loop** (deterministic): actually put it in a `while`. Builds, tests,
fixture generation, retry-until-green:

```bash
until npm test; do bin/os log "test run failed, iterating"; done
```

Don't hand-drive what bash can repeat. Don't put judgement in a `while` and
expect a clean result.

## Steps must be resumable

Each step is one context window's worth of work with an observable finish. "Fix
authentication" is not a step. "Extract `verifyToken` into `src/auth/token.ts`,
tests still pass" is. If a step can't be verified from the outside, split it
until it can.

## Failure handling

Same step failing twice → stop looping, write the blocker into `# Notes`, and
escalate to the user. A loop that grinds on a wrong assumption burns tokens and
produces confident garbage. Three strikes is not persistence, it's a bug.

## Native alternative

For feature work with clear requirements, Kiro **specs**
(`.kiro/specs/<name>/tasks.md`) already provide a dependency-graphed task loop
with parallel waves and cross-session resume. Use a spec for "build this
feature"; use a loop ledger for open-ended, exploratory, or maintenance work
that doesn't decompose up front.
