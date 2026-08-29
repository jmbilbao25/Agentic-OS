---
inclusion: auto
name: lazy-senior
description: How much code to write, and when not to write any. The laziness ladder, root-cause over symptom, and what laziness never applies to. Use before adding a file, a dependency, an abstraction, or a second copy of existing logic.
---

# Lazy senior mode

Adapted from [ponytail](https://github.com/DietrichGebert/ponytail) by
DietrichGebert. Lazy means efficient, not careless. The best code is the code never
written.

## The ladder

Understand the problem first — read the task and the code it touches, trace the
real flow end to end. Then climb, and stop at the first rung that holds:

1. Does this need to be built at all?
2. Does it already exist in this codebase? Reuse the helper or pattern that is
   already here.
3. Does the standard library do this? Use it.
4. Does a native platform feature cover it? Use it.
5. Does an already-installed dependency solve it? Use it.
6. Can it be one line? Make it one line.
7. Only then: write the minimum that works.

Rung 3 is worth more than it looks. This repo dropped `authlib` entirely by moving
to a PBKDF2 hash from `hashlib`, and avoided `python-multipart` by parsing one
urlencoded login form with `urllib.parse.parse_qs`.

## Fix the shared function once

A report names a symptom. Find the function every caller goes through and fix it
there: one guard in the shared path is a smaller diff than one per caller, and
patching only the path the report named leaves a sibling caller broken.

Worked example from this repo: the map drew the kernel and the skills, but clicking
them 404'd *and* they were unsearchable. Two bugs, one cause — `/api/graph` read
`load() + load_system()` while `/api/doc` and the indexer read only `load()`. The
fix was one new function, `vault.load_all()`, used by all three. Patching the 404
alone would have left the search gap untouched.

## Rules

- No abstraction that was not asked for.
- No new dependency that can be avoided.
- Deletion over addition. Boring over clever. Fewest files possible.
- Shortest working diff wins — but only once you understand the problem. The
  smallest change in the wrong place is a second bug.
- Question complex requests: "do you need X, or does Y cover it?"
- Between two stdlib approaches of the same size, take the edge-case-correct one.
  Lazy means less code, not the flimsier algorithm.
- Mark a deliberate simplification that has a known ceiling with a `ponytail:`
  comment naming the ceiling and the upgrade path. See the in-memory login
  attempt counter in `server/auth.py`.

## Never lazy about

Understanding the problem. Input validation at trust boundaries. Error handling
that prevents data loss. Security. Accessibility. Anything explicitly requested.

And leave one runnable check behind. Non-trivial logic gets the smallest thing that
fails if the logic breaks — an assert-based self-check in the module, no framework,
no fixtures. `python -m server.settings`, `python -m server.gauntlet`,
`python -m server.passwd --selfcheck` are all exactly this. Trivial one-liners need
no test.
