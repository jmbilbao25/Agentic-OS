# Activities

Automation recipes. One file each, and the Activities panel in the web UI turns
every one into a button.

A **skill** teaches an agent how to do something. An **activity** is the thing
itself: it runs without an agent present, from the panel or from
`bin/os activity <name>`.

```markdown
---
name: fetch-ai-news
description: What it does, and when to press it. Shown on the button.
---

# Fetch ai news

Prose for whoever reads the file. Ignored by the runner.

## Steps

- radar
- distill
```

That is the entire format. Frontmatter, then a `## Steps` list.

## The steps

The vocabulary is fixed, and lives in `STEPS` in [`../../server/activities.py`](../../server/activities.py):

| Step | Does | Writes |
|---|---|---|
| `radar` | Capture today's AI signal from six keyless feeds | `brain/raw/` |
| `research: <topic>` | Deep-dive one topic and capture the sources | `brain/raw/` |
| `distill` | Triage the newest capture into a digest | `brain/output/` |
| `doctor` | Distil every capture and wikilink it into the vault | `brain/wiki/` |
| `reindex` | Rebuild the search index | — |
| `log: <text>` | Append one line to today's journal | `brain/journal/` |

**There is no `shell:` step, and that is the design.** `brain/raw/` is text fetched
from the internet; activities are authored by an agent that reads it and then
executed by a human pressing a button. A shell verb would make "summarise this
captured page" a route to arbitrary code execution with the user supplying the
click. So an activity composes capabilities the server already has and cannot
invent new ones — adding a verb is a reviewed edit to `STEPS`, not data.

## Writing one

Ask the agent. `mcp__agentos__write_activity` takes a name, a description and a
JSON array of steps, validates every step against the vocabulary, and returns the
vocabulary in the error when a step is wrong — so a small model fixes itself on the
next call. `config/skills/activity-forge/SKILL.md` is the instruction it follows.

By hand: drop a file in here and it appears in the panel. A file that does not
parse is reported in the panel's notice bar rather than silently ignored.

Then run it once. An activity that has never executed is a guess.
