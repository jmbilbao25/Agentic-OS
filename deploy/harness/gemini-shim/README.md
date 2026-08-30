# gemini-shim

A loopback proxy that lets the harness talk to Gemini 3.x. It exists for exactly
one reason: **DSH drops the `thought_signature` Gemini requires, so the turn after
any tool call fails with a 400.**

Without it, Gemini looks like it works — chat is fine, the first tool call is fine
— and then the agent loop dies on the turn that reads the tool result. Which is
every real task in this vault.

## The problem

Gemini 3.x returns a signed thinking token with each tool call and requires it
echoed back on the next turn. Google's OpenAI-compatible surface carries it in a
non-standard field:

```
choices[].message.tool_calls[].extra_content.google.thought_signature
```

DSH reaches providers through `@deepseek-ai/dsh-llm-pi-ai`, and:

```
supportedProtocols() → ["openai-completions", "openai-responses", "anthropic-messages"]
```

There is no `google-generative-ai`. pi-ai *upstream* ships one that handles
signatures correctly (`@earendil-works/pi-ai/dist/api/google-generative-ai.js`,
`google-shared.js` — both reference `thoughtSignature`), but DSH does not expose
it. The `openai-completions` path contains no mention of `extra_content` at all,
so it cannot carry Google's shape and silently drops the field on replay.

## Evidence (gemini-3.7-flash, 2026-08-30)

Replay of a tool call, second turn:

| Turn 2 sent | Result |
|---|---|
| **with** `extra_content` | **200** |
| **without** `extra_content` | **400 — "Function call is missing a thought_signature in functionCall parts"** |

No thinking level avoids it:

| `reasoning_effort` | signature emitted | turn 2 stripped |
|---|---|---|
| omitted | yes | 400 |
| `none` | yes | 400 |
| `low` | yes | 400 |
| `high` | yes | 400 |

With the shim in the path, the identical stripped request returns **200**, both
buffered and streaming. Verified against pi-ai's exact wire shape for an
unrecognised endpoint (`developer` role, `max_completion_tokens`, bare
`reasoning_effort`, `stream: true`) — Google accepts all three, which is why the
route needs no `compat` overrides.

## How it works

Remembers `thought_signature` keyed by the tool-call id Google assigned, and
re-attaches it when DSH replays that same tool call. Nothing else is rewritten.

Two properties worth knowing:

- **It never invents a signature.** When Gemini emits several tool calls in one
  turn, only the *first* carries one — the rest legitimately have none. Injecting
  everywhere would corrupt the turn, so injection happens only for a tool-call id
  a signature was actually observed for.
- **It does not hold the API key.** The `Authorization` header arrives from DSH
  and is forwarded verbatim, keeping the credential inside pi-ai's `apiKeyEnv`
  seam. The unit sets `InaccessiblePaths` on `harness.env` so the shim process
  cannot read the key even if it wanted to.

The cache is in-memory and bounded (2000 entries). It is a correctness aid for
live conversations, not durable state: a restart costs one 400 on a conversation
caught mid-tool-call, and the next turn re-establishes it.

## Install

```bash
sudo install -m 0644 deploy/harness/gemini-shim/gemini-shim.service \
  /etc/systemd/system/gemini-shim.service
sudo systemctl daemon-reload && sudo systemctl enable --now gemini-shim
curl -s http://127.0.0.1:8787/healthz
```

Put the key in `deploy/harness/harness.env` (gitignored):

```
GEMINI_API_KEY=...
```

`jm-harness` reads that file via `EnvironmentFile`, so **a key change needs
`systemctl restart jm-harness`** — settings.yaml is hot-reloaded, environment is
not.

Then the route in `$DSH_HOME/settings.yaml`:

```yaml
llm-pi-ai:
  providers:
    gemini:
      displayName: Gemini (via local shim)
      api: openai-completions
      baseURL: http://127.0.0.1:8787/v1
      apiKeyEnv: GEMINI_API_KEY
      models:
        - id: gemini-3.7-flash
          name: Gemini 3.7 Flash
          contextWindow: 1048576
          maxTokens: 8192
          reasoningEfforts:
            low: low
            medium: medium
            high: high
```

`off` is deliberately absent: as a bare YAML key it parses as boolean `false`
under YAML 1.1. Add it quoted — `"off": none` — if you want an Off level; Google
does accept `reasoning_effort: "none"`.

## Operating notes

- **`gemini-3.7-flash` returns 503 "experiencing high demand" fairly often.**
  pi-ai's default retry policy (normal mode, five retries) absorbs this; set
  `retryPolicy` on the route if you want it more aggressive.
- Health and counters: `curl -s http://127.0.0.1:8787/healthz` reports
  `cached_signatures`, `remembered`, `injected`, `requests`, `misses`. A rising
  `misses` means leading tool calls arrived with no cached signature — expected
  after a restart, suspicious otherwise.
- Logs go to journald: `journalctl -u gemini-shim -f`. The key and the signature
  body are never logged.
- Bound to `127.0.0.1` deliberately. It performs no authentication of its own, so
  a public bind would publish an unauthenticated relay to a billed account.

## Making this unnecessary

The correct fix is upstream: add `google-generative-ai` to DSH's
`supportedProtocols()`. pi-ai already implements the protocol and already handles
`thoughtSignature`, so this is plausibly a one-line change, after which a plain
catalog route replaces this whole directory. Note pi-ai's installed catalog tops
out at `gemini-3.6-flash`, so 3.7 would still be declared through a `models:`
list — which is supported, since a model absent from the catalog inherits the
protocol its shipped siblings agree on.
