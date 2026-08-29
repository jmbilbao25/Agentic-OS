# The visual second brain

A small FastAPI app that renders `brain/` as an interactive orbit map, answers
questions over it with citations, and runs a build-and-critique loop against a real
reference.

**Read-only over the vault, on purpose.** This app renders and searches markdown; it
never writes it. Authoring goes through `bin/os` so every change to memory is a git
commit you can review, revert, and blame. The index here is a cache; deleting it is
a valid repair step.

The one exception is `settings.local.json`, which is machine state rather than
memory — it holds an API key and a model choice, neither of which belongs in a git
history.

```
config.py     boot-time config: paths, bind address, credentials
settings.py   runtime config: the schema that also generates the settings UI
passwd.py     PBKDF2 hashing, and the CLI that mints a password hash
vault.py      the only module that knows the on-disk layout
embed.py      local CPU embeddings, lazily loaded and allowed to be absent
index.py      build the SQLite index (FTS5 + sqlite-vec)
search.py     hybrid retrieval, fused with weighted RRF + a name-match nudge
llm.py        OpenAI-compatible inference, model routing, the model catalogue
gauntlet.py   the builder/critic loop
auth.py       single-user credential auth
app.py        routes
static/       the UI: orbit.js (canvas map), md.js (renderer), and one module per view
tools/        smoke.py (end-to-end), eval_retrieval.py (score retrieval), devserve.sh
```

## Run it locally

```bash
pip install -r server/requirements.txt
cp server/.env.example server/.env
python -m server.passwd                 # paste the output into server/.env
python -m server.index --full
server/tools/devserve.sh                # http://127.0.0.1:8000
```

`DEV_NO_AUTH=true` skips sign-in for a quick look, and is **ignored unless the bind
address is loopback** — so it cannot accidentally publish an open instance.

`sqlite-vec` also needs a Python built with loadable SQLite extensions. Some distro
and pyenv builds are not:

```bash
python -c "import sqlite3;print(hasattr(sqlite3.connect(':memory:'),'enable_load_extension'))"
```

A `False` there is why an install with every package present still reports
keyword-only mode.

For the always-on deployment see [`../deploy/README.md`](../deploy/README.md).

## Check it works

```bash
python -m server.tools.smoke     # 37 end-to-end checks, no server needed
python -m server.settings        # settings layer self-check
python -m server.gauntlet        # verdict parsing, blinding, SSRF guard
python -m server.passwd --selfcheck
```

`smoke.py` drives the real ASGI app through `TestClient` against a temporary index
and a temporary settings file, so it never touches your real ones. It is aimed at
the failures that are silent: an auth gate that stops gating, a settings write that
half-applies, a document the map can draw but not open.

## Configuration

Two layers, on purpose.

`config.py` holds what genuinely cannot change while running — paths, bind address,
session secret, credentials. `settings.py` holds everything else, resolved as
**saved value → environment → shipped default**, and editable from the UI without a
restart. A model swap that needs a restart is a model swap nobody makes.

`settings.SCHEMA` is also the form: `/api/settings` ships it to the browser, which
renders the controls, ranges, help text and "needs a reindex" flags from it. Adding
a knob is one entry in Python and nothing else. A hand-maintained settings form
drifts from its backend within one change.

Writes are all-or-nothing. One bad field returns per-field errors and applies none
of them, because a form that half-applies leaves you guessing which half.

The API key is write-only: stored with mode 600, never serialised back to the
browser, reported as a `set` flag plus a four-character tail.

## Retrieval

Hybrid, because keyword and vector search fail in opposite directions. Keyword nails
exact terms — a filename, a rare token, an error string — and whiffs on paraphrase.
Vectors do the reverse.

| Half | Engine | Notes |
|---|---|---|
| Keyword | SQLite **FTS5** + `bm25()` | ships with SQLite; zero new dependency |
| Semantic | **sqlite-vec** + quantised BGE-small (ONNX, CPU) | a file, not a service |
| Fusion | **weighted Reciprocal Rank Fusion** | combines by *rank*, so the two incomparable score scales never need normalising |
| Names | a bounded title-affinity bonus | neither half can see a title |

Four things here were measured, not assumed:

1. **Naive RRF was worse than semantic alone.** On a small corpus, keyword search
   returns much of the vault at near-random rank, dragging good semantic hits down.
   Weighting semantic 2× and lowering `RRF_K` to 20 fixed it.
2. **`fastembed.query_embed()` is a no-op for this model** — it returned a vector
   identical to `embed()` (cosine 1.0000). BGE v1.5 wants an instruction prefix on
   queries only, so `embed.py` applies it explicitly rather than trusting the
   library.
3. **Stopwords had to be stripped from the FTS query.** FTS5's porter tokenizer
   keeps them, so "why is git the disk" ranked by `is`/`the` density and buried the
   note literally titled *Git Is The Disk*.
4. **Typing a note's name did not return that note.** BM25 indexes `title`, but
   every chunk of a document carries the same title, so a title match lifts all of
   its chunks equally and cancels out in the ranking; the vector side embeds
   `heading + text`, so the title is not in the vector at all. Net effect: the most
   common query in a personal vault was the one the ranker was worst at —
   `AGENTS.md` did not return AGENTS.md at all, and `ralph` put *Ralph Loop* third.
   `search.name_affinity()` adds a small bounded bonus when a query looks like it is
   *naming* a note. On the benchmark, top-1 went **7/16 → 12/16** with no loss on
   the paraphrase probes; a 225-config sweep found `W_TITLE=0.08` to be the smallest
   value reaching the plateau, and found nothing that beats it.

Re-check any of this after the vault grows:

```bash
python -m server.tools.eval_retrieval          # score the current config
python -m server.tools.eval_retrieval --sweep  # grid-search the knobs
```

The evaluator calls `search.fuse()` — the same function the app uses. It used to
reimplement fusion inline, which meant a change to ranking was invisible to the
benchmark whose whole job is catching ranking regressions.

Add a probe whenever the UI fails to find something you knew was there. A benchmark
containing only queries you already pass is decoration.

### Graceful degradation

If `sqlite-vec` or `fastembed` is missing, the app runs **keyword-only** and says so
in the status pill. That is a supported mode, not a broken one — a vault you can
search by keyword beats a 500 page. Same for inference: with no API key, search
works and Ask returns an explicit, actionable message instead of a dead spinner.

## Model routing

The provider is three settings — base URL, key, model — so OpenRouter, OpenAI,
Together, a local Ollama at `/v1` and your own proxy are all the same code path.

- **Live swapping.** The model picker filters the provider's own catalogue and shows
  context length and price per million tokens next to each id, because those are the
  two things that decide the choice. A 400-entry `<select>` is not a picker.
- **Fallbacks.** `LLM_FALLBACK_MODELS` is tried in order. OpenRouter routes the list
  server-side (faster and cheaper than a failed round trip); other providers get a
  client-side retry. A free-tier model rate-limiting mid-sentence is the normal
  case, not the exception.
- **Per-request override.** Ask and Gauntlet can each name a model without changing
  the saved default.
- **Usage and cost** stream back as their own SSE event, so the UI can report tokens
  and spend rather than guessing.
- **Errors are explained, not echoed.** A 401 becomes "the API key was rejected,
  check it in Settings"; a 429 says free-tier models do this and suggests a
  fallback.

## The gauntlet loop

A builder drafts from your vault; a **separate** critic with fresh context compares
it against a real reference **blind**, labels stripped and sides randomised per
round, and names one concrete gap. It loops until the critic picks ours.

The four ways this fails are the four things the implementation is built around: a
vague bar (refused up front — a bar under 200 characters cannot be judged against),
the builder judging its own work (separate call, separate model, no history), a soft
critic (a forced A/B, never a score out of ten), and exiting after N rounds (the
ceiling is a cost stop, and hitting it is reported as a loss).

Set the builder and critic to **different** models. Same model on both sides is the
"builder judging its own work" failure wearing two hats; the app warns and runs
anyway, because sometimes it is all you have.

`bar_url` fetches a page instead of pasting one. Private, loopback and link-local
addresses are refused: the server holds an API key and sits inside your network, so
"fetch this URL for me" is a request to make it your proxy.

See [`../config/skills/gauntlet-loop/SKILL.md`](../config/skills/gauntlet-loop/SKILL.md).
The pattern is adapted from [gauntlet-loop](https://github.com/robonuggets/gauntlet-loop)
by robonuggets (CC BY 4.0).

## Security

- **One username, one password.** No registration, no reset, no second user — each
  of those is an attack surface that exists to solve a problem a single operator does
  not have. Losing the password means editing `.env` on the box, which you can do and
  an attacker cannot.
- **PBKDF2-HMAC-SHA256, 600k iterations, per-install salt.** From `hashlib`, so
  there is nothing to install. Mint one with `python -m server.passwd`.
- **No username enumeration.** The KDF runs on every attempt regardless of whether
  the username matched, then the username result is folded in. Short-circuiting made
  a wrong username 12× faster to reject than a wrong password (0.008s vs 0.101s),
  which tells an attacker exactly what they need. Measured after the fix: 0.0996s
  vs 0.1004s.
- **Online guessing** is capped by a per-address failure counter and a lockout
  window, which a correct password does not bypass.
- **Login CSRF** is blocked by a token minted into the form and checked on submit.
- **Session fixation** is prevented by clearing the session on successful login.
- **Open redirects** are blocked: `next` is honoured only when it is a local path.
- An **empty credential config denies everyone**. Failing closed is deliberate.
- Credentials are re-checked against live config on every request, so changing the
  username takes effect immediately rather than whenever a cookie expires.
- **CSP with no `unsafe-inline`**, plus `nosniff`, `no-referrer`, `DENY` framing, and
  HSTS when `AGENTOS_BASE_URL` is https. The UI uses external files and the CSSOM,
  never a style attribute or an inline handler.
- **No `/openapi.json`** — there is no third-party client to generate one for, and an
  unauthenticated schema would enumerate the whole API for free.
- Only `/healthz` is public, and it leaks nothing about the vault.
- All markdown is HTML-escaped before any tag is generated. The vault is trusted, but
  "trusted input" is how XSS happens.
- `bash bin/os selftest` scans tracked files for private keys and API tokens.
  `.gitignore` does not help with a file that was added before it was ignored.

## API

| Route | |
|---|---|
| `GET /healthz` | public liveness |
| `GET /api/status` | index mode, counts, model, UI prefs, config problems |
| `GET /api/graph` | all nodes + resolved wikilink edges |
| `GET /api/doc?id=` | one document, frontmatter parsed, plus backlinks and outgoing links |
| `GET /api/search?q=&k=&layers=` | hybrid search |
| `POST /api/ask` | SSE: `sources`, `retrieval`, `model`, `delta`, `usage`, `done` |
| `POST /api/gauntlet` | SSE: `start`, `round`, `builder_delta`, `verdict`, `done` |
| `POST /api/gauntlet/bar` | fetch a reference artifact from a URL |
| `GET /api/settings` | the schema, current values, and where each came from |
| `PUT /api/settings` | validate and persist; 422 with per-field errors |
| `POST /api/settings/reset` | forget saved values, fall back to env and defaults |
| `GET /api/models?refresh=` | the provider's catalogue, normalised and cached |
| `POST /api/reindex?full=` | incremental or full rebuild |
| `POST /api/sync` | `git pull` then reindex |

Everything except `/healthz` requires a session.

## The UI

No framework and no CDN — it must work on a locked-down box with no outbound access.
`md.js` is a ~130-line markdown renderer for that reason, and the display face is
subset and self-hosted under `static/fonts/` rather than pulled from a font CDN.

The design bar it is held to is
[`../config/steering/20-craft-floor.md`](../config/steering/20-craft-floor.md).

Layout is **deterministic** polar geometry, not a force simulation: a node sits in
the same place every visit. Spatial memory is the entire value of a map, and a layout
that reshuffles on reload destroys it.

Rings are the ARMS layers, outermost first — Applications (`output/`), Routines
(`loops/`), Memory (`wiki/`, `raw/`, `journal/`, `decisions/`), Skills
(`config/skills/`, `config/steering/`) — around the kernel every agent boots from.
Dot size is note length; curves are `[[wikilinks]]`.

Three interaction decisions worth knowing:

- **Selecting a note freezes the drift.** The ambient rotation is what makes the map
  feel alive and exactly what makes it useless when you want to read something. It
  eases to zero while a note is open and eases back when you close it — which is
  also what lets the camera centre a node and have it stay centred.
- **Hovering dims everything unconnected.** A wikilink graph is only legible one
  neighbourhood at a time.
- **Filtered-out notes ghost rather than vanish.** Dragging the recency scrubber
  should show the vault thinning out over time, not delete two thirds of the picture.

One dock holds the four views — Note, Ask, Gauntlet, Settings — because reading a
note, asking a question and changing a model are all the same act, and they should
share a position you learn once.

**Keys.** `/` search · `>` commands · `#` tags · `@` layers · `Ctrl/Cmd-K` palette ·
`A` ask · `G` gauntlet · `,` settings · `j`/`k` walk the link graph · `0` reset ·
`+`/`-` zoom · `Esc` unwinds one layer at a time · drag to pan, wheel to zoom,
pinch on touch.
