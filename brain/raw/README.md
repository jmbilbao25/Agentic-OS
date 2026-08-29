---
layer: raw
---

# raw — the capture layer

Unprocessed input. Clippings, transcripts, pasted threads, API dumps, screenshots'
worth of text, half-formed thoughts at 2am.

## Rules

- **Append freely.** This is the one layer with no quality bar. Friction here means
  you stop capturing, and uncaptured is unrecoverable.
- **Never cite a `raw/` file as knowledge.** If you want to rely on something in
  here, distil it into `brain/wiki/` first. A citation to raw is a promise you
  haven't kept yet.
- **Keep the source.** Every file starts with where it came from — a URL, a person,
  a date. Raw material without provenance is rumour.
- **Deletion is allowed and expected.** Once a note in `wiki/` supersedes a raw
  capture, the capture is disposable. Distilled beats hoarded.

## Format

Filenames are `YYYY-MM-DD <slug>.md`. Frontmatter carries the provenance:

```markdown
---
captured: 2026-08-29
source: https://example.com/article
kind: article | transcript | thread | dump | scratch
---

# What it was called

Paste, unedited. Add `> ` blockquotes for your own reactions so the seam between
their words and yours stays visible.
```

## Promotion

`raw/` → `wiki/` is **distillation**, not a move. Read the capture, write the idea
in your own words as an atomic note, wikilink it, then decide whether the raw file
still earns its disk space.
