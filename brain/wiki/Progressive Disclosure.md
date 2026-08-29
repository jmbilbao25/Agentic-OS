---
created: 2026-08-29
tags: [context, skills, architecture]
---

# Progressive Disclosure

Load the *index* always and the *content* on demand. This is the single structural
idea that lets a capability library grow without the context window growing with it.

Applied to skills: only `name` and `description` sit in context at startup. The body
loads when a request matches the description. Files the body references load only
when the instructions point at them. So a hundred skills cost roughly a hundred
one-line descriptions — a rounding error — until one is actually needed.

Applied to memory: `brain/STATE.md` is the always-loaded index (hard ceiling ~60
lines). Everything colder lives in `brain/wiki/` and is fetched by one deterministic
command. The kernel in `AGENTS.md` deliberately contains **no knowledge** — it
contains the instruction to go get knowledge. See [[Steering as Boot Loader]].

Applied to skill files: a `SKILL.md` that grew past ~150 lines becomes a router
table pointing at one file per job, with an explicit instruction to read *only* the
matching file. The router gets shorter as the skill gets bigger, which is the
signature of the pattern working.

## Why this beats a bigger context window

Bigger windows do not fix the problem, because the cost is not only tokens:

- **Attention dilutes.** A model asked to hold ten irrelevant procedures alongside
  the relevant one follows the relevant one less precisely.
- **Contradictions compound.** Two skills loaded together can disagree; loaded
  separately they never meet. See [[Context Rot]].
- **Cost is per turn, not per session.** An always-included file is re-supplied
  every single turn.

The discipline is the same as good software design: a narrow interface, and the
implementation behind it. The index is the interface.

## The failure mode it prevents

Without it, the natural move when an agent lacks context is to add more to the
always-on layer. That works for a week and then every session starts with four
thousand tokens of instructions, most contradicting each other, and the agent
follows none of them reliably. The fix is never a bigger preamble — it is a smaller
index pointing at more, better-organised content.

## The rule

Anything in the always-loaded layer must justify its place **on every future
session**, not on the one where you added it.

Related: [[Steering as Boot Loader]], [[Context Rot]], [[Grep Beats Embeddings Here]]
