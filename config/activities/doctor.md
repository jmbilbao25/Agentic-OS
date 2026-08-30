---
name: doctor
description: Read every capture in brain/raw/ that nobody has promoted yet, distil each into atomic notes, and wikilink them into the knowledge already in the vault. Press this to turn captures into knowledge.
---

# Doctor

`fetch-ai-news` fills `brain/raw/` and writes a digest. Neither of those is
knowledge — a digest is a dated artifact you read once. The doctor does the
promotion the kernel describes: `raw` → `wiki`, by distilling rather than copying,
and it refuses to leave the result unconnected.

For each capture with no notes yet, it asks for at most five atomic notes and
requires every one to link into a note that already exists. A note that links to
nothing is an orphan, and an orphan is a note you will never find again — so
orphans are reported and dropped rather than filed.

Three guarantees worth knowing before you press it:

- **Links resolve.** The model is given the exact list of existing note titles and
  may only link to those; every link is then re-checked and unresolvable ones are
  unwrapped to plain text. `bin/os selftest` fails on a broken wikilink, so this
  is enforcement rather than etiquette.
- **Nothing is overwritten.** A proposed title the vault already has is dropped
  and reported as already covered. Merging a machine's paragraph into a note you
  wrote is a harder operation, and doing it silently would make the vault
  untrustworthy.
- **Everything is reversible.** Each note is tagged `doctor` and `draft`, carries
  the capture it came from, and is its own git commit. `git revert` takes the set
  back out.

Needs an inference key. Read what it writes — `draft` is not a decoration.

## Steps

- doctor
