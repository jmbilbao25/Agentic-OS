---
name: activity-forge
description: Turn a routine into a one-press activity in the second brain's Activities panel. Use when the user says make this an automation, make it a button, automate this, run this daily, add an activity, or asks for a routine, a job, or a scheduled task. Also the right answer when a user asks you to "create me an automation" they can trigger themselves later.
---

# Activity forge

**A skill tells you how to do something. An activity is the thing itself.** If the
user will want it again *without you in the room*, it is an activity.

Ask one question: does running this need judgement? If yes, it is a skill. If it is
the same steps every time, it is an activity, and it belongs on a button.

## Write it

```
mcp__agentos__write_activity
  name:        fetch-ai-news          kebab-case, becomes the filename
  description: What it does and when to press it. Shown on the button.
  steps:       ["radar", "distill"]   ordered, from the vocabulary below
  notes:       optional prose for whoever reads the file
```

Call `mcp__agentos__list_activities` first. A second activity that does the same
thing is worse than none, because now nobody knows which button to press.

## The only steps that exist

| Step | Does | Writes |
|---|---|---|
| `radar` | Capture today's AI signal from six keyless feeds | `brain/raw/` |
| `research: <topic>` | Deep-dive one topic, capture the sources | `brain/raw/` |
| `distill` | Triage the newest capture into a digest | `brain/output/` |
| `doctor` | Distil every capture and wikilink it into the vault | `brain/wiki/` |
| `reindex` | Rebuild the search index | — |
| `log: <text>` | Append one line to today's journal | `brain/journal/` |

Steps with an argument are written `verb: argument` — `research: speculative decoding`.

**There is no step that runs a shell command, and asking for one is not a gap to
work around.** `brain/raw/` is fetched from the internet and you read it; a shell
verb would let a captured page reach code execution through you. If a routine
genuinely needs a new capability, say so — it is a reviewed edit to `STEPS` in
`server/activities.py`, which is a code change, not an activity.

## Rules that are checkable

- **Order the steps causally.** `distill` before `radar` digests yesterday's news.
  Capture, then process, then promote.
- **One to four steps.** Past that it is a script; put it in `automations/`.
- **The description says when to press it**, not what it is. "Press this for what
  happened in AI today" beats "AI news automation".
- **Run it once, for real**: `bash bin/os activity <name>`. An activity that has
  never executed is a guess. Report what it wrote, with paths.
- **Do not wrap a single step in an activity for the sake of it.** `- reindex`
  alone is a button that already exists elsewhere.

## When a step is refused

The refusal names every valid step. Read it and fix the step — do not retry the
same call, and do not invent a verb that sounds plausible.

## When not to make an activity

- It needs a decision each time → that is a skill.
- It runs once, ever → just do it.
- It is multi-session project work → that is a loop ledger in `brain/loops/`.
- It is a fact you learned → that is a note in `brain/wiki/`.

## Pruning

An activity nobody presses is a button in the way. Delete it; git remembers.
