---
inclusion: auto
name: vault-conventions
description: Conventions for writing into the brain/ vault — the raw/wiki/output layers, note format, frontmatter, wikilinks, journal and decision layout, and Obsidian compatibility. Use when creating, editing, reorganizing, or pruning any file under brain/.
---

# Vault conventions

`brain/` is a plain Obsidian vault. No plugins required to read it, no database, no
export step. Anything that breaks "a folder of markdown" is a bug.

## The three layers

Knowledge flows inward. Nothing is born a wiki note.

| Layer | Holds | Quality bar | Lifetime |
|---|---|---|---|
| `brain/raw/` | unprocessed capture | none — capture beats curation | disposable once distilled |
| `brain/wiki/` | atomic wikilinked knowledge | one idea, in your own words | permanent, rewritten in place |
| `brain/output/` | shipped artifacts | publishable | immutable once shipped |

Promote by **rewriting**, never by moving. A raw capture that got dragged into
`wiki/` unedited is still raw, just mislabelled.

## Supporting files

| Path | Holds | Lifetime |
|---|---|---|
| `brain/STATE.md` | working memory, loaded every boot | rewritten constantly |
| `brain/journal/YYYY-MM-DD.md` | what happened, append-only | permanent, never edited |
| `brain/decisions/` | one decision + tradeoff each | permanent, superseded not deleted |
| `brain/lessons.md` | activation-based corrections | pruned when wrong |
| `brain/loops/` | task ledgers with checkboxes | archived when closed |

## Note format

```markdown
---
created: 2026-08-29
tags: [memory, retrieval]
---

# Title

One-sentence claim up top. Then detail.

Related: [[Other Note]], [[Some Decision]]
```

- Filenames match the H1: `brain/wiki/Ralph Loop.md`. Spaces are fine; Obsidian
  resolves `[[Ralph Loop]]` by filename.
- One idea per note. If a note needs two H1-level claims, it is two notes.
- Links are the index. Prefer adding a `[[link]]` over adding a folder.
- Tags describe the *idea*, not the tool you happened to use that day. Tool-named
  tags rot the moment you switch tools.

## Lessons are activation-based

A lesson is useless as a fact; it needs a trigger. Write
`When <situation> → <do this>. Because <one-line reason>.`
Not `Prefer X`. If you cannot name the situation that should fire it, it is a note,
not a lesson.

## Contradictions get reconciled, not appended

New information about an existing note **rewrites** that note. Never leave two notes
disagreeing — pick one, fold the other in, keep the filename so inbound `[[links]]`
survive, and record the change in the journal. Append-only knowledge rots into a
landfill.

## Pruning

`brain/STATE.md` over ~60 lines, or a lesson that hasn't fired in months, is context
tax on every future session. Cut it. Deletion is maintenance.

## Portability

Write nothing that depends on a specific agent, vendor, or IDE. The vault outlives
whichever harness is fashionable this quarter — that is the entire point of keeping
it as markdown in git.
