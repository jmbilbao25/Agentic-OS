---
name: skill-forge
description: Turn a repeated task into a reusable skill, or split an overgrown skill into a file set with a router. Use when the user says make this a skill, you notice the same instructions being given twice, a SKILL.md has grown past ~150 lines, or the user asks to organise, refactor, or create skills.
---

# Skill forge

**The rule: the second time you are told the same thing, it becomes a skill.** Not
the third, not "when I have time". The second time is when the pattern is proven and
the memory of what went wrong the first time is still fresh.

## Anatomy

```
config/skills/<name>/
  SKILL.md      frontmatter + when it fires + a router table
  <job>.md      one file per distinct job or reference set
```

Frontmatter is the whole activation contract:

```yaml
---
name: research          # MUST equal the folder name — selftest enforces this
description: <what it does> Use when <the trigger phrases and situations>.
---
```

The `description` is the only part loaded until the skill fires, so it is doing two
jobs at once: saying what the skill does, and listing the words that should trigger
it. Write the triggers as the user would actually phrase them, not as you would
categorise them. `"make it good, polish it, why does this feel cheap"` beats
`"quality assurance"`.

## Thin first, router later

A skill under ~120 lines is one file. Do not build a file tree for a skill that does
one thing — that is ceremony.

Split when **any** of these is true:

- past ~150 lines
- it covers two jobs that never co-occur
- it carries reference material (checklists, examples, templates) alongside procedure
- you keep scrolling past most of it to reach the part you need

When you split, `SKILL.md` gets **shorter**, not longer. It becomes a router:

```markdown
| Making | Read |
|---|---|
| an interface | `ui.md` |
| prose | `writing.md` |
```

Then state the rule explicitly: *read only the file that matches the task, never all
of them.* Progressive disclosure is the mechanism that keeps a large capability
library nearly free until used — see `brain/wiki/Progressive Disclosure.md`.

## Writing rules

- **Imperative, not descriptive.** "Run the checklist, fix what fails" — not "this
  skill helps with quality".
- **Rules must be checkable.** "Two typefaces maximum" can be verified; "good
  typography" cannot. If you cannot check it, it is not a rule, it is a mood.
- **Say what NOT to do.** Guardrails are the most valuable content, because the
  failure modes are what actually recur.
- **Include the escape hatch.** When does this skill not apply? A skill that claims
  universal applicability gets ignored.
- **No knowledge in the skill** that belongs in the vault. Skills are procedure;
  `brain/wiki/` holds understanding. Link, don't duplicate.
- **Short skills get followed. Long ones get skimmed.**

## Testing a new skill

1. Run it once, for real, on a real task. A skill that has never executed is a
   guess.
2. Note where you had to improvise — that gap is the missing instruction, and it is
   the highest-value edit you will make to the file.
3. `bash bin/os selftest` — verifies `name` matches the folder and the description
   is present and within limits.
4. `adapters/install.sh` — re-link so every harness sees it.

## When not to make a skill

- The task happened once. Wait for the second time.
- It is a fact, not a procedure → that is a note in `brain/wiki/`.
- It is a multi-session project → that is a loop ledger in `brain/loops/`.
- It only encodes a preference already in `AGENTS.md` or `brain/lessons.md`.

## Pruning

A skill that has not fired in months is context tax on every session. Delete it.
Deletion is maintenance, and git remembers.
