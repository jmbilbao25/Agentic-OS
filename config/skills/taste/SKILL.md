---
name: taste
description: Apply a concrete craft standard to anything being produced — UI, prose, code, or a document — and review work against checkable rules instead of vibes. Use when building or reviewing an interface, writing anything a human will read, naming things, or when the user says make it good, polish it, taste, impeccable, or asks why something feels cheap.
---

# Taste

Taste is not a feeling you either have or lack. It is a **checklist you actually
run**. Every rule below is falsifiable: you can look at the work and say yes or no.
That is the whole trick — "make it beautiful" is unactionable, "no more than two
typefaces and one accent colour" is a thing you can check.

## The router

Read only the file that matches what you are making. Reading all of them wastes
context and none of it applies.

| Making | Read |
|---|---|
| an interface, a page, a dashboard | `ui.md` |
| prose, docs, a README, a commit message | `writing.md` |
| an API, a CLI, a module, names | `code.md` |
| reviewing anything before shipping | `review.md` |

## The four rules that outrank everything

1. **Honest beats impressive.** A loading state that admits it is loading beats a
   fake progress bar. A UI that says "keyword-only, no embeddings" beats one that
   silently returns worse results. If the work has to mislead to look good, the
   work is not good.

2. **Delete before you add.** The most common fix is removal. If a section,
   button, adjective, or abstraction can be deleted without loss, deleting it *is*
   the improvement. Slop is additive; craft is subtractive.

3. **Every element earns its place.** For each thing on the screen or page, name
   the question it answers. No answer, no element. This kills decorative charts,
   restated summaries, and "Overview" sections that overview nothing.

4. **Specific beats general.** "Fast" is nothing; "answers in 200ms on a 1 GB box"
   is something. Concreteness is the cheapest quality signal available and the
   first thing missing from generated work.

## The AI-slop tells

Recognise these in your own output and cut them:

- Opening with a restatement of the request
- Tricolons everywhere — "fast, simple, and powerful"
- Emoji as section headers, or a 🚀 in a sentence about latency
- Hedging stacked on hedging: "it's generally considered somewhat useful"
- "Comprehensive", "robust", "seamless", "leverage", "elevate", "delve", "tapestry"
- A summary that repeats the thing it summarises
- Bullet lists where every bullet is the same shape and length
- Praise for the user's question, or for the material being summarised
- Closing with "In conclusion" or an offer to help further nobody asked for
- Confident claims with no source, number, or file path attached

## Doing the work

Produce, then run the relevant checklist against it, then fix what fails. Do not
review while drafting — that produces cautious, shapeless work. Draft with nerve,
review without mercy.

When rejecting your own work, name the rule it violated. "This feels off" is not a
review; "three of the four bullets restate the heading" is.

## What this skill will not do

It will not make an ugly idea beautiful. Presentation cannot rescue a thing that
should not exist — the correct note on those is "delete this", and saying so is
the most valuable thing taste does.
