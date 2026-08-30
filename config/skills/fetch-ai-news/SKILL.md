---
name: fetch-ai-news
description: Fetch the latest AI news radar and distill it into a brief. Use when the user says: fetch AI news, run radar, get latest AI news, ai news brief, brief me on AI, what's new in AI today, run the AI radar. Runs bin/os brief (radar + distill) and reports the digest.
---

# Fetch AI News — radar + brief

One-shot automation: captures today's signal from 6 keyless sources and runs the LLM triage.

## Trigger phrases
- "fetch AI news"
- "run radar"
- "get latest AI news"
- "ai news brief"
- "brief me on AI"
- "what's new in AI today"
- "run the AI radar"

## Procedure

```bash
# From the AgentOS root
bin/os brief
```

That command runs:
1. `bin/os radar` — gathers from Hugging Face papers/models, arXiv, GitHub trending, Hacker News, Lobsters → writes dated file to `brain/raw/`
2. `bin/os distill` — LLM triage of the newest capture → writes digest to `brain/output/`

## What to report back

- The **digest** printed by `brief` (Worth your time / Worth knowing / Patterns / Skip)
- Path to the raw capture: `brain/raw/YYYY-MM-DD AI radar.md`
- Path to the output digest: `brain/output/YYYY-MM-DD AI digest.md`
- Item counts and any feed failures

## After a successful run

```bash
bin/os save "AI news brief $(date +%F)"
```
Commits the new raw + output files and pushes (if origin exists).

## Guardrails

- **Do not run `radar` alone** unless the user explicitly asks for raw capture only. The value is the distilled brief.
- **Do not promote raw → wiki automatically.** The vault boundary exists for a reason — promotion is a deliberate human (or explicitly instructed) act.
- **If every feed fails**, report the failure and do not write empty files. `radar` exits non-zero in this case; `brief` will surface it.
- **Rate limits**: the LLM call in `distill` uses the configured model (currently OpenRouter free tier). If it 429s, report the error and the raw capture path — the user can re-run `distill` later.
- **Dry run**: `bin/os radar --dry` prints the capture without writing. Useful for preview.

## Escape hatch

This skill does NOT apply when:
- The user wants a **topic-specific deep dive** (use `bin/os research "<topic>"` instead — documented in the `research` skill)
- The user wants to **browse the web UI** (the server at `https://jm-agentic-os-13-218-239-165.sslip.io` has interactive search)
- The user wants to **schedule it** — that is a server concern (systemd timer at 06:15 daily), not an agent skill

## Reference
- Sources & provenance: `config/skills/research/sources.md`
- Triage grades: `config/skills/research/triage.md`
- Vault layers: `config/skills/second-brain/SKILL.md`
