---
created: 2026-08-19
tags: [claude-code, auth, verified]
---

# Claude Code Cannot Use Kiro Models

Tested directly: `npm i -g @anthropic-ai/claude-code` installs fine (v2.1.235) and
then says `Not logged in · Please run /login`. There is no supported way to point it
at a Kiro subscription.

## What Claude Code will authenticate against

- A Claude Pro or Max subscription (OAuth login)
- An Anthropic Console API key (`ANTHROPIC_API_KEY`, `sk-ant-…`)
- Claude for Teams/Enterprise with SSO
- Cloud providers: Amazon Bedrock, Google Vertex AI, Microsoft Foundry

That's the complete list. Kiro's entitlement is not any of them — it isn't an
Anthropic-compatible endpoint, and Anthropic's Agent SDK documentation states
plainly that third-party developers are not permitted to offer claude.ai login or
rate limits for their products. So "use my Kiro Opus quota in Claude Code" is not a
missing feature, it's a licensing boundary. Anything that appears to do it is
either a proxy that violates terms or a paid gateway reselling tokens.

## The two legitimate ways to run Claude Code locally

1. **Your own Anthropic account** — Pro/Max subscription or a Console API key.
2. **Your own AWS Bedrock access** — `CLAUDE_CODE_USE_BEDROCK=1` plus AWS
   credentials. Kiro is an AWS product, but a Kiro subscription is *not* Bedrock
   model access; that's separate provisioning and separate billing.

## Why you don't need it

`kiro-cli` already runs Kiro's models — Opus included — locally on your machine
under the subscription you already pay for, and unlike Kiro Web it supports hooks,
custom agents, global `~/.kiro/` config, and real shell loops.
[[Kiro Crew Is The Local OS]] then wraps `kiro-cli` over ACP and adds the
scheduler, daemon, memory, and dashboard.

Wanting "Claude Code specifically" is usually wanting one of: a local agent that
remembers (Crew does it better), enforced session hooks (Kiro CLI has them), or
unattended loops (`kirocrew cron` and `kirocrew run`). Pick the tool by the
capability, not by the brand on it.

Related: [[Kiro Crew Is The Local OS]], [[Kiro Web Capability Matrix]]
