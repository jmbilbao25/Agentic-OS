# The visual second brain

A small FastAPI app that renders `brain/` as an interactive orbit map and answers
questions over it with citations.

**Read-only over the vault, on purpose.** This app renders and searches markdown;
it never writes it. Authoring goes through `bin/os` so every change to memory is a
git commit you can review, revert, and blame. The index here is a cache.

```
config.py     every knob, read from server/.env
vault.py      the only module that knows the on-disk layout
embed.py      local CPU embeddings, lazily loaded and allowed to be absent
index.py      build the SQLite index (FTS5 + sqlite-vec)
search.py     hybrid retrieval, fused with weighted RRF
llm.py        OpenAI-compatible inference — provider is one env var
auth.py       Google OAuth with a single-account allowlist
app.py        routes
static/       the UI: orbit.js (canvas map), md.js (renderer), app.js (wiring)
tools/        eval_retrieval.py (score retrieval), devserve.sh
```

## Run it locally

```bash
pip install -r server/requirements.txt
cp server/.env.example server/.env      # add keys, or use DEV_NO_AUTH for a look
python -m server.index --full
server/tools/devserve.sh                # http://127.0.0.1:8000
```

`DEV_NO_AUTH=true` skips Google sign-in, and is **ignored unless the bind address
is loopback** — so it cannot accidentally publish an open instance.

For the always-on deployment see [`../deploy/README.md`](../deploy/README.md).

## Retrieval

Hybrid, because keyword and vector search fail in opposite directions. Keyword
nails exact terms — a filename, a rare token, an error string — and whiffs on
paraphrase. Vectors do the reverse.

| Half | Engine | Notes |
|---|---|---|
| Keyword | SQLite **FTS5** + `bm25()` | ships with SQLite; zero new dependency |
| Semantic | **sqlite-vec** + quantised BGE-small (ONNX, CPU) | a file, not a service |
| Fusion | **weighted Reciprocal Rank Fusion** | combines by *rank*, so the two incomparable score scales never need normalising |

Three things here were measured, not assumed:

1. **Naive RRF was worse than semantic alone.** On a small corpus, keyword search
   returns much of the vault at near-random rank, dragging good semantic hits down.
   Weighting semantic 2× and lowering `RRF_K` to 20 fixed it. Now hybrid beats both
   halves on top-5, which is what RAG actually consumes.
2. **`fastembed.query_embed()` is a no-op for this model** — it returned a vector
   identical to `embed()` (cosine 1.0000). BGE v1.5 wants an instruction prefix on
   queries only, so `embed.py` applies it explicitly rather than trusting the library.
3. **Stopwords had to be stripped from the FTS query.** FTS5's porter tokenizer
   keeps them, so "why is git the disk" ranked by `is`/`the` density and buried the
   note literally titled *Git Is The Disk*.

Re-check any of this after the vault grows:

```bash
python -m server.tools.eval_retrieval          # score the current config
python -m server.tools.eval_retrieval --sweep  # grid-search the knobs
```

Add a probe to that file whenever the UI fails to find something you knew was
there. A benchmark containing only queries you already pass is decoration.

### Graceful degradation

If `sqlite-vec` or `fastembed` is missing, the app runs **keyword-only** and says
so in the status pill. That is a supported mode, not a broken one — a vault you can
search by keyword beats a 500 page. Same for inference: with no API key, search
works and Ask returns an explicit message instead of a dead spinner.

## Security

- Google OAuth; the allowlist is checked against Google's **verified** email on
  every request, so revoking access takes effect immediately rather than whenever
  a cookie happens to expire.
- An **empty** `ALLOWED_EMAILS` denies everyone. Failing closed is deliberate.
- Unverified Google emails are rejected.
- Only `/healthz` is public, and it leaks nothing about the vault.
- The app binds to loopback; TLS terminates in front of it.
- All markdown is HTML-escaped before any tag is generated. The vault is trusted,
  but "trusted input" is how XSS happens.

## API

| Route | |
|---|---|
| `GET /healthz` | public liveness |
| `GET /api/status` | index mode, counts, model, config problems |
| `GET /api/graph` | all nodes + resolved wikilink edges |
| `GET /api/doc?id=` | one document, frontmatter parsed |
| `GET /api/search?q=&k=&layers=` | hybrid search |
| `POST /api/ask` | SSE: `sources` first, then `delta`, then `done` |
| `POST /api/reindex` | incremental reindex |
| `POST /api/sync` | `git pull` then reindex |

## The UI

No framework and no CDN — it must work on a locked-down box with no outbound
access. `md.js` is a ~120-line markdown renderer for that reason.

Layout is **deterministic** polar geometry, not a force simulation: a node sits in
the same place every visit. Spatial memory is the entire value of a map, and a
layout that reshuffles on reload destroys it.

Rings are the ARMS layers, outermost first — Applications (`output/`), Routines
(`loops/`), Memory (`wiki/`, `raw/`, `journal/`, `decisions/`), Skills
(`config/skills/`) — around the kernel every agent boots from. Dot size is note
length; curves are `[[wikilinks]]`.

`/` search · `a` ask · `↑↓` results · `Enter` open · `Shift+Enter` ask ·
`0` reset · `+`/`-` zoom · drag to pan · `?` for the full list.
