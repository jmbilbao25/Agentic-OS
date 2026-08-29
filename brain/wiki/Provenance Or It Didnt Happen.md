---
created: 2026-08-29
tags: [research, memory, reliability]
---

# Provenance Or It Didnt Happen

Every claim in the vault carries where it came from, or it is marked unverified.
There is no third category, and "I'm fairly sure" is the third category pretending
to be the first.

This matters more for an agent's memory than for a human's, because an agent will
read its own note in six months with **total confidence and no recollection of how
sure it was when writing it**. A human at least feels the hesitation again. The
note is the only place that hesitation can be stored.

## The three states

| State | How it is written | What it licenses |
|---|---|---|
| **Verified** | source link, or the command and its output | acting on it |
| **Measured** | the number, the date, the conditions | acting on it, with the conditions restated |
| **Unverified** | the words "not verified" or "assumed", explicitly | reasoning about it, never asserting it |

An unmarked claim is read as verified. That is why omission is worse than a wrong
label: a wrong label gets corrected, an omission gets inherited.

## What counts as provenance

- A URL, for anything external
- A file path and line, for anything in the repo
- A command and its actual output, for anything measured
- A date, always — "913MB RAM" was true of one instance on one day
- The conditions, for a measurement — "247MB under a 700MB cap while idle" is a
  different claim from "247MB"

## Layer boundaries are a provenance mechanism

`brain/raw/` exists so that unverified material has somewhere to live that is not
`brain/wiki/`. The rule "never cite a raw file as knowledge" is a provenance rule
wearing a filing costume: the directory *is* the label.

An automation that writes directly to `wiki/` destroys this, because the resulting
note is indistinguishable from one a human understood and restated. That is why
`automations/radar.py` writes only to `raw/`, and why distillation is a separate
deliberate step.

## The measurement discipline

When recording a number, record how it was obtained. "The app uses 247MB" is nearly
useless in six months. Useful:

> `systemctl show agentos -p MemoryCurrent` → 247MB against a 700MB cap, idle,
> 2026-08-29, `t3.micro` with a 2GB swapfile.

Now a future reader can tell whether their 400MB reading is a regression or just a
different workload.

## Why an agent gets this wrong by default

Language models are fluent about things they have not checked, and fluency reads as
confidence. The mitigation is structural rather than motivational: make the *format*
require provenance, so producing an unsourced claim means leaving a visible hole
rather than writing a smooth sentence.

Related: [[Signal Triage]], [[Git Is The Disk]], [[Evals Before Vibes]]
