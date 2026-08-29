# Can an AI agent carry a persistent OS? — findings

Question: can an AI coding agent carry a persistent second brain, an
Obsidian-compatible vault, a UI, loop engineering, and skills across every session —
not just within one — without binding itself to a single vendor?

**Yes.** Not as a plugin or a background process, but as *repo-resident markdown plus a
boot convention*. The build in this repo is the answer; below is what the research
established and where the hard edges are.

*Sources are linked inline. Summarized and paraphrased, not quoted.*

## 1. Audit your harness before you design for it

The single constraint that decides the architecture is **which config surface your
harness actually loads** — and the failure mode is silent. An unsupported config file
does not error; it simply never loads, and you debug the wrong layer for an hour.

Hosted (browser/cloud) surfaces and local (IDE/CLI) surfaces of the *same* product
routinely differ. Audit rather than assume:

| Primitive | Typical hosted | Typical local | What it buys you |
|---|---|---|---|
| always-on instruction file | ✅ | ✅ | the kernel / boot loader |
| skills or reusable procedures | ✅ | ✅ | SOPs as commands |
| shell + runtimes + internet | ✅ | ✅ | the escape hatch for everything else |
| session-start hook | ❌ | ✅ | boot becomes *enforced*, not instructed |
| scheduler / cron | ❌ | ✅ | routines that fire with the laptop shut |
| long-lived daemon | ❌ | ✅ | anything surviving logout |
| custom sub-agents | inconsistent | inconsistent | per-role tools and model routing |
| repo-level MCP config | inconsistent | usually ✅ | connectors that travel with the project |
| user/global config scope | inconsistent | ✅ | a brain that follows you across repos |
| filesystem durability | **assume ❌** | ✅ | — |

Two properties do most of the work wherever you are:

**An always-included instruction file is injected into every interaction.** That is the
boot loader. Keep it small and imperative — it should contain the instruction to fetch
knowledge, never the knowledge itself.

**Skills load by progressive disclosure.** Typically only `name` + `description` sit in
context at startup; the body loads when a request matches, and referenced files load only
when the instructions point at them ([the Agent Skills
pattern](https://open.substack.com/pub/swirlai/p/agent-skills-progressive-disclosure)). So
a large capability library costs almost nothing until used — exactly the property an OS
needs for its program list.

**The convergence worth betting on:** [`AGENTS.md`](https://agents.md/) has become a
cross-vendor convention for the instruction file, read natively by a growing set of tools.
Writing the kernel there and *generating* vendor bindings from it (see `adapters/`) is the
difference between porting in an afternoon and rewriting.

## 2. Persistence: git is the only durable layer

Hosted harnesses describe a sandbox lifecycle of provision → clone → configure → execute →
**tear down**, while simultaneously claiming session file state persists in the cloud, and
expiring sessions on a timer regardless. Those claims are rarely reconciled and a snapshot
mechanism is rarely documented.

Engineering conclusion: **treat the filesystem as scratch and the git remote as storage.**
Hence `bin/os save` after every durable decision, and a vault that lives *inside* the clone
at `brain/` rather than in any home or config directory.

Vendor-side persistence layers (synced personal config, account-level "memory" learned from
your feedback) are worth using where they exist, with one caveat: they are not inspectable
as files and not structurable. A complement to a vault, never a replacement — you cannot
diff them, review them in a PR, or read them in five years without the software that wrote
them.

## 3. The boot problem, and why an always-on file beats a hook anyway

Where session hooks exist they are the clean answer: exit 0 and stdout is injected into
context. Where they don't, an always-included instruction file substitutes — and turns out
to be *more* robust for this particular job.

A hook fires once; its output lives in the transcript and can be dropped by context
compaction on a long session. An always-included file is re-supplied every turn, so the
boot rule survives compaction, an explicit compact, and a session resumed on another
device.

This repo ships both, pointed at the same `bin/os boot` entry point. Cost of the
instruction-file path: boot is instructed, not enforced. Written up in
`brain/decisions/2026-08-19 Steering as the boot loader.md`.

## 4. Loop engineering

The relevant prior art is Geoffrey Huntley's **Ralph loop**: run the agent in a
`while true`, re-feed the same prompt file each iteration, and let the filesystem and git
carry memory while each iteration starts with a clean context window
([howaiworks](https://howaiworks.ai/blog/geoffrey-huntley-ralph-agentic-coding-loop),
[Steve Kinney](https://github.com/stevekinney/stevekinney.net/blob/main/writing/the-ralph-loop.md),
[geocod.io](https://www.geocod.io/code-and-coordinates/2026-01-27-ralph-loops)).

"Loop engineering" is the broader framing: where prompt engineering optimizes one message
and context engineering optimizes one call's inputs, loop engineering optimizes the control
system that runs the agent repeatedly and escalates only when stuck
([overview](https://linas.substack.com/p/loop-engineering-complete-guide)).

The adaptation a hosted surface forces: **an agent in a hosted session cannot re-invoke
itself.** So the ledger becomes the loop counter and the session becomes the loop body —
`bin/os loop next` prints the fixed goal plus the next unchecked step, and any future
session resumes from the file. Deterministic repetition still belongs in a real shell loop
(`until npm test; do ...`).

Where a harness ships a native task system (specs, plan files, dependency-graphed task
lists), prefer it for decomposable feature work and keep loop ledgers for open-ended or
maintenance work. Never run both for the same work — two sources of truth about "what's
next" is worse than either.

Genuinely unavailable on hosted surfaces: unattended overnight autonomy. No cron, no daemon,
sandbox dies with the task. Drive it from outside — a scheduled CI job, or the always-on box
in `deploy/`.

## 5. Second brain and Obsidian

An Obsidian vault is a folder of markdown with `[[wikilinks]]` — no plugin, no API, no server
needed for an agent to use it. That makes "the repo is the vault" almost free, and it is a
well-trodden pattern: markdown-first agent memory in
[agent-memory-vault](https://github.com/vscoder427/agent-memory-vault),
[AgentsOS](https://github.com/lsetiawan/AgentsOS),
[obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain),
[ReMe](https://github.com/agentscope-ai/ReMe) (markdown with frontmatter and wikilinks as
memory nodes), plus write-ups on
[Obsidian + agent architectures](https://www.mindstudio.ai/blog/ai-second-brain-claude-code-obsidian-architecture)
and [vault-as-AI-knowledge-base](https://www.billmongan.com/posts/2026/05/obsidian-ai-vault/).
Human round-trip sync is [Obsidian Git](https://github.com/Vinzent03/obsidian-git).

Broader "agentic OS" templates worth reading:
[aporb/agentic-os](https://github.com/aporb/agentic-os),
[itseffi/agentic-os](https://github.com/itseffi/agentic-os),
[EvolvingAgentsLabs/skillos](https://github.com/EvolvingAgentsLabs/skillos) (skills as
programs), [agenticloop](https://github.com/bartoszarendt/agenticloop) (markdown-first
orchestrator/engineer roles with review loops).

Most assume a local CLI and a persistent home directory. The delta here is building for a
surface with **no hooks, no custom agents, and an ephemeral filesystem** — which is why the
boot loader is an instruction file and the storage is git.

### The three-layer vault

Capture, knowledge, and artifacts have different quality bars and different lifetimes, which
is why they are three directories: `raw/` (capture freely, never cite), `wiki/` (atomic,
rewritten in place), `output/` (immutable once shipped). Promotion is *rewriting*, not
moving — the discipline is what keeps a vault from degenerating into a landfill of
half-read clippings.

## 6. Retrieval: keyword-first, hybrid when a human is looking

Original finding: grep beats embeddings at this scale. The structure — a hot `STATE.md`,
atomic notes, a hand-built link graph — does the work a similarity search would, with no
index to keep fresh and no stale-index failure mode. Grep's failure mode is honest: zero
hits means zero hits.

That note named its own revisit condition, and it fired (2026-08-29). Two things changed:

1. A **human** browsing a visual second brain searches by half-remembered concept, which has
   no reliable keyword.
2. A **RAG answer** needs passages ranked across the whole vault — the job keyword search is
   worst at.

So `server/` runs hybrid retrieval, chosen to honour the original constraint rather than
abandon it:

| Choice | Why |
|---|---|
| SQLite **FTS5 + BM25** | keyword half with zero new dependency; SQLite ships it |
| **sqlite-vec** | vector half as a *file*, not a service — no daemon to babysit |
| quantised MiniLM, ONNX, CPU | ~90 MB, runs on 1 GB RAM; no GPU, no API call to embed |
| **Reciprocal Rank Fusion** | keyword hits still surface when embeddings whiff, and vice versa |
| index rebuilt from markdown | disposable by construction; `rm index.db` is a valid repair |

The load-bearing rule is unchanged: **markdown is truth, the index is a cache.** `bin/os
recall` still greps, because an agent mid-task wants a deterministic answer. Agents recall;
humans browse.

## 7. Models: keep the provider one variable away

Model access is **not transferable between vendors**. Agent CLIs authenticate against their
own subscription, their own API key, or a cloud reseller they have a deal with — and vendor
terms generally forbid third parties exposing a consumer login to other products. So
"use my subscription from tool A inside tool B" is a licensing boundary, not a missing
feature.

Two practical findings:

- **Open-source agent ≠ free inference.** [Hermes Agent](https://hermes-agent.nousresearch.com/docs/)
  is MIT-licensed with no paid tiers, but it is a *client*: its docs state you need at least
  one [configured provider](https://hermes-agent.nousresearch.com/docs/integrations/providers/)
  to use it, and the recommended gateway is a paid subscription. Conflating the two leads to
  paying for the wrong thing.
- **The OpenAI-compatible chat-completions shape is the interop layer.** Nearly every
  provider, aggregator, and local server speaks it — including Hermes, which exposes its own
  [OpenAI-compatible API server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server).
  Target that shape and the provider becomes `base_url` + `api_key` + `model`.

This repo therefore defaults to an aggregator's free tier, and swapping to a paid provider,
a different lab, or a local `ollama` is an env-var edit. Reasoning in
`brain/wiki/Model Access Is Not Transferable.md`.

## 8. UI

Four, in order of usefulness:

1. **Obsidian** on `brain/` — graph, backlinks, search, mobile. The real editing UI.
2. **`server/` orbit map** — the vault as concentric ARMS rings with hybrid search and cited
   RAG answers. This is the browsing UI, and the one worth showing other people.
3. **`docs/index.html`**, generated by `bin/os dash` — one self-contained static file, served
   free from GitHub Pages. No server required, so it works when nothing else does.
4. A harness's read-only file explorer — fine for spot checks, no rendering.

A note on hosting the interactive one: a dev server inside an agent sandbox is not reachable
from your browser, which is why the always-on box exists. TLS via
[Tailscale Funnel](https://tailscale.com/kb/1223/funnel) gives a real certificate on a stable
hostname with no domain purchase and no inbound port opened.

## 9. Verdict

| Wanted | Status |
|---|---|
| Persistent second brain across sessions | ✅ `brain/` in git, booted by the kernel |
| Same brain in every session, any device | ✅ repo clone + global kernel for repo-less sessions |
| Works with any agent / harness | ✅ `AGENTS.md` + generated bindings in `adapters/` |
| Works with any model / provider | ✅ OpenAI-compatible shape, provider is one env var |
| Obsidian + a real UI | ✅ vault is Obsidian-native; orbit UI + static dashboard |
| Skills as loadable programs | ✅ `config/skills/`, progressive disclosure |
| Semantic search over the vault | ✅ hybrid BM25 + vectors, index disposable |
| Loop engineering | ✅ ledger-driven; ⚠️ no unattended autonomy inside a hosted session |
| Automatic boot enforced by platform | ⚠️ instructed on hosted; real hook on local |
| Per-role models / tool restrictions | ⚠️ depends entirely on the harness |
| Cron / daemon / self-restart | ✅ on the always-on box; ❌ inside a hosted sandbox |

The honest summary: everything asked for is achievable, and the two things that aren't
platform-native (enforced boot, unattended autonomy) have external answers — a session hook
locally, and a $10/month box for everything else.

Verified in-sandbox: `bin/os selftest` passes including the binding-drift and broken-wikilink
guards (both confirmed by negative test), `boot` reconstructs full context in one call, `dash`
renders, loop tick/status round-trips, and the orbit UI was loaded headless and screenshotted.

The one property that cannot be verified from inside a single session is durability across
teardown — steps 4-6 of `brain/loops/harden-agentos.md`, and confirming it is on you from a
fresh session.
