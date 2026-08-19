# Can you run an agentic OS inside Kiro? — findings

Question: can Kiro carry a persistent second brain, an Obsidian-compatible vault,
a UI, loop engineering, and skills across every session — not just within one?

**Yes.** Not as a plugin or a background process, but as *repo-resident markdown
plus a boot convention*. The build in this repo is the answer; below is what the
research established and where the hard edges are.

*Sources are linked inline. Summarized and paraphrased, not quoted.*

## 1. What Kiro Web actually loads

This is the constraint that decides the whole architecture. Kiro runs one agent
harness across IDE, CLI, Web, and Mobile, but the surfaces do not expose the same
config.

| Primitive | Web | Source |
|---|---|---|
| `.kiro/steering/*.md`, all inclusion modes | ✅ | [Steering](https://kiro.dev/docs/steering/) |
| `.kiro/skills/<name>/SKILL.md` | ✅ | [Agent Skills](https://kiro.dev/docs/skills/) |
| `.kiro/specs/<name>/tasks.md` | ✅ | [Specs](https://kiro.dev/docs/specs/) |
| bash + language runtimes + internet | ✅ | [Sandbox](https://kiro.dev/docs/web/sandbox/) |
| Built-in subagents | ✅ | [Subagents](https://kiro.dev/docs/custom-agents/subagents/) |
| `.kiro/hooks/*.json` | ❌ | [Hooks](https://kiro.dev/docs/hooks/) — Web listed unsupported |
| `.kiro/agents/*.json` (custom agents) | ❌ | [Custom agents](https://kiro.dev/docs/custom-agents/) |
| repo `.kiro/settings/mcp.json` | ❌ | [MCP config](https://kiro.dev/docs/mcp/configuration/) — use Settings → Agent |
| `~/.kiro/` global scope | ❌ | [Configuration](https://kiro.dev/docs/configuration/) — no local filesystem |

Two facts do most of the work:

**Steering with `inclusion: always` is injected into every interaction.** That is
the boot loader. Modes are `always`, `auto` (description-matched, needs `name` +
`description`), `fileMatch` (+ `fileMatchPattern`), and `manual` (`#name`), plus
`#[[file:path]]` to pull a live workspace file into a steering doc.

**Skills use progressive disclosure.** Only `name` + `description` sit in context
at startup; the body loads when a request matches; referenced files load only when
the instructions point at them ([Anthropic's Agent Skills
pattern](https://open.substack.com/pub/swirlai/p/agent-skills-progressive-disclosure)).
A large capability library therefore costs almost nothing until used — which is
exactly the property an OS needs for its program list.

## 2. Persistence: git is the only durable layer

The docs describe the Web sandbox lifecycle as provision → clone repos →
configure → execute → **tear down**
([Sandbox](https://kiro.dev/docs/web/sandbox/)), while
[cloud sessions](https://kiro.dev/docs/cloud-sessions/) say conversation history,
bound repos, and sandbox file state persist in the cloud, and that sessions are
deleted after 90 days. Those statements are never reconciled, and no snapshot
mechanism is documented.

Engineering conclusion: treat the filesystem as scratch and the git remote as
storage. Hence `bin/os save` after every durable decision, and a vault that lives
*inside* the clone at `brain/` rather than in any home or config directory.

Two persistence layers do exist beyond git, and both are worth using:

- **Cloud configuration** (`Settings → Cloud configuration`) syncs personal
  steering, skills, agents, and hooks into web sandboxes — the mechanism for a
  kernel that follows you into repos that don't contain it.
- **Memory** (`Settings → Memory`) stores per-account learnings from PR feedback
  ([Memory](https://kiro.dev/docs/web/memory/)). Useful, but not inspectable as
  files and not something you can structure — a complement to a vault, not a
  replacement.

## 3. The boot problem, and why steering beats a hook anyway

On IDE and CLI, a `SessionStart` hook is the clean answer: exit 0 and its stdout
is injected into context ([Hook actions](https://kiro.dev/docs/hooks/actions/)).
On Web, hooks don't run.

An `inclusion: always` steering file substitutes for it — and turns out to be more
robust for this purpose. A hook fires once; its output lives in the transcript and
can be dropped by context compaction on a long session. Always-included steering
is re-supplied every turn, so the boot rule survives compaction, `/compact`, and a
session resumed on another device.

This repo ships both, pointed at the same `bin/os boot` entry point. Cost of the
Web path: boot is instructed, not enforced. Written up in
`brain/decisions/2026-08-19 Steering as the boot loader.md`.

## 4. Loop engineering

The relevant prior art is Geoffrey Huntley's **Ralph loop**: run the agent in a
`while true`, re-feed the same prompt file each iteration, and let the filesystem
and git carry memory while each iteration starts with a clean context window
([howaiworks](https://howaiworks.ai/blog/geoffrey-huntley-ralph-agentic-coding-loop),
[Steve Kinney](https://github.com/stevekinney/stevekinney.net/blob/main/writing/the-ralph-loop.md),
[geocod.io](https://www.geocod.io/code-and-coordinates/2026-01-27-ralph-loops)).
"Loop engineering" is the broader framing: where prompt engineering optimizes one
message and context engineering optimizes one call's inputs, loop engineering
optimizes the control system that runs the agent repeatedly and escalates only
when stuck ([overview](https://linas.substack.com/p/loop-engineering-complete-guide)).

The adaptation Web forces: **an agent in a Web session cannot re-invoke itself.**
So the ledger becomes the loop counter and the session becomes the loop body —
`bin/os loop next` prints the fixed prompt plus the next unchecked step, and any
future session resumes from the file. Deterministic repetition still belongs in a
real shell loop (`until npm test; do ...`), which the sandbox runs fine.

For decomposable feature work, Kiro **specs** already provide a native task loop
with a dependency graph, parallel waves, and cross-session resume — use a spec for
"build this feature", a loop ledger for open-ended or maintenance work.

Genuinely unavailable: unattended overnight autonomy *inside* Web. There is no
cron and no daemon, and the sandbox dies with the task. Drive it from outside
(GitHub Actions on a schedule, or Kiro CLI locally in a `while` loop) if you want
that.

## 5. Second brain and Obsidian

An Obsidian vault is a folder of markdown with `[[wikilinks]]` — no plugin, no
API, no server needed for an agent to use it. That makes "the repo is the vault"
almost free, and it is a well-trodden pattern: markdown-first agent memory in
[agent-memory-vault](https://github.com/vscoder427/agent-memory-vault),
[AgentsOS](https://github.com/lsetiawan/AgentsOS),
[obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain),
[ReMe](https://github.com/agentscope-ai/ReMe) (markdown files with frontmatter and
wikilinks as memory nodes), plus write-ups on
[Obsidian + Claude Code architectures](https://www.mindstudio.ai/blog/ai-second-brain-claude-code-obsidian-architecture)
and [vault-as-AI-knowledge-base](https://www.billmongan.com/posts/2026/05/obsidian-ai-vault/).
Human round-trip sync is [Obsidian Git](https://github.com/Vinzent03/obsidian-git).

Kiro-specific prior art exists too and is worth reading:
[wilbur-labs/kiro-workspace](https://github.com/wilbur-labs/kiro-workspace)
(multi-agent workspace with shared context, learned memories, session recovery),
[TeiNam/kiro-with-harness](https://github.com/TeiNam/kiro-with-harness) (installer
for curated steering/hooks/agents/skills), and
[Auriti-Labs/kiro-memory](https://github.com/Auriti-Labs/kiro-memory)
(cross-session memory capture). Broader "agentic OS" templates:
[aporb/agentic-os](https://github.com/aporb/agentic-os),
[itseffi/agentic-os](https://github.com/itseffi/agentic-os),
[EvolvingAgentsLabs/skillos](https://github.com/EvolvingAgentsLabs/skillos)
(skills as programs), [agenticloop](https://github.com/bartoszarendt/agenticloop)
(markdown-first orchestrator/engineer roles with review loops).

Most of them assume a local CLI and a persistent home directory. The delta here is
building for a surface with **no hooks, no custom agents, and an ephemeral
filesystem** — which is why the boot loader is steering and the storage is git.

Retrieval: grep, not embeddings. At vault scale the structure — a hot `STATE.md`,
atomic notes, and a hand-built link graph — does the work a similarity search
would, without an index to keep fresh or a stale-index failure mode. Reasoning in
`brain/notes/Grep Beats Embeddings Here.md`; revisit at thousands of notes.

## 6. UI

Three, in order of usefulness:

1. **Obsidian** on `brain/` — graph, backlinks, search, mobile. The real UI.
2. **`docs/index.html`**, generated by `bin/os dash` — one self-contained file
   (working memory, loop progress, searchable notes, clickable wikilinks,
   journal). Serve it with GitHub Pages from `/docs`, since a dev server inside
   the sandbox isn't reachable from your browser.
3. **Kiro Web's read-only file explorer** — fine for spot checks, no rendering.

## 7. Verdict

| Wanted | Status |
|---|---|
| Persistent second brain across sessions | ✅ `brain/` in git, booted by steering |
| Same brain in every session, any device | ✅ repo clone + cloud config for cross-repo |
| Obsidian + UI | ✅ vault is Obsidian-native; static dashboard via Pages |
| Skills as loadable programs | ✅ `.kiro/skills/`, progressive disclosure |
| Loop engineering | ✅ ledger-driven; ⚠️ no unattended in-Web autonomy |
| Automatic boot enforced by platform | ⚠️ steering-instructed on Web; hook on IDE/CLI |
| Per-role models / tool restrictions | ❌ custom agents unavailable on Web |
| Cron / daemon / self-restart | ❌ needs an external driver |

The honest summary: everything asked for is achievable, and the two things that
aren't (platform-enforced boot, unattended autonomy) have external workarounds
rather than in-Web ones. Verified in this sandbox: `bin/os selftest` passes,
`boot` reconstructs full context in one call, `dash` renders, loop tick/status
round-trips. The one property that cannot be verified from inside a single
session is durability across teardown — that's steps 3 and 4 of
`brain/loops/harden-agentos.md`, and it's on you to confirm from a fresh session.
