---
created: 2026-08-29
tags: [craft, writing, design]
---

# Taste Is A Checklist

Taste is treated as an innate faculty — you either have an eye or you don't. That
framing is useless to an agent, and mostly useless to a person, because it offers
nothing to do.

The operational version: **taste is a set of rules specific enough to check.**
"Make it beautiful" cannot be executed. "No more than two typefaces and one accent
colour" can be verified in ten seconds by looking. Everything worth calling taste
decomposes into rules of the second kind — that decomposition is what
`config/skills/taste/` is.

## Why this matters for generated work

An agent has no aesthetic discomfort. It will not wince at a full-width paragraph of
14px grey-on-grey, because nothing hurts. What it can do is run a checklist that
says line length 45–90 characters and body contrast ≥ 4.5:1. Externalised rules
substitute for the missing wince.

This is the same move as the rest of this OS: put the thing in a file because the
runtime cannot be trusted to hold it. Memory goes in `brain/`, procedure goes in
skills, and judgement goes in checklists.

## The generative direction

Rules do not only filter, they generate. "Every element must answer a question"
produces a different first draft than "add a dashboard" — you start by asking what
questions the user has, and the layout follows. Constraints are a starting point, not
a filter applied at the end.

## The three rules that do most of the work

1. **Delete before you add.** The most common improvement is removal. Slop is
   additive; craft is subtractive. If a section survives deletion, it should have
   been deleted.
2. **Honest beats impressive.** A status pill reading `keyword-only` beats one
   reading `hybrid` on an index with no vectors. This repo shipped exactly that lie
   and had to fix it — see [[Evals Before Vibes]]. Anything that has to mislead to
   look good is not good.
3. **Specific beats general.** "Fast" is nothing. "42s full index, 63 vectors, on a
   913MB box" is something. Concreteness is the cheapest quality signal there is, and
   the first thing missing from generated work.

## The slop tells

Generated work has a recognisable smell, and it is mostly *padding that survives
deletion*: opening by restating the request, tricolons everywhere, emoji as headings,
stacked hedges, "comprehensive" and "seamless" and "leverage", a closing summary of
what was just said, bullet lists where every bullet is the same length, praise for
the question.

None of those are style crimes in isolation. Together they signal text produced to
occupy space rather than to say something — which is the actual definition of slop,
and the reason the fix is always deletion rather than rewriting.

## Draft with nerve, review without mercy

Reviewing while drafting produces cautious, shapeless work. Separate the passes:
write the strong version, then run the checklist and cut what fails.

And when rejecting your own work, name the rule. "This feels off" is not a review;
"three of four bullets restate the heading" is something you can fix.

Related: [[Progressive Disclosure]], [[Evals Before Vibes]], [[Signal Triage]]
