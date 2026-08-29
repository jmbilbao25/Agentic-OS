"""The gauntlet loop: build, criticise blind, loop until ours wins.

Adapted from the gauntlet-loop skill by robonuggets (CC BY 4.0) —
https://github.com/robonuggets/gauntlet-loop — and wired into the vault so the
builder writes from your own notes rather than from general knowledge.

The whole value is in the comparison, so the four things that break a gauntlet
loop are the four things this file is built around:

- **A vague bar.** The bar here is a real artifact — text you pasted or a page we
  fetched. If we cannot obtain it, we refuse to start rather than let the critic
  invent a comparison and approve everything.
- **The builder judging its own work.** Builder and critic are separate calls
  with separate message lists, and can be separate models. The critic never sees
  the goal's history, the round number, or how hard the builder tried.
- **A soft critic.** The critic gets a binary job — A or B — not a score out of
  ten. Scores drift upward every round; a forced choice does not. It is also
  required to name exactly one gap, because "several issues" is how a critic
  avoids committing.
- **Exiting after N rounds.** The exit is winning the blind comparison. The round
  ceiling is a cost stop, and when it triggers the result is reported as a loss,
  not dressed up as a finish.

Blindness is real, not decorative: which of A and B is ours is chosen per round
by secrets.choice, and the mapping never leaves this module until after the
verdict is parsed.
"""
import asyncio
import html
import ipaddress
import json
import logging
import re
import secrets
import socket
from typing import AsyncGenerator, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from . import llm, search, settings

log = logging.getLogger("agentos.gauntlet")

MAX_ARTIFACT = 14000        # characters of ours or the bar sent to the critic
MAX_FETCH = 400_000         # bytes pulled from a bar URL

_TAGS = re.compile(r"<(script|style|noscript|template)\b.*?</\1>", re.S | re.I)
_BLOCK = re.compile(r"</(p|div|section|article|h[1-6]|li|tr|blockquote|pre)>", re.I)
_ANYTAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n{3,}")


# ------------------------------------------------------------------ the bar

def html_to_text(raw: str) -> str:
    s = _TAGS.sub(" ", raw)
    s = _BLOCK.sub("\n\n", s)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = _ANYTAG.sub("", s)
    s = html.unescape(s)
    s = _WS.sub(" ", s)
    return _NL.sub("\n\n", s).strip()


def _is_public_host(host: str) -> bool:
    """Refuse to fetch a bar from anything on the local network.

    The server holds an API key and sits inside whatever network you deployed it
    to, so 'fetch this URL for me' is a request to make the server your proxy.
    Cloud metadata endpoints are the classic target.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False
    return True


async def fetch_bar(url: str) -> Dict:
    """Pull a reference artifact off the web. Returns {text, title, error}."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return {"error": "The bar URL must be http or https."}
    if not parsed.hostname:
        return {"error": "That does not look like a URL."}
    if not await asyncio.to_thread(_is_public_host, parsed.hostname):
        return {"error": "Refusing to fetch a private or unresolvable address. "
                         "Paste the reference text instead."}
    try:
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True,
                                     max_redirects=4) as c:
            r = await c.get(url, headers={
                "User-Agent": "AgentOS-Gauntlet/1.0 (+personal second brain)",
                "Accept": "text/html,text/plain,*/*"})
        if r.status_code >= 400:
            return {"error": "The bar URL returned %d." % r.status_code}

        ctype = r.headers.get("content-type", "")
        if not ctype.startswith(("text/", "application/json",
                                "application/xhtml")):
            return {"error": "The bar URL served %s, which is not readable text."
                             % (ctype or "an unknown type")}

        body = r.text[:MAX_FETCH]
        title = ""
        m = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
        if m:
            title = html.unescape(_ANYTAG.sub("", m.group(1))).strip()[:200]
        text = html_to_text(body) if "html" in ctype else body.strip()
        if len(text) < 200:
            return {"error": "Only got %d characters of text from that URL — it is "
                             "probably JavaScript-rendered. Paste the text instead."
                             % len(text)}
        return {"text": text, "title": title or url, "error": None}
    except httpx.HTTPError as e:
        return {"error": "Could not fetch the bar (%s)." % e.__class__.__name__}


def _clip(s: str, n: int = MAX_ARTIFACT) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n].rsplit("\n", 1)[0] + "\n…[truncated]"


# ----------------------------------------------------------------- prompting

BUILDER_SYSTEM = """You are the builder in a gauntlet loop.

You are producing an artifact that has to beat a specific named reference in a \
blind comparison judged by someone who will see both and not know which is which.

- Match or exceed the reference's standard. Do not imitate its content and do not \
quote it. Different substance, higher quality.
- Ground the substance in the supplied excerpts from the user's own vault. Prefer \
their vocabulary and their positions. Cite as [n] when you lean on an excerpt.
- Write the artifact and nothing else. No preamble, no explanation of your \
approach, no notes to the reader about what you changed.
- When a critique is supplied, treat its single named gap as the priority for \
this round. Do not regress what already worked."""

CRITIC_SYSTEM = """You are a harsh critic making a blind comparison.

You are shown two artifacts, A and B, that attempt the same brief. You do not \
know who wrote either. One may be a published professional reference.

Judge only what is in front of you: substance, structure, specificity, and \
whether a reader gets real value fast. Length is not quality. Confidence is not \
quality.

Praise is useless here. Your job is a forced choice and one actionable gap.

Reply with a single JSON object and nothing else:

{"winner": "A" or "B",
 "reason": "one sentence on why the winner won",
 "gap": "the single biggest concrete thing the loser must fix, as an instruction"}

Rules:
- "winner" must be exactly "A" or "B". A tie is not available to you; pick the \
one you would hand to a reader.
- "gap" must name one specific fixable thing. Not a list. Not "more detail"."""


def _builder_messages(goal, bar_text, bar_label, hits, critique, previous):
    excerpts = "\n\n".join(
        "[%d] %s — %s\n%s" % (i, h["title"], h["heading"], h["text"])
        for i, h in enumerate(hits, 1)) or "(no relevant notes found)"

    parts = [
        "Brief: %s" % goal,
        "",
        "The bar to beat is %s. Here it is in full — study its standard, then "
        "beat it on substance:\n\n<<<REFERENCE\n%s\nREFERENCE"
        % (bar_label, _clip(bar_text)),
        "",
        "Excerpts from the user's vault to build from:\n\n%s" % excerpts,
    ]
    if previous:
        parts += ["", "Your previous attempt:\n\n<<<PREVIOUS\n%s\nPREVIOUS"
                  % _clip(previous)]
    if critique:
        parts += ["", "A blind critic compared your previous attempt against the "
                      "reference and preferred the reference. The single biggest "
                      "gap it named:\n\n%s\n\nFix that. Output the full revised "
                      "artifact." % critique]
    else:
        parts += ["", "Output the artifact."]
    return [{"role": "system", "content": BUILDER_SYSTEM},
            {"role": "user", "content": "\n".join(parts)}]


def _critic_messages(goal, a_text, b_text):
    """Fresh context every round. The critic gets the brief and two artifacts —
    no history, no round number, no hint which side is which."""
    return [
        {"role": "system", "content": CRITIC_SYSTEM},
        {"role": "user", "content":
            "Brief both artifacts attempt: %s\n\n"
            "=== A ===\n%s\n\n=== B ===\n%s\n\n"
            "Which is better, A or B? Reply with the JSON object only."
            % (goal, _clip(a_text), _clip(b_text))},
    ]


_JSON = re.compile(r"\{.*\}", re.S)


def parse_verdict(text: str) -> Optional[Dict]:
    """Pull the verdict out of whatever the critic actually said.

    Models wrap JSON in prose or fences no matter how firmly you ask them not to,
    so this takes the outermost braces rather than trusting the whole response to
    parse. Returns None when there is no usable winner, and the caller treats that
    as an inconclusive round instead of silently scoring it a loss.
    """
    if not text:
        return None
    m = _JSON.search(text)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    winner = str(obj.get("winner", "")).strip().upper()[:1]
    if winner not in ("A", "B"):
        return None
    return {"winner": winner,
            "reason": str(obj.get("reason", "")).strip()[:600],
            "gap": str(obj.get("gap", "")).strip()[:800]}


# --------------------------------------------------------------------- loop

async def run(goal: str, bar_text: str, *, bar_label: str = "the reference",
              builder_model: str = None, critic_model: str = None,
              max_rounds: int = None, top_k: int = None
              ) -> AsyncGenerator[Dict, None]:
    """Drive the loop, yielding events. Never raises into the SSE stream."""
    goal = (goal or "").strip()
    bar_text = (bar_text or "").strip()

    if not goal:
        yield {"type": "error", "message": "Give it a goal."}
        return
    if len(bar_text) < 200:
        yield {"type": "error",
               "message": "The bar is too thin to judge against (%d characters). "
                          "A vague bar is the most common way a gauntlet loop "
                          "fails — the critic invents the comparison and approves "
                          "everything." % len(bar_text)}
        return
    if not llm.configured():
        yield {"type": "error",
               "message": "No inference key. Add one in Settings."}
        return

    ceiling = int(max_rounds or settings.get("GAUNTLET_MAX_ROUNDS"))
    builder = (builder_model or settings.get("GAUNTLET_BUILDER_MODEL")
               or settings.get("LLM_MODEL"))
    critic = (critic_model or settings.get("GAUNTLET_CRITIC_MODEL")
              or settings.get("LLM_MODEL"))
    temp = settings.get("GAUNTLET_TEMPERATURE")

    found = search.search(goal, top_k=top_k or settings.get("TOP_K"))
    hits = found["hits"]

    yield {"type": "start", "ceiling": ceiling, "builder": builder,
           "critic": critic, "same_model": builder == critic,
           "bar_label": bar_label, "bar_chars": len(bar_text),
           "sources": [{"n": i, "title": h["title"], "path": h["path"],
                        "doc_id": h["doc_id"], "heading": h["heading"]}
                       for i, h in enumerate(hits, 1)]}

    if builder == critic:
        yield {"type": "notice",
               "message": "Builder and critic are the same model. It will grade "
                          "itself generously — set a different critic in Settings."}

    current, critique = "", ""

    for rnd in range(1, ceiling + 1):
        yield {"type": "round", "n": rnd, "of": ceiling}

        # ---- build
        yield {"type": "phase", "phase": "building", "model": builder}
        buf = []
        failed = None
        async for ev in llm.stream(
                _builder_messages(goal, bar_text, bar_label, hits, critique,
                                  current),
                model=builder, temperature=temp):
            kind = ev.get("type")
            if kind == "delta":
                buf.append(ev["text"])
                yield {"type": "builder_delta", "text": ev["text"]}
            elif kind == "usage":
                yield dict(ev, phase="builder")
            elif kind == "error":
                failed = ev["message"]
            elif kind in ("notice", "model"):
                yield ev

        attempt = "".join(buf).strip()
        if failed or not attempt:
            yield {"type": "error",
                   "message": failed or "The builder returned nothing."}
            return
        current = attempt
        yield {"type": "builder_done", "chars": len(current), "round": rnd}

        # ---- criticise, blind
        yield {"type": "phase", "phase": "judging", "model": critic}
        ours_is = secrets.choice("AB")
        a, b = (current, bar_text) if ours_is == "A" else (bar_text, current)

        res = await llm.complete(_critic_messages(goal, a, b),
                                 model=critic, temperature=0.0)
        if res.get("usage"):
            yield dict(res["usage"], phase="critic")
        if res.get("error"):
            yield {"type": "error", "message": "Critic failed: %s" % res["error"]}
            return

        verdict = parse_verdict(res.get("text", ""))
        if not verdict:
            yield {"type": "inconclusive", "round": rnd,
                   "raw": (res.get("text") or "")[:400],
                   "message": "The critic did not return a usable verdict. "
                              "Rebuilding rather than counting it as a win."}
            critique = ("Your previous attempt was not judged conclusively. "
                        "Make its central claim sharper and more specific.")
            continue

        won = verdict["winner"] == ours_is
        yield {"type": "verdict", "round": rnd, "won": won,
               "reason": verdict["reason"], "gap": verdict["gap"],
               "ours_was": ours_is, "picked": verdict["winner"]}

        if won:
            yield {"type": "done", "won": True, "rounds": rnd, "final": current,
                   "message": "The critic picked ours blind in round %d." % rnd}
            return

        critique = verdict["gap"] or "Make it more specific and more useful."

    yield {"type": "done", "won": False, "rounds": ceiling, "final": current,
           "message": "Hit the %d-round ceiling without winning. The exit is "
                      "supposed to be the comparison, so treat this as a loss: "
                      "raise the ceiling, or the bar is genuinely better."
                      % ceiling}


# ponytail: one runnable check for the parsing and blinding logic — the parts
# that fail silently and wrongly. `python -m server.gauntlet`
def _selfcheck():
    assert parse_verdict('{"winner":"A","reason":"r","gap":"g"}')["winner"] == "A"
    # fenced and prefixed, which is what models actually send
    assert parse_verdict('Sure!\n```json\n{"winner": "B", "reason": "x", '
                         '"gap": "y"}\n```')["winner"] == "B"
    assert parse_verdict('{"winner":"b"}')["winner"] == "B", "case not normalised"
    assert parse_verdict('{"winner":"Artifact A"}')["winner"] == "A"
    assert parse_verdict("no json here") is None
    assert parse_verdict('{"winner":"tie"}') is None, "tie must be inconclusive"
    assert parse_verdict('{"winner":"C"}') is None
    assert parse_verdict('{"broken": ') is None
    assert parse_verdict("") is None
    assert parse_verdict('[1,2]') is None, "non-object accepted"
    v = parse_verdict('{"winner":"A","reason":"%s","gap":"%s"}' % ("r" * 900, "g" * 900))
    assert len(v["reason"]) == 600 and len(v["gap"]) == 800, "fields not clamped"

    assert html_to_text("<p>one</p><p>two</p>") == "one\n\ntwo"
    assert "alert" not in html_to_text("<script>alert(1)</script><p>hi</p>")
    assert html_to_text("<p>a &amp; b</p>") == "a & b"
    assert html_to_text("<h1>T</h1><div>body</div>") == "T\n\nbody"

    assert not _is_public_host("127.0.0.1")
    assert not _is_public_host("localhost")
    assert not _is_public_host("169.254.169.254"), "cloud metadata reachable"
    assert not _is_public_host("10.0.0.5")
    assert not _is_public_host("192.168.1.1")
    assert not _is_public_host("this-host-does-not-exist.invalid")

    assert _clip("abc", 10) == "abc"
    long = _clip("x" * 50 + "\n" + "y" * 50, 60)
    assert long.endswith("[truncated]") and len(long) < 120

    # blinding must actually vary
    draws = {secrets.choice("AB") for _ in range(60)}
    assert draws == {"A", "B"}, "blind side is not being randomised"
    print("gauntlet selfcheck OK")


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    _selfcheck()
