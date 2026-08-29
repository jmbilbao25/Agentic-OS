---
created: 2026-08-19
updated: 2026-08-29
tags: [runtime, deployment, persistence]
---

# Local Runtime Closes The Gaps

Every gap in [[Harness Capability Matrix]] — no enforced boot, no cron, no daemon, no
custom agents — is a gap in the *hosting*, not in the OS. Move the same vault and the
same `bin/os` onto a machine you control and all of them close at once.

## What a machine you control adds

| Missing capability | What provides it |
|---|---|
| enforced boot | a real session hook, or a wrapper script around the agent CLI |
| routines that fire with your laptop shut | `cron` / `systemd` timers |
| survives logout and restarts on crash | a `systemd` unit |
| unattended loop advancement | a timer calling `bin/os loop next` |
| semantic recall over the whole vault | an indexer + a local embedding model |
| a real UI | a small HTTP server in front of the vault |

None of that needs a vendor feature. It needs a box with an uptime.

## The two viable hosts

**Your own hardware.** Free, private, and asleep half the time. A laptop that sleeps
is a poor host for a scheduler, so this works for interactive use and fails for
routines.

**A small always-on server.** A `t3.micro`-class instance is enough for the vault, a
hybrid search index, and a quantised embedding model, because none of those are heavy
— the *model inference* is remote. Roughly $10/month, and it is awake at 4am when the
routine fires. This is what `deploy/` provisions and what the `deploy-always-on` loop
tracks.

## Keep the model remote

The temptation on any server is to run inference locally too. Resist it at small
sizes: a box that can hold a useful model costs an order of magnitude more than a box
that can hold an index, and the quality is worse. Keep inference behind an
OpenAI-compatible endpoint and treat the provider as swappable — see
[[Model Access Is Not Transferable]] for why pinning yourself to one vendor's auth is
the thing that actually strands you.

What *does* belong on the box: the vault, the search index, the embedding model
(quantised, ~90 MB, CPU-only), the scheduler, and the web UI.

## Why this doesn't invalidate the vault

The vault stays the durable, portable, auditable layer. Any runtime with a database
will offer you better recall than markdown plus grep, and you should use it — as an
*index*, not as the source of truth. State in a database is state you cannot diff,
cannot review in a PR, and cannot read in five years without the software that wrote
it. Markdown in git survives the runtime that indexes it.

The rule: **indexes are disposable, the vault is not.** Anything that inverts that
relationship is a trap, however good the retrieval is.

Related: [[Harness Capability Matrix]], [[Git Is The Disk]], [[Model Access Is Not Transferable]], [[Grep Beats Embeddings Here]]
