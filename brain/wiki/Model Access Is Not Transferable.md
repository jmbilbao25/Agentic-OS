---
created: 2026-08-19
updated: 2026-08-29
tags: [auth, licensing, portability, verified]
---

# Model Access Is Not Transferable

A subscription to one vendor's agent product does not grant model access to a
different vendor's agent product, even when both sit on top of the same underlying
model. This is a licensing boundary, not a missing feature, and no amount of config
gets around it.

Verified the hard way: installing a vendor's coding CLI works fine, and then it asks
to log in — and the only credentials it accepts are that vendor's own. A subscription
purchased elsewhere is not one of them.

## What agent CLIs actually authenticate against

Almost every one accepts exactly three categories:

1. **That vendor's own subscription**, via OAuth.
2. **That vendor's own API key**, from their console.
3. **A cloud reseller** the vendor has a deal with — Bedrock, Vertex, Foundry.

An entitlement bought from anyone outside those three is not convertible. Vendor terms
generally *forbid* third parties from exposing their consumer login or rate limits to
other products, so anything that appears to bridge two ecosystems is either violating
terms or is a paid gateway quietly reselling tokens at a markup.

## The design consequence

Do not build an OS that assumes a particular provider's auth. Build it so the provider
is one environment variable.

- Talk to models over the **OpenAI-compatible chat-completions shape**. It is the de
  facto interop layer; nearly every provider and every local server speaks it.
- Keep `base_url`, `api_key`, and `model` in config, never in code.
- Aggregators (OpenRouter and similar) exist precisely to make the provider swappable,
  and their free tiers are enough to prove a system works before you pay anyone.
- A local server (`ollama`, `vllm`, `llama.cpp`) is the same shape again, so "run it
  offline" costs a URL change rather than a rewrite.

That is the whole mitigation. When it is one variable, a licensing wall stops being an
architectural problem and becomes a procurement preference.

## The trap to name out loud

Wanting *one specific branded tool* is almost always wanting one of its capabilities:
an agent that remembers, enforced session hooks, or unattended loops. All three are
obtainable from several tools, and from this repo. Pick by capability, not by the brand
on it — otherwise you end up paying twice for the same model and calling it
integration.

Related: [[Local Runtime Closes The Gaps]], [[Harness Capability Matrix]]
