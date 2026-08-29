"""Inference over an OpenAI-compatible endpoint.

Deliberately thin. The provider is three settings — base URL, key, model — so
OpenRouter, OpenAI, Together, a local Ollama at /v1 and your own proxy are all
the same code path. See brain/wiki/Model Access Is Not Transferable.md

Two things this does beyond "post and read the stream":

- **Yields structured events, not strings.** The caller needs to distinguish a
  token from a cost report from a failure. A generator of bare strings forces the
  UI to guess, which is how you end up rendering "[provider error 429]" as if the
  model had said it.
- **Routes around a dead model.** OpenRouter takes a `models` array and picks the
  first one that answers; everything else gets the same behaviour client-side.
  A free-tier model that rate-limits mid-sentence is the normal case, not the
  exceptional one.
"""
import json
import logging
import time
from typing import AsyncGenerator, Dict, List, Optional

import httpx

from . import config, settings

log = logging.getLogger("agentos.llm")

_models_cache = {"at": 0.0, "key": "", "data": []}
MODELS_TTL = 600.0


# ------------------------------------------------------------------- prompting

def build_prompt(question: str, hits: List[Dict], system: str = None):
    blocks = []
    for i, h in enumerate(hits, 1):
        blocks.append("[%d] %s — %s (%s)\n%s"
                      % (i, h["title"], h["heading"], h["path"], h["text"]))
    context = "\n\n".join(blocks) if blocks else "(no excerpts retrieved)"
    return [
        {"role": "system", "content": system or settings.get("LLM_SYSTEM_PROMPT")},
        {"role": "user",
         "content": "Excerpts from my vault:\n\n%s\n\n---\nQuestion: %s"
                    % (context, question)},
    ]


def configured() -> bool:
    return bool(settings.get("LLM_API_KEY"))


def is_openrouter() -> bool:
    return "openrouter" in settings.get("LLM_BASE_URL")


def _headers():
    h = {"Authorization": "Bearer %s" % settings.get("LLM_API_KEY"),
         "Content-Type": "application/json"}
    if is_openrouter():
        # OpenRouter asks for these for attribution; harmless elsewhere.
        h["HTTP-Referer"] = config.BASE_URL or "http://localhost"
        h["X-Title"] = "AgentOS Second Brain"
    return h


def _chain(model: Optional[str]) -> List[str]:
    """The model to try, then the fallbacks, de-duplicated and order-preserving."""
    primary = (model or settings.get("LLM_MODEL") or "").strip()
    out = [primary] if primary else []
    for m in settings.get("LLM_FALLBACK_MODELS"):
        if m and m not in out:
            out.append(m)
    return out or [""]


def _batches(chain: List[str]) -> List[List[str]]:
    """Group the fallback chain into what one request can carry.

    OpenRouter routes server-side and accepts at most 3 models per request, so a
    longer chain is sent as successive batches of 3 rather than being silently
    truncated — previously `attempts = chain[:1]` meant anything past the third
    model was configured, displayed, and never actually tried.

    Every other provider takes one model per request.
    """
    if is_openrouter() and len(chain) > 1:
        return [chain[i:i + 3] for i in range(0, len(chain), 3)]
    return [[m] for m in chain]


def _payload(messages, model, *, stream, temperature=None, max_tokens=None,
             chain=None):
    body = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "temperature": settings.get("LLM_TEMPERATURE")
        if temperature is None else float(temperature),
    }

    cap = settings.get("LLM_MAX_TOKENS") if max_tokens is None else int(max_tokens)
    if cap:
        body["max_tokens"] = cap

    effort = settings.get("LLM_REASONING_EFFORT")
    if effort and effort != "off":
        body["reasoning"] = {"effort": effort}

    if is_openrouter():
        # Server-side routing: OpenRouter walks the list itself, which is both
        # faster and cheaper than us retrying after a failed round trip.
        #
        # Belt and braces: _batches() already limits this to 3, but OpenRouter
        # rejects a longer array outright with 400 "'models' array must have 3
        # items or fewer" — a primary plus three fallbacks failed every request
        # rather than degrading — so the cap is enforced here too.
        if chain and len(chain) > 1:
            body["models"] = chain[:3]
        body["usage"] = {"include": True}
    elif stream:
        body["stream_options"] = {"include_usage": True}

    return body


def _usage_event(raw: dict, model: str) -> dict:
    """Normalise a provider usage block. `cost` is OpenRouter-specific and simply
    absent elsewhere, which the UI renders as tokens-only."""
    if not isinstance(raw, dict):
        return {}
    ev = {"type": "usage", "model": model,
          "prompt_tokens": raw.get("prompt_tokens"),
          "completion_tokens": raw.get("completion_tokens"),
          "total_tokens": raw.get("total_tokens")}
    if raw.get("cost") is not None:
        ev["cost"] = raw["cost"]
    return ev


def _explain(status: int, body: str) -> str:
    """Turn a provider status into something the person reading it can fix."""
    hint = {
        401: "The API key was rejected. Check it in Settings.",
        402: "The account is out of credit.",
        403: "The key is not allowed to use this model.",
        404: "That model id does not exist at this provider.",
        429: "Rate limited. Free-tier models do this; add a fallback model or "
             "wait.",
        502: "The provider could not reach the upstream model.",
        503: "The model is temporarily unavailable.",
    }.get(status, "")
    detail = body.strip()[:300]
    try:
        parsed = json.loads(body)
        detail = (parsed.get("error") or {}).get("message") or detail
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return ("%s %s" % (hint, detail)).strip() or ("provider error %d" % status)


# ---------------------------------------------------------------- streaming

async def stream(messages: List[Dict], *, model: str = None,
                 temperature: float = None,
                 max_tokens: int = None) -> AsyncGenerator[dict, None]:
    """Yield event dicts: model, delta, usage, error.

    Failures are yielded rather than raised, because the caller is an SSE
    response that has already committed its headers — an exception here shows the
    user a dead spinner instead of a reason.
    """
    if not configured():
        yield {"type": "error",
               "message": "No inference key. Add one in Settings — search still "
                          "works without it."}
        return

    chain = _chain(model)
    url = "%s/chat/completions" % settings.get("LLM_BASE_URL")
    timeout = settings.get("LLM_TIMEOUT")

    # OpenRouter walks the chain itself, so one attempt is the whole chain there.
    attempts = _batches(chain)
    last_error = None

    for attempt, batch in enumerate(attempts):
        mdl = batch[0]
        payload = _payload(messages, mdl, stream=True, temperature=temperature,
                           max_tokens=max_tokens, chain=batch)
        produced = False
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, headers=_headers(),
                                         json=payload) as r:
                    if r.status_code >= 400:
                        body = (await r.aread()).decode("utf-8", "replace")
                        last_error = _explain(r.status_code, body)
                        log.warning("llm %s on %s: %s", r.status_code, mdl,
                                    body[:200])
                        continue                       # try the next model

                    yield {"type": "model", "id": mdl}
                    async for line in r.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            obj = json.loads(data)
                        except json.JSONDecodeError:
                            continue

                        if obj.get("usage"):
                            ev = _usage_event(obj["usage"],
                                              obj.get("model") or mdl)
                            if ev:
                                yield ev

                        choices = obj.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}

                        # Reasoning models emit their scratchpad on a separate
                        # key. Surfaced as its own event so the UI can fold it
                        # away instead of mixing it into the answer.
                        think = delta.get("reasoning")
                        if think:
                            yield {"type": "reasoning", "text": think}
                        text = delta.get("content")
                        if text:
                            produced = True
                            yield {"type": "delta", "text": text}
            if produced:
                return
            if not last_error:
                last_error = "The model returned an empty response."
        except httpx.TimeoutException:
            last_error = "Timed out after %ss." % timeout
            log.warning("llm timeout on %s", mdl)
        except httpx.HTTPError as e:
            last_error = "Could not reach %s (%s)" % (
                settings.get("LLM_BASE_URL"), e.__class__.__name__)
            log.warning("llm transport error on %s: %s", mdl, e)
        except Exception as e:                          # noqa: BLE001
            last_error = "Inference failed: %s" % e
            log.exception("llm stream failed on %s", mdl)

        if attempt + 1 < len(attempts):
            yield {"type": "notice",
                   "message": "%s failed — trying %s" % (mdl, attempts[attempt + 1])}

    yield {"type": "error", "message": last_error or "Inference failed."}


async def complete(messages: List[Dict], *, model: str = None,
                   temperature: float = None, max_tokens: int = None) -> Dict:
    """Non-streaming call. Returns {text, model, usage, error}.

    The gauntlet critic uses this: its verdict is a small structured answer that
    nobody needs to watch arrive token by token.
    """
    if not configured():
        return {"text": "", "error": "No inference key configured."}

    chain = _chain(model)
    url = "%s/chat/completions" % settings.get("LLM_BASE_URL")
    attempts = _batches(chain)
    last_error = None

    for batch in attempts:
        mdl = batch[0]
        payload = _payload(messages, mdl, stream=False, temperature=temperature,
                           max_tokens=max_tokens, chain=batch)
        try:
            async with httpx.AsyncClient(timeout=settings.get("LLM_TIMEOUT")) as c:
                r = await c.post(url, headers=_headers(), json=payload)
            if r.status_code >= 400:
                last_error = _explain(r.status_code, r.text)
                log.warning("llm %s on %s: %s", r.status_code, mdl, r.text[:200])
                continue
            obj = r.json()
            msg = (obj.get("choices") or [{}])[0].get("message") or {}
            return {"text": msg.get("content") or "",
                    "model": obj.get("model") or mdl,
                    "usage": _usage_event(obj.get("usage") or {},
                                          obj.get("model") or mdl),
                    "error": None}
        except httpx.TimeoutException:
            last_error = "Timed out after %ss." % settings.get("LLM_TIMEOUT")
        except Exception as e:                          # noqa: BLE001
            last_error = "Inference failed: %s" % e
            log.exception("llm complete failed on %s", mdl)

    return {"text": "", "error": last_error or "Inference failed."}


# ------------------------------------------------------------ model catalogue

def _norm_model(m: dict) -> dict:
    """One shape for every provider's /models response.

    OpenRouter is rich (context length, per-token price, modality); OpenAI
    returns little more than an id. Normalising here means the model picker does
    not need a branch per provider.
    """
    pricing = m.get("pricing") or {}

    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    prompt = _num(pricing.get("prompt"))
    completion = _num(pricing.get("completion"))
    mid = m.get("id") or m.get("name") or ""
    arch = m.get("architecture") or {}
    return {
        "id": mid,
        "name": m.get("name") or mid,
        "context": m.get("context_length") or m.get("context") or
                   (m.get("top_provider") or {}).get("context_length"),
        # Per-token from the API; per-million is what humans compare.
        "prompt_per_m": round(prompt * 1_000_000, 4) if prompt is not None else None,
        "completion_per_m": round(completion * 1_000_000, 4)
                            if completion is not None else None,
        "free": mid.endswith(":free") or (prompt == 0 and completion == 0),
        "modalities": arch.get("input_modalities") or [],
        "reasoning": bool(m.get("supported_parameters") and
                          "reasoning" in (m.get("supported_parameters") or [])),
        "description": (m.get("description") or "")[:400],
    }


async def list_models(force: bool = False) -> Dict:
    """The provider's catalogue, cached for ten minutes.

    Cached because the model picker opens on every keystroke and the catalogue
    changes daily at best. Keyed on base URL + key so switching provider or
    rotating a key does not serve the previous provider's list.
    """
    base = settings.get("LLM_BASE_URL")
    key = "%s|%s" % (base, settings.get("LLM_API_KEY")[-6:])
    fresh = (time.time() - _models_cache["at"]) < MODELS_TTL
    if not force and fresh and _models_cache["key"] == key and _models_cache["data"]:
        return {"models": _models_cache["data"], "cached": True, "provider": base}

    headers = _headers()
    if not settings.get("LLM_API_KEY"):
        # OpenRouter serves its catalogue unauthenticated, which makes the picker
        # useful before a key is ever entered.
        headers.pop("Authorization", None)

    try:
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.get("%s/models" % base, headers=headers)
        if r.status_code >= 400:
            return {"models": _models_cache["data"],
                    "error": _explain(r.status_code, r.text), "provider": base}
        payload = r.json()
        raw = payload.get("data") if isinstance(payload, dict) else payload
        models = [_norm_model(m) for m in (raw or []) if isinstance(m, dict)]
        models = [m for m in models if m["id"]]
        models.sort(key=lambda m: m["id"])
        _models_cache.update(at=time.time(), key=key, data=models)
        return {"models": models, "cached": False, "provider": base}
    except Exception as e:                              # noqa: BLE001
        log.warning("model list failed: %s", e)
        return {"models": _models_cache["data"],
                "error": "Could not reach %s (%s)" % (base, e.__class__.__name__),
                "provider": base}
