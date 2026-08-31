# gemini-shim

A loopback proxy that lets the harness talk to Gemini 3.x. It exists for **two**
independent reasons, and either one alone is fatal to the route:

1. **Google rejects the request outright.** Its OpenAI-compatible surface
   implements a *subset* of OpenAI's schema and refuses the whole payload on an
   unknown field. pi-ai sends `store`, so every turn — chat included — answered
   `400 Unknown name "store"`.
2. **DSH drops the `thought_signature` Gemini requires**, so the turn after any
   tool call fails with a different 400.

Problem 1 masked problem 2 completely. Until it was fixed, *nothing* on this
route had ever worked: not chat, not the first tool call, nothing. The evidence
is in the journal — 13 consecutive real requests, every one of them carrying
`store`, every one of them a 400.

Once past it, problem 2 is what the rest of this document is about, and it bites
only after a tool call: chat is fine, the first tool call is fine, and then the
agent loop dies on the turn that reads the tool result. Which is every real task
in this vault.

## Problem 1: the request schema

Google names the offending field, which makes this diagnosable in one log line:

```
400 INVALID_ARGUMENT — Invalid JSON payload received.
                       Unknown name "store": Cannot find field.
```

The full refused set, determined empirically on 2026-08-30 by sending each
documented Chat Completions field and recording which ones came back rejected:

| Refused by Google | Accepted by Google |
|---|---|
| `store`, `metadata`, `logit_bias`, `seed`, `logprobs`, `top_logprobs`, `prediction`, `verbosity`, `safety_identifier`, `prompt_cache_key`, `frequency_penalty`, `usage` | `max_tokens`, `max_completion_tokens`, `modalities`, `n`, `parallel_tool_calls`, `presence_penalty`, `reasoning_effort`, `response_format`, `service_tier`, `stop`, `stream_options`, `temperature`, `top_p`, `user` |

Plus one conflict that is not about unknown fields at all:

```
400 — "max_tokens and max_completion_tokens cannot both be set"
```

pi-ai can populate both. `sanitise()` drops the legacy `max_tokens` and keeps
`max_completion_tokens`, which cannot change the effective cap.

**It also strips-and-retries fields it has never heard of.** When a 400 names a
field present in the body, the shim removes it and retries once, up to
`SHIM_MAX_FIELD_STRIPS` (default 8), logging the name so it can be promoted into
the static set. This is deliberate: the outage was caused by pi-ai adding exactly
one field, so the generic case is worth more than handling `store` specifically.

Proof the fix is real — identical body, two destinations:

| Request | Result |
|---|---|
| with `store`, **through the shim** | **200** |
| with `store`, **direct to Google** | **400 Unknown name "store"** |

## Problem 2: thought signatures

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
        # Leads because it answers; see Operating notes on 3.7's availability.
        - id: gemini-3.6-flash
          name: Gemini 3.6 Flash
          contextWindow: 1048576
          maxTokens: 8192
          input: [ text, image ]
          reasoningEfforts:
            low: low
            medium: medium
            high: high
        - id: gemini-3.7-flash
          name: Gemini 3.7 Flash (503s under load)
          contextWindow: 1048576
          maxTokens: 8192
          input: [ text, image ]
          reasoningEfforts:
            low: low
            medium: medium
            high: high
```

`deploy/harness/settings.yaml.example` carries this route in full, with
`gemini-3.5-flash` and `gemini-3.1-flash-lite` as well.

`off` is deliberately absent: as a bare YAML key it parses as boolean `false`
under YAML 1.1. Add it quoted — `"off": none` — if you want an Off level; Google
does accept `reasoning_effort: "none"`.

## Operating notes

- **`gemini-3.7-flash` is the least available model Google offers here.** An
  availability sweep on one key inside one minute, 2026-08-30:

  | Model | Result |
  |---|---|
  | `gemini-3.7-flash` | 503 "experiencing high demand", then a read timeout |
  | `gemini-3.6-flash` | 200 |
  | `gemini-3.5-flash` | 200 |
  | `gemini-3.1-flash-lite` | 200 |

  pi-ai's default retry policy (normal mode, five retries) absorbs an occasional
  503, but it cannot absorb a model that is saturated — which is why the route
  leads with `gemini-3.6-flash` and keeps 3.7 as a listed alternative rather than
  the default. Set `retryPolicy` on the route if you want retries more aggressive.
- Health and counters: `curl -s http://127.0.0.1:8787/healthz` reports
  `cached_signatures`, `remembered`, `injected`, `requests`, `misses` and
  `dropped`. A rising `misses` means leading tool calls arrived with no cached
  signature — expected after a restart, suspicious otherwise. `dropped` rising
  in step with `requests` is normal, not a warning: it is `store` being removed
  once per request. After four real agent tasks the counters read
  `requests: 14, dropped: 18, remembered: 6, injected: 11, misses: 0` — which is
  what a healthy route looks like, both jobs visibly doing work.
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
