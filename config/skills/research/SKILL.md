---
name: research
description: Investigate a topic across real sources, attribute every claim, and land it in the vault without polluting it. Use when the user asks what is new, asks you to research or look into something, wants to know the state of the art, needs sources for a claim, or asks about latest trends, papers, tools, or models.
---

# Research

Research is gathering plus **judgement**. The gathering is automated; the judgement
is the part that matters and cannot be.

## The tools

```bash
bin/os radar                       # today's signal, 6 keyless sources → brain/raw/
bin/os research "<topic>"          # topic-specific gather → brain/raw/
bin/os research "<topic>" --fetch 4 # also pull page text for the top results
bin/os distill                     # LLM triage of the newest capture → brain/output/
bin/os brief                       # radar + distill in one step
```

Everything lands in `brain/raw/` with provenance. Nothing lands in `brain/wiki/`
automatically, and that boundary is the point — see `sources.md` for why.

## The loop

1. **State the question first**, in one sentence, before gathering. Without it you
   will collect interesting things instead of relevant ones.
2. **Gather** with `bin/os research`. Six sources, no API keys.
3. **Triage** — most of what comes back is noise. Ask of each item: does this change
   a decision? If no, it is context, not knowledge. See `triage.md`.
4. **Verify anything load-bearing.** Open the actual source. A digest is a pointer,
   not evidence, and an LLM summary of a paper is two lossy steps from the paper.
5. **Distil into `brain/wiki/`** in your own words, one idea per note, with the
   source linked. If you cannot restate it without the tab open, you have not
   understood it yet.
6. **Reconcile, don't append.** If a note already covers this, rewrite that note.
   Two notes disagreeing is worse than one note being stale.
7. **Let the raw capture rot.** It is in git if you need it. Deleting it is a valid
   and encouraged outcome.

## Rules

- **Never present a search result as a finding.** "arXiv has three papers on this"
  is not "this is how it works".
- **Cite or flag.** Every factual claim gets a source, or the words "I have not
  verified this".
- **Distinguish what you read from what you inferred.** These get conflated
  constantly and it is the main way research produces confident wrongness.
- **Recency is not relevance.** A 2019 paper that the field still builds on beats
  yesterday's preprint. Sort by whether it changes something, never by date alone.
- **Report the absence.** "Nothing in this capture addresses evaluation" is often
  the most valuable sentence in a brief — a gap in the field is a gap in your plan.
- **Contradictions get named, not averaged.** If two sources disagree, say so and
  say which you believe and why.
- **Say when a search failed.** An empty result is information. Silence looks like
  an answer.

## What good output looks like

A brief that answers the question in the first sentence, grades its items by
whether they matter, names the pattern across them, names what is missing, and
attaches a source to every claim.

A brief that lists everything found in the order found is a directory listing, not
research.
