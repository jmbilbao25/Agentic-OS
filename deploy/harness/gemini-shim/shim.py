#!/usr/bin/env python3
"""
gemini-shim — a thought_signature-preserving proxy between DSH and Gemini.

WHY THIS EXISTS
---------------
Gemini 3.x returns a `thought_signature` alongside every tool call and *requires*
it echoed back on the next turn. Google's OpenAI-compatible surface carries it in
a non-standard place:

    choices[].message.tool_calls[].extra_content.google.thought_signature

DSH reaches providers through `@deepseek-ai/dsh-llm-pi-ai`, whose
`supportedProtocols()` is `["openai-completions", "openai-responses",
"anthropic-messages"]` — no `google-generative-ai`, even though pi-ai upstream
ships one that handles signatures correctly. The `openai-completions` path knows
nothing about `extra_content`, so it drops the field when it replays the
assistant turn, and Gemini answers:

    400 — Function call is missing a thought_signature in functionCall parts.

Verified against gemini-3.7-flash on 2026-08-30: replaying WITH the field returns
200, replaying WITHOUT it returns 400, at every reasoning_effort including
omitted and "none". There is no thinking level that avoids the requirement and no
DSH setting that fixes it.

So this shim sits in the middle. It remembers each signature keyed by the
tool-call id Google assigned, and re-attaches it when DSH replays that same
tool call. Nothing else about the request or response is rewritten.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It never invents a signature. When Gemini emits several tool calls in one turn
only the FIRST carries a signature — the rest legitimately have none — so
injecting one everywhere would corrupt the turn. Injection happens only for a
tool-call id we have actually seen a signature for.

It does not hold the API key. The Authorization header arrives from DSH and is
forwarded verbatim, which keeps the credential inside pi-ai's `apiKeyEnv` seam
instead of duplicating it into a second service's config. GEMINI_API_KEY is only
consulted as a fallback for manual curl testing.

The signature cache is in-memory and bounded: it is a correctness aid for live
conversations, not durable state. A restart loses it, which costs one 400 on any
conversation mid-tool-call; the next turn re-establishes it.
"""

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get(
    "GEMINI_OPENAI_BASE", "https://generativelanguage.googleapis.com/v1beta/openai"
).rstrip("/")
HOST = os.environ.get("SHIM_HOST", "127.0.0.1")
PORT = int(os.environ.get("SHIM_PORT", "8787"))
# Each signature is ~500 bytes of base64; 2000 entries is a few MB, which matters
# on a t3.micro already running the harness under a 340M cap.
MAX_CACHE = int(os.environ.get("SHIM_CACHE_ENTRIES", "2000"))
# A reasoning turn at effort=high can think for a long time before first byte.
TIMEOUT = float(os.environ.get("SHIM_UPSTREAM_TIMEOUT", "900"))

_lock = threading.Lock()
_sigs: "OrderedDict[str, str]" = OrderedDict()
_stats = {"remembered": 0, "injected": 0, "requests": 0, "misses": 0}


def log(msg: str) -> None:
    # journald captures stdout. Never log the key or the signature body.
    print(f"[gemini-shim] {msg}", flush=True)


def remember(tool_call_id, signature) -> None:
    if not tool_call_id or not signature:
        return
    with _lock:
        if tool_call_id in _sigs:
            _sigs.move_to_end(tool_call_id)
        else:
            _stats["remembered"] += 1
        _sigs[tool_call_id] = signature
        while len(_sigs) > MAX_CACHE:
            _sigs.popitem(last=False)


def recall(tool_call_id):
    if not tool_call_id:
        return None
    with _lock:
        sig = _sigs.get(tool_call_id)
        if sig is not None:
            _sigs.move_to_end(tool_call_id)
        return sig


def _signature_of(tool_call):
    """Read the signature out of a tool call, tolerating absent nesting."""
    if not isinstance(tool_call, dict):
        return None
    extra = tool_call.get("extra_content")
    if not isinstance(extra, dict):
        return None
    google = extra.get("google")
    if not isinstance(google, dict):
        return None
    sig = google.get("thought_signature")
    return sig if isinstance(sig, str) and sig else None


def inject(body: dict) -> int:
    """Re-attach signatures to assistant tool calls that lost them in transit."""
    injected = 0
    missing = 0
    messages = body.get("messages")
    if not isinstance(messages, list):
        return 0
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        tool_calls = msg.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for i, call in enumerate(tool_calls):
            if not isinstance(call, dict):
                continue
            if _signature_of(call):
                continue  # already intact — leave it exactly as-is
            sig = recall(call.get("id"))
            if sig is None:
                # Expected for every tool call after the first in a turn: Gemini
                # only signs the first. Only the first one missing is a problem.
                if i == 0:
                    missing += 1
                continue
            extra = call.setdefault("extra_content", {})
            if not isinstance(extra, dict):
                extra = call["extra_content"] = {}
            google = extra.setdefault("google", {})
            if not isinstance(google, dict):
                google = extra["google"] = {}
            google["thought_signature"] = sig
            injected += 1
    if injected:
        with _lock:
            _stats["injected"] += injected
    if missing:
        with _lock:
            _stats["misses"] += missing
        log(f"warn: {missing} leading tool call(s) had no cached signature "
            f"(cold cache or restart) — upstream may answer 400")
    return injected


def harvest_message(message) -> None:
    if not isinstance(message, dict):
        return
    for call in message.get("tool_calls") or []:
        if isinstance(call, dict):
            remember(call.get("id"), _signature_of(call))


def harvest_stream_chunk(payload: str, partial: dict) -> None:
    """
    Harvest from one SSE `data:` payload.

    Observed shape from Google's compat surface: each tool call arrives complete
    in a single delta, carrying both `id` and (for the first call only)
    `extra_content`. The `partial` map still stitches id and signature across
    chunks, because a provider that fragments deltas is allowed to and this costs
    nothing.
    """
    try:
        chunk = json.loads(payload)
    except (ValueError, TypeError):
        return
    if isinstance(chunk, list):
        chunk = chunk[0] if chunk else {}
    if not isinstance(chunk, dict):
        return
    for choice in chunk.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            continue
        for pos, call in enumerate(delta.get("tool_calls") or []):
            if not isinstance(call, dict):
                continue
            key = (choice.get("index", 0), call.get("index", pos))
            slot = partial.setdefault(key, {})
            if call.get("id"):
                slot["id"] = call["id"]
            sig = _signature_of(call)
            if sig:
                slot["sig"] = sig
            if slot.get("id") and slot.get("sig"):
                remember(slot["id"], slot["sig"])


HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "content-length",
    "content-encoding", "host",
}


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.1 so we can answer streaming responses with chunked encoding.
    protocol_version = "HTTP/1.1"
    server_version = "gemini-shim/1.0"

    def log_message(self, fmt, *args):
        pass  # access logs are noise here; we log the decisions that matter

    def _json(self, status: int, obj: dict) -> None:
        raw = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.rstrip("/") in ("/healthz", "/v1/healthz"):
            with _lock:
                self._json(200, {"ok": True, "cached_signatures": len(_sigs), **_stats})
        else:
            self._json(404, {"error": {"message": f"no route for GET {self.path}"}})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._json(404, {"error": {"message": f"no route for POST {self.path}"}})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length else b""

        try:
            body = json.loads(raw or b"{}")
        except ValueError as exc:
            self._json(400, {"error": {"message": f"shim could not parse request JSON: {exc}"}})
            return
        if not isinstance(body, dict):
            self._json(400, {"error": {"message": "shim expected a JSON object body"}})
            return

        with _lock:
            _stats["requests"] += 1

        n = inject(body)
        streaming = bool(body.get("stream"))
        if n:
            log(f"re-attached {n} signature(s) | model={body.get('model')} stream={streaming}")

        auth = self.headers.get("Authorization")
        if not auth:
            fallback = os.environ.get("GEMINI_API_KEY", "").strip()
            if fallback:
                auth = "Bearer " + fallback
        if not auth:
            self._json(401, {"error": {"message":
                "shim received no Authorization header and GEMINI_API_KEY is unset"}})
            return

        payload = json.dumps(body).encode()
        req = urllib.request.Request(
            f"{UPSTREAM}/chat/completions",
            data=payload,
            headers={"Authorization": auth, "Content-Type": "application/json",
                     "Accept": "text/event-stream" if streaming else "application/json"},
            method="POST",
        )

        try:
            resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as exc:
            detail = exc.read()
            self.send_response(exc.code)
            passthrough = exc.headers.get("Content-Type", "application/json")
            self.send_header("Content-Type", passthrough)
            self.send_header("Content-Length", str(len(detail)))
            self.end_headers()
            self.wfile.write(detail)
            log(f"upstream {exc.code}: {detail[:200]!r}")
            return
        except Exception as exc:  # network, DNS, timeout
            self._json(502, {"error": {"message": f"shim could not reach Gemini: {exc}"}})
            log(f"upstream unreachable: {exc}")
            return

        with resp:
            if streaming:
                self._relay_stream(resp)
            else:
                self._relay_once(resp)

    def _relay_once(self, resp) -> None:
        data = resp.read()
        try:
            parsed = json.loads(data)
            # Google array-wraps some responses (notably errors). pi-ai's
            # openai-completions parser expects an object, so unwrap.
            if isinstance(parsed, list):
                parsed = parsed[0] if parsed else {}
                data = json.dumps(parsed).encode()
            for choice in (parsed.get("choices") or []) if isinstance(parsed, dict) else []:
                if isinstance(choice, dict):
                    harvest_message(choice.get("message"))
        except ValueError:
            pass  # not JSON: forward untouched rather than guessing
        self.send_response(resp.status)
        self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _relay_stream(self, resp) -> None:
        self.send_response(resp.status)
        self.send_header("Content-Type", resp.headers.get("Content-Type", "text/event-stream"))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        partial: dict = {}
        pending = b""
        try:
            while True:
                block = resp.read(4096)
                if not block:
                    break
                # Forward first, parse second: harvesting must never add latency
                # to the token stream the user is watching.
                self.wfile.write(b"%x\r\n" % len(block) + block + b"\r\n")
                self.wfile.flush()

                pending += block
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    line = line.strip()
                    if line.startswith(b"data:"):
                        body = line[5:].strip()
                        if body and body != b"[DONE]":
                            harvest_stream_chunk(body.decode("utf-8", "replace"), partial)
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            log("client disconnected mid-stream")


def main() -> int:
    log(f"listening on http://{HOST}:{PORT}  ->  {UPSTREAM}")
    log(f"cache={MAX_CACHE} entries  upstream_timeout={TIMEOUT}s")
    try:
        ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        log("shutting down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
