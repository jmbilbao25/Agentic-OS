---
layer: output
---

# output — the artifact layer

Things you actually shipped, or are about to. Posts, essays, reports, briefs,
newsletters, PR descriptions, client deliverables.

## Rules

- **Composed, not captured.** An artifact is assembled from `wiki/` notes. If you
  are writing an artifact and discover you have no note to draw on, that is a signal
  to write the note first — the artifact will be better and the note is reusable.
- **Immutable once shipped.** A published piece is a historical record. Corrections
  go in a new version (`v2`), not over the top of the original. What you thought in
  August is data.
- **Status lives in frontmatter**, so the dashboard and the agent can both see it
  without reading the body.
- **Link back.** Every artifact lists the notes it drew on. That backlink is what
  turns the vault from storage into compound interest — you can see which ideas keep
  earning.

## Format

```markdown
---
created: 2026-08-29
status: draft | review | shipped
channel: newsletter | x | blog | client | internal
shipped: 2026-08-31
url: https://…
---

# Title

Body.

---
Drew on: [[Note One]], [[Note Two]], [[Some Decision]]
```

## Why this is a layer and not a folder

`raw` is what the world gave you. `wiki` is what you understand. `output` is what
you gave back. Those are three different lifetimes and three different quality bars,
which is exactly why they are three directories and not one.
