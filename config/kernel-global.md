# AgentOS — portable global kernel

Install this at your harness's **user/global** scope, not in a repo. It then loads
in every session — including sessions bound to no repository at all, which is the
only way to get a brain into a session that clones nothing.

Where "global scope" lives depends on the harness:

| Harness | Global location |
|---|---|
| Claude Code | `~/.claude/CLAUDE.md` |
| Kiro | Settings → Cloud configuration (Web), or `~/.kiro/steering/` (IDE/CLI) |
| Cursor | Settings → Rules for AI |
| Codex / opencode / Zed | `~/.config/<tool>/AGENTS.md` |
| Gemini CLI | `~/.gemini/GEMINI.md` |
| Anything else | wherever it reads user-level instructions |

---

You have a persistent second brain. It is not in this sandbox; it lives in a git
repository. Boot it before doing anything else.

## Boot — first tool call of every session, no exceptions

```bash
[ -x /projects/sandbox/Agentic-OS/bin/os ] \
  || git clone -q --depth 1 https://github.com/jmbilbao25/Agentic-OS.git /projects/sandbox/Agentic-OS
bash /projects/sandbox/Agentic-OS/bin/os boot
```

Same path whether the session is bound to the brain repo or to something else, so
there is one command to remember and no branch to pick.

Do this before answering anything, even "hi" or "what are we doing?". A session that
skips boot starts amnesiac and will confidently tell the user there is no prior
context — which is a lie; the context is one clone away.

If the clone fails, say so plainly. Do not carry on pretending to have memory.

## Save — last tool call of every session

```bash
bash /projects/sandbox/Agentic-OS/bin/os save "<one-line summary of this session>"
```

Sandboxes get torn down when a task ends. `save` commits and pushes to the brain's
own remote, so it works from any session regardless of which repo — if any — that
session is bound to. Run it the moment a durable decision is made, not only at the
end.

## While working

- durable correction with a trigger → `bin/os lesson "When X → do Y. Because Z."`
- something happened → `bin/os log "..."`
- decision with a tradeoff → `bin/os decide "<title>"`, then fill it in
- concept worth linking → `bin/os note "<Title>"`
- recall anything → `bin/os recall "<term>"`
- multi-session work → `bin/os loop next <name>`; the ledger remembers, you don't

## Two repos in one session

When the session is bound to some *other* project, the brain is a sidecar clone with
its own remote. Cross-project lessons still land in it. That project's own kernel
applies on top — project rules beat these global ones.

Keep them separate: work product goes in the project repo's branch and PR, memory
goes in the brain. Never commit project code into the brain, and never commit brain
notes into a project repo.

## Maintenance

The clone URL appears exactly once, above. Move the brain and that line is the only
edit; every future session follows.
