---
inclusion: auto
name: vault-conventions
description: Conventions for writing into the brain/ vault — note format, frontmatter, wikilinks, journal and decision layout, and Obsidian compatibility. Use when creating, editing, reorganizing, or pruning any file under brain/.
---

# Vault conventions

`brain/` is a plain Obsidian vault. No plugins required to read it, no database,
no export step. Anything that breaks "a folder of markdown" is a bug.

## Note format

```markdown
---
created: 2026-08-19
tags: [kiro, memory]
---

# Title

One-sentence claim up top. Then detail.

Related: [[Other Note]], [[Some Decision]]
```

- Filenames match the H1: `brain/notes/Ralph Loop.md`. Spaces are fine, Obsidian
  resolves `[[Ralph Loop]]` by filename.
- One idea per note. If a note needs two H1-level claims, it's two notes.
- Links are the index. Prefer adding a `[[link]]` over adding a folder.

## Layers

| Path | Holds | Lifetime |
|---|---|---|
| `brain/STATE.md` | working memory, loaded every boot | rewritten constantly |
| `brain/journal/YYYY-MM-DD.md` | what happened, append-only | permanent, never edited |
| `brain/notes/` | atomic wikilinked knowledge | permanent, rewritten in place |
| `brain/decisions/` | one decision + tradeoff each | permanent, superseded not deleted |
| `brain/lessons.md` | activation-based corrections | pruned when wrong |
| `brain/loops/` | task ledgers with checkboxes | archived when closed |

## Lessons are activation-based

A lesson is useless as a fact; it needs a trigger. Write
`When <situation> → <do this>. Because <one-line reason>.`
Not `Prefer X`. If you can't name the situation that should fire it, it's a note,
not a lesson.

## Contradictions get reconciled, not appended

New information about an existing note **rewrites** that note. Never leave two
notes disagreeing — pick one, fold the other in, and note the change in the
journal. Append-only knowledge rots into a landfill.

## Pruning

`brain/STATE.md` over ~60 lines, or a lesson that hasn't fired in months, is
context tax on every future session. Cut it. Deletion is maintenance.
