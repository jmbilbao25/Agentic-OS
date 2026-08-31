#!/usr/bin/env python3
"""
gemini-shim — a schema-fitting, thought_signature-preserving proxy between DSH
and Gemini.

It does two separate jobs, because there are two separate incompatibilities
between what pi-ai's `openai-completions` path sends and what Google's
OpenAI-compatible surface accepts. Either one alone breaks the route.

WHY THIS EXISTS — PART 1: THE REQUEST SCHEMA
--------------------------------------------
Google implements a *subset* of OpenAI's request schema and rejects the whole
payload on an unknown field rather than ignoring it:

    400 INVALID_ARGUMENT — Invalid JSON payload received.
                           Unknown name "store": Cannot find field.

pi-ai sends `store`. So every Gemini turn failed with that 400 and the signature
handling below never even got reached — the route had never once worked in
practice. See GOOGLE_UNSUPPORTED and sanitise() for the full refused set,
determined empirically, plus an adaptive strip-and-retry so the next field pi-ai
adds costs one round trip instead of the whole route.

WHY THIS EXISTS — PART 2: THOUGHT SIGNATURES
--------------------------------------------
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

import base64
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get(
    "GEMINI_OPENAI_BASE", "https://generativelanguage.googleapis.com/v1beta/openai"
).rstrip("/")
HOST = os.environ.get("SHIM_HOST", "127.0.0.1")
PORT = int(os.environ.get("SHIM_PORT", "8787"))

# ---------------------------------------------------------------- vertex mode
#
# Off unless VERTEX_SA_JSON and VERTEX_PROJECT are both set. Two reasons to turn
# it on, and both were measured on 2026-08-31:
#
#   * AI Studio would not serve gemini-3.7-flash at all — 503 "experiencing high
#     demand", then read timeouts, repeatedly, across hours. The same model on
#     Vertex at locations/global answered 200 first try.
#   * Vertex accepts `store`, which AI Studio rejects. The sanitiser below is
#     harmless here, and still required for the AI Studio path.
#
# What does NOT change: the thought_signature requirement is identical. Verified
# on Vertex — replay with the signature 200, replay without it
# 400 "Function call is missing a thought_signature in functionCall parts". So the
# cache below earns its keep on both backends.
#
# THE HONEST COST, because the unit was written to avoid exactly this. Vertex
# authenticates with a short-lived OAuth token minted from a service-account
# private key, not a static API key, so pi-ai's `apiKeyEnv` seam cannot carry it
# — an env var cannot refresh itself hourly. That means the shim has to hold a
# credential, and gemini-shim.service was deliberately built so it could not:
# ProtectHome=read-only, ProtectSystem=strict, and InaccessiblePaths naming
# server/.env and harness.env, with the comment "the shim does NOT get
# GEMINI_API_KEY". Turning this on walks that back, and a service-account key is
# a worse thing to hold than an API key: it is an identity, not a scoped token.
#
# So: keep the SA file mode 600, grant it via a single ReadOnlyPaths entry and
# nothing broader, and give the account the narrowest role that works
# (roles/aiplatform.user). If you want the original property back, mint the token
# out-of-process — a systemd timer writing a fresh token to a file every 45
# minutes, with VERTEX_TOKEN_FILE pointing at it — and the shim then holds only a
# derived credential that expires, never the private key. That is the better
# design; this is the one that fits in the seam that exists today.
VERTEX_SA_JSON = os.environ.get("VERTEX_SA_JSON", "").strip()
VERTEX_TOKEN_FILE = os.environ.get("VERTEX_TOKEN_FILE", "").strip()
VERTEX_PROJECT = os.environ.get("VERTEX_PROJECT", "").strip()
# `global` is not a typo and not a default worth changing casually: it is the only
# location that served gemini-3.7-flash on this project. us-central1 answered 404
# "Publisher model ... not found or your project does not have access" for both
# 3.7 and 3.6, while serving gemini-2.5-flash fine. Region availability for
# Gemini is per-model, so re-probe before pinning a region.
VERTEX_LOCATION = os.environ.get("VERTEX_LOCATION", "global").strip()
VERTEX_MODE = bool(VERTEX_PROJECT and (VERTEX_SA_JSON or VERTEX_TOKEN_FILE))
_TOKEN_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
# Refresh this far before the token actually dies, so a long reasoning turn that
# starts near the boundary does not finish holding an expired credential.
_TOKEN_SKEW = 300.0

_tok_lock = threading.Lock()
_tok = {"value": "", "expires": 0.0}


def _vertex_upstream() -> str:
    """Vertex's OpenAI-compatible surface. Note `global` has no host prefix."""
    host = ("https://aiplatform.googleapis.com" if VERTEX_LOCATION == "global"
            else "https://%s-aiplatform.googleapis.com" % VERTEX_LOCATION)
    return ("%s/v1/projects/%s/locations/%s/endpoints/openapi"
            % (host, VERTEX_PROJECT, VERTEX_LOCATION))


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _mint_token() -> str:
    """Exchange the service-account key for an access token.

    Signs the assertion with `cryptography`, which is already on the system
    Python here, rather than adding google-auth. That keeps this file a
    stdlib-plus-one-present-library script, which is the same reason
    automations/research.py parses HTML with a regex instead of a parser.
    """
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    with open(VERTEX_SA_JSON, "rb") as fh:
        sa = json.load(fh)
    now = int(time.time())
    token_uri = sa.get("token_uri") or "https://oauth2.googleapis.com/token"
    header = {"alg": "RS256", "typ": "JWT", "kid": sa.get("private_key_id")}
    claims = {"iss": sa["client_email"], "scope": _TOKEN_SCOPE, "aud": token_uri,
              "iat": now, "exp": now + 3600}
    signing_input = ("%s.%s" % (_b64u(json.dumps(header).encode()),
                                _b64u(json.dumps(claims).encode()))).encode()
    key = serialization.load_pem_private_key(sa["private_key"].encode(), password=None)
    assertion = "%s.%s" % (signing_input.decode(),
                           _b64u(key.sign(signing_input, padding.PKCS1v15(),
                                          hashes.SHA256())))
    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion}).encode()
    req = urllib.request.Request(
        token_uri, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    with _tok_lock:
        _tok["value"] = payload["access_token"]
        _tok["expires"] = time.time() + float(payload.get("expires_in", 3600))
    log("minted a Vertex access token, good for %ss" % payload.get("expires_in"))
    return _tok["value"]


def _vertex_auth() -> str:
    """A live bearer token, refreshed slightly before it expires."""
    if VERTEX_TOKEN_FILE:
        # Out-of-process minting: whatever wrote this file owns the private key,
        # and the shim only ever sees the expiring token it derived.
        with open(VERTEX_TOKEN_FILE) as fh:
            return "Bearer " + fh.read().strip()
    with _tok_lock:
        if _tok["value"] and time.time() < _tok["expires"] - _TOKEN_SKEW:
            return "Bearer " + _tok["value"]
    return "Bearer " + _mint_token()
# Each signature is ~500 bytes of base64; 2000 entries is a few MB, which matters
# on a t3.micro already running the harness under a 340M cap.
MAX_CACHE = int(os.environ.get("SHIM_CACHE_ENTRIES", "2000"))
# A reasoning turn at effort=high can think for a long time before first byte.
TIMEOUT = float(os.environ.get("SHIM_UPSTREAM_TIMEOUT", "900"))

_lock = threading.Lock()
_sigs: "OrderedDict[str, str]" = OrderedDict()
_stats = {"remembered": 0, "injected": 0, "requests": 0, "misses": 0, "dropped": 0}


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


# ------------------------------------------------------------- schema fitting
#
# Google's OpenAI-compatible surface implements a SUBSET of OpenAI's request
# schema, and it rejects the entire payload rather than ignoring a field it does
# not recognise:
#
#     400 INVALID_ARGUMENT — Invalid JSON payload received.
#                            Unknown name "store": Cannot find field.
#
# pi-ai's openai-completions path sends `store`. So before this list existed,
# EVERY turn on the gemini route failed with that 400 — the route had never once
# worked, and the thought_signature machinery below never got the chance to
# matter. The signature bug is real, but it is the *second* bug in the path.
#
# Determined empirically on 2026-08-30 against gemini-3.7-flash by sending each
# documented Chat Completions field and recording which ones Google refused.
GOOGLE_UNSUPPORTED = frozenset({
    "store", "metadata", "logit_bias", "seed", "logprobs", "top_logprobs",
    "prediction", "verbosity", "safety_identifier", "prompt_cache_key",
    "frequency_penalty", "usage",
})

# Verified ACCEPTED in the same sweep. Recorded so that a later reader does not
# "tidy up" by adding them to the set above:
#   max_tokens, max_completion_tokens, modalities, n, parallel_tool_calls,
#   presence_penalty, reasoning_effort, response_format, service_tier, stop,
#   stream_options, temperature, top_p, user
#
# `usage` is in the unsupported set because it is an OpenRouter extension
# (`{"include": true}`), not an OpenAI field — it only appears here if a route
# was copied from the openrouter block.

# Google names the offending field in the error text, which lets the shim
# recover from a field it has never seen instead of failing the turn. That
# matters because this whole outage was caused by pi-ai adding one field.
UNKNOWN_FIELD_RE = re.compile(r'Unknown name \\?"([^"\\]+)\\?"')

# Bounded so a genuinely broken request cannot spin. Each strip is one retry.
MAX_FIELD_STRIPS = int(os.environ.get("SHIM_MAX_FIELD_STRIPS", "8"))


def sanitise(body: dict) -> list:
    """Drop request fields Google's compat surface refuses. Returns what went."""
    dropped = []
    for key in list(body):
        if key in GOOGLE_UNSUPPORTED:
            body.pop(key, None)
            dropped.append(key)

    # A semantic conflict rather than an unknown field:
    #     400 — "max_tokens and max_completion_tokens cannot both be set"
    # pi-ai can populate both (it prefers max_completion_tokens for
    # OpenAI-style endpoints but also carries the legacy alias). Keep the
    # modern one; dropping the legacy alias cannot change the effective cap.
    if "max_tokens" in body and "max_completion_tokens" in body:
        body.pop("max_tokens", None)
        dropped.append("max_tokens(both-caps-set)")

    return dropped


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
                body = {"ok": True, "cached_signatures": len(_sigs), **_stats}
            body["backend"] = "vertex" if VERTEX_MODE else "ai-studio"
            if VERTEX_MODE:
                body["vertex"] = {
                    "project": VERTEX_PROJECT, "location": VERTEX_LOCATION,
                    # Seconds of life left on the cached token: 0 means the next
                    # request mints a fresh one, which is normal, not an error.
                    "token_ttl": max(0, int(_tok["expires"] - time.time())),
                    "token_source": "file" if VERTEX_TOKEN_FILE else "service-account",
                }
            self._json(200, body)
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

        dropped = sanitise(body)
        if dropped:
            with _lock:
                _stats["dropped"] += len(dropped)
            # Loud on purpose. This one line is the difference between
            # "Gemini is broken" and "Gemini needed a field removed".
            log(f"dropped {len(dropped)} unsupported field(s): {', '.join(dropped)}")
        if n:
            log(f"re-attached {n} signature(s) | model={body.get('model')} stream={streaming}")

        # In Vertex mode the credential DSH sent is discarded and replaced with a
        # minted OAuth token: pi-ai can only carry a static string in apiKeyEnv,
        # and Vertex will not accept one. Everywhere else the client's header is
        # still forwarded verbatim, so the AI Studio path keeps the property that
        # the shim never holds a key.
        if VERTEX_MODE:
            base = _vertex_upstream()
            try:
                auth = _vertex_auth()
            except Exception as exc:                                # noqa: BLE001
                self._json(502, {"error": {"message":
                    "shim could not mint a Vertex token: %s: %s"
                    % (type(exc).__name__, exc)}})
                log("vertex token mint failed: %s" % exc)
                return
        else:
            base = UPSTREAM
            auth = self.headers.get("Authorization")
            if not auth:
                fallback = os.environ.get("GEMINI_API_KEY", "").strip()
                if fallback:
                    auth = "Bearer " + fallback
            if not auth:
                self._json(401, {"error": {"message":
                    "shim received no Authorization header and GEMINI_API_KEY is "
                    "unset"}})
                return

        # Adaptive strip-and-retry.
        #
        # GOOGLE_UNSUPPORTED covers what pi-ai sends today. This covers what it
        # sends after its next release — which is precisely the failure that
        # took this route down, so handling it once is worth more than handling
        # `store` specifically. Google names the offending field, so one wasted
        # round trip turns a dead turn into a live one and logs the field name
        # to promote into the static set.
        resp = None
        for attempt in range(MAX_FIELD_STRIPS + 1):
            req = urllib.request.Request(
                f"{base}/chat/completions",
                data=json.dumps(body).encode(),
                headers={"Authorization": auth, "Content-Type": "application/json",
                         "Accept": "text/event-stream" if streaming else "application/json"},
                method="POST",
            )
            try:
                resp = urllib.request.urlopen(req, timeout=TIMEOUT)
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read()
                field = None
                if exc.code == 400 and attempt < MAX_FIELD_STRIPS:
                    found = UNKNOWN_FIELD_RE.search(detail.decode("utf-8", "replace"))
                    if found and found.group(1) in body:
                        field = found.group(1)
                if field:
                    body.pop(field, None)
                    log(f"upstream rejected unknown field {field!r} — stripped it and "
                        f"retried; add it to GOOGLE_UNSUPPORTED to skip this round trip")
                    continue
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

        if resp is None:
            self._json(502, {"error": {"message":
                f"shim exhausted {MAX_FIELD_STRIPS} field-strip retries"}})
            log("exhausted field-strip retries")
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
    target = _vertex_upstream() if VERTEX_MODE else UPSTREAM
    log(f"listening on http://{HOST}:{PORT}  ->  {target}")
    if VERTEX_MODE:
        log("backend=vertex project=%s location=%s token=%s"
            % (VERTEX_PROJECT, VERTEX_LOCATION,
               "file" if VERTEX_TOKEN_FILE else "service-account key"))
        log("model ids on this backend MUST be '<publisher>/<model>', e.g. "
            "google/gemini-3.7-flash — a bare id is rejected 400")
    else:
        log("backend=ai-studio (set VERTEX_SA_JSON + VERTEX_PROJECT for Vertex)")
    log(f"cache={MAX_CACHE} entries  upstream_timeout={TIMEOUT}s")
    try:
        ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        log("shutting down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
