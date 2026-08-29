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


async def stream(messages: List[Dict]) -> AsyncGenerator[str, None]:
    """Yield content deltas. Errors are yielded as text, not raised, so the UI
    always shows the user what went wrong instead of a dead spinner."""
    if not configured():
        yield "[no inference key configured — set OPENROUTER_API_KEY in server/.env]"
        return

    payload = {"model": config.LLM_MODEL, "messages": messages,
               "stream": True, "temperature": 0.2}
    url = "%s/chat/completions" % config.LLM_BASE_URL

    try:
        async with httpx.AsyncClient(timeout=config.LLM_TIMEOUT) as client:
            async with client.stream("POST", url, headers=_headers(),
                                     json=payload) as r:
                if r.status_code >= 400:
                    body = (await r.aread()).decode("utf-8", "replace")[:400]
                    log.warning("llm %s: %s", r.status_code, body)
                    yield "[provider error %d] %s" % (r.status_code, body)
                    return
                async for line in r.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        delta = (json.loads(data)["choices"][0]
                                 .get("delta", {}).get("content"))
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
                    if delta:
                        yield delta
    except httpx.TimeoutException:
        yield "\n[timed out after %ss]" % config.LLM_TIMEOUT
    except Exception as e:                          # noqa: BLE001
        log.exception("llm stream failed")
        yield "\n[inference failed: %s]" % e
