"""Inference over an OpenAI-compatible endpoint.

Deliberately thin. The provider is three config values, so OpenRouter, OpenAI,
Anthropic-via-proxy, a Hermes API server, or a local ollama are all the same code
path. See brain/wiki/Model Access Is Not Transferable.md
"""
import json
import logging
from typing import AsyncGenerator, Dict, List

import httpx

from . import config

log = logging.getLogger("agentos.llm")

SYSTEM = """You are the assistant inside a personal second brain. You answer \
strictly from the supplied excerpts of the user's own vault.

Rules:
- Ground every claim in the excerpts. Cite as [n] using the excerpt numbers.
- If the excerpts do not answer the question, say so plainly and name what is \
missing. Never fill the gap from general knowledge without flagging it.
- The user wrote these notes. Do not explain their own ideas back to them at \
length — be direct and add the connection they asked for.
- Prefer the user's own vocabulary from the excerpts over synonyms.
- Brief and specific. No preamble."""


def build_prompt(question: str, hits: List[Dict]):
    blocks = []
    for i, h in enumerate(hits, 1):
        blocks.append("[%d] %s — %s (%s)\n%s"
                      % (i, h["title"], h["heading"], h["path"], h["text"]))
    context = "\n\n".join(blocks) if blocks else "(no excerpts retrieved)"
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user",
         "content": "Excerpts from my vault:\n\n%s\n\n---\nQuestion: %s"
                    % (context, question)},
    ]


def models() -> List[str]:
    """The fallback chain, in order of preference.

    LLM_MODEL may be a comma-separated list. This exists because free-tier models
    are rate-limited upstream constantly — the requested model returned 429 on
    three consecutive probes during deployment — and a second brain that cannot
    answer because one provider is busy is not much of a second brain.
    """
    return [m.strip() for m in config.LLM_MODEL.split(",") if m.strip()]


def configured() -> bool:
    return bool(config.LLM_API_KEY)


def _headers():
    h = {"Authorization": "Bearer %s" % config.LLM_API_KEY,
         "Content-Type": "application/json"}
    if "openrouter" in config.LLM_BASE_URL:
        # OpenRouter asks for these for attribution; harmless elsewhere.
        h["HTTP-Referer"] = config.BASE_URL or "http://localhost"
        h["X-Title"] = "AgentOS Second Brain"
    return h


async def _stream_one(client, model, messages):
    """Stream one model. Yields ('text', chunk) or ('fail', reason).

    Two shapes have to be handled. Most models put the answer in
    `delta.content`. Some reasoning models leave `content` empty for the whole
    response and put everything in `delta.reasoning` — measured on this key:
    `openrouter/free` and `minimax/minimax-m2.7:free` both returned empty content
    with a populated reasoning field. Reading only `content` renders a blank
    answer, which looks like a bug in this app rather than a quirk of the model.

    So reasoning is buffered separately and only used if no real content ever
    arrives. `reasoning.exclude` asks the provider to omit it where supported.
    """
    payload = {
        "model": model, "messages": messages, "stream": True,
        "temperature": 0.2,
        "reasoning": {"exclude": True},
    }
    url = "%s/chat/completions" % config.LLM_BASE_URL

    async with client.stream("POST", url, headers=_headers(), json=payload) as r:
        if r.status_code >= 400:
            body = (await r.aread()).decode("utf-8", "replace")
            try:
                raw = json.loads(body)["error"]["metadata"]["raw"][:120]
            except Exception:                        # noqa: BLE001
                raw = body[:120]
            yield "fail", "%d %s" % (r.status_code, raw)
            return

        content_seen = False
        reasoning_buf = []
        async for line in r.aiter_lines():
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                d = json.loads(data)["choices"][0].get("delta", {})
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            piece = d.get("content")
            if piece:
                content_seen = True
                yield "text", piece
            elif not content_seen:
                rz = d.get("reasoning") or d.get("reasoning_content")
                if rz:
                    reasoning_buf.append(rz)

        if not content_seen:
            if reasoning_buf:
                # The model's whole answer lived in the reasoning channel.
                yield "text", "".join(reasoning_buf)
            else:
                # An empty answer is a failure, not a result — fall through to
                # the next model rather than showing the user a blank panel.
                yield "fail", "empty response"


async def stream(messages: List[Dict]) -> AsyncGenerator[str, None]:
    """Yield answer text, trying each model in the chain until one produces
    something. Errors are yielded as text rather than raised, so the UI always
    shows what went wrong instead of spinning forever."""
    if not configured():
        yield "[no inference key configured — set OPENROUTER_API_KEY in server/.env]"
        return

    chain = models()
    problems = []

    async with httpx.AsyncClient(timeout=config.LLM_TIMEOUT) as client:
        for i, model in enumerate(chain):
            produced = False
            try:
                async for kind, val in _stream_one(client, model, messages):
                    if kind == "text":
                        produced = True
                        yield val
                    else:
                        problems.append("%s: %s" % (model, val))
                        log.warning("model %s unusable (%s)", model, val)
                        break
                if produced:
                    if i:
                        log.info("answered by fallback model %s", model)
                    return
            except httpx.TimeoutException:
                problems.append("%s: timed out after %ss" % (model, config.LLM_TIMEOUT))
            except Exception as e:                   # noqa: BLE001
                problems.append("%s: %s" % (model, e))
                log.exception("stream failed on %s", model)

    yield ("[no model in the chain could answer]\n\n" +
           "\n".join("- %s" % p for p in problems))
