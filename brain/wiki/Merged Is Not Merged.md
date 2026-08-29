---
created: 2026-08-29
tags: [git, process, postmortem]
---

# Merged Is Not Merged

A merged pull request means *the commits it contained at merge time* are on the
base branch. It does not mean the branch is on the base branch, and it does not
mean later pushes to that branch went anywhere.

## What happened

PR #1 was opened when the branch had one commit. Nine more commits were pushed to
the same branch afterwards. The PR was merged — reporting `commits: 1` — and
closed. Those nine commits stayed on the branch, orphaned: pushed, backed up, and
absent from `main`.

Nothing errored. `git push` succeeded every time. The branch was green. `main` was
simply missing 34 files, and the only symptom was a deployed box running code that
no longer matched its own default branch.

A second session then built parallel work on top of that incomplete `main` and
merged it as PR #2. At that point two lineages existed, both rooted in the same
first commit, each missing the other's work:

- `main` had a gauntlet loop, runtime settings, modular UI, real webfonts
- the branch had the automations, three skills, six notes, TLS provisioning

Shared files had been rewritten independently on both sides — ~2,400 insertions
against ~3,900 deletions across 30 files. Not a conflict git could resolve.

## The check that would have caught it

```bash
git log --oneline main..origin/<branch>     # commits the branch has that main lacks
git rev-list --count main..origin/<branch>  # zero, or you have a problem
```

Run it **after** any PR merge, not before. Before the merge it is trivially
non-zero and tells you nothing.

Better: compare file trees, because commit counts hide squashes and rebases.

```bash
comm -23 <(git ls-tree -r --name-only <branch> | sort) \
         <(git ls-tree -r --name-only origin/main | sort)
```

## Why "just merge them" was not the answer

Both lineages had independently rewritten the same modules. Taking either side
wholesale would have deleted real work, and a three-way merge would have produced
a file that compiled and behaved like neither.

What worked instead: **treat one lineage as the base and re-land the other's
additions as additions.** Most of the missing work lived in directories the base
never touched (`automations/`, `config/skills/*`, `brain/wiki/`, `deploy/`), so it
re-landed cleanly. The two files that genuinely overlapped were ported by hand,
and two were dropped because the base already had equivalents.

The integration bugs only showed up once it ran: the base's `llm.stream()` yields
event dicts where the incoming caller expected strings, and `llm.models()` did not
exist. **A file-copy merge type-checks and still does not work** — the interfaces
have to be read, not assumed.

## Rules

1. **A merged PR is a snapshot, not a subscription.** Verify after merging.
2. **Push and merge are different events.** Pushing to a merged PR's branch is a
   no-op on the base.
3. **Diff trees, not commit counts**, when reconciling.
4. **Re-land additively where possible.** New files in untouched directories carry
   almost no merge risk; rewritten shared modules carry almost all of it.
5. **Run the base's own test suite before and after.** That is the only way to
   attribute a failure to your change rather than inheriting the blame — here it
   separated one real regression from two pre-existing failures.

Related: [[Git Is The Disk]], [[Evals Before Vibes]], [[Provenance Or It Didnt Happen]]
