---
loop: operator-console
status: open
check: node server/static/js/layouts.js && bash bin/os selftest
created: 2026-08-31
---

# Goal
Turn the vault UI from a map you look at into a console you operate from: fast on a
phone, honest about what the server already knows, and able to run the automations
that currently have no interface at all. Then decide — on measured evidence, not
vibes — whether a second agent belongs on this box.

The claim under test: every "more relevant info" item below is already computed and
sent by the server today and thrown away by the client, so surfacing it costs a
render and no new backend.

# Done when
A phone can change layout, scrub recency and read vault stats; `POST /api/run/{name}`
is reachable from the UI; the render loop idles when nothing is moving; and the
Hermes question has a written answer with a number attached, not an opinion.

# Steps

## Shipped
- [x] rAF-coalesce `AskView.paint()` — it was a full markdown reparse + innerHTML
      rebuild + forced layout *per streamed token*, O(N²) in answer length
- [x] preserve `<details open>` and text selection across streamed repaints
- [x] only auto-scroll the answer when the reader is already at the bottom
- [x] cache the canvas rect; `getBoundingClientRect()` was running per pointermove
- [x] coalesce hover hit-testing to one linear scan per frame, not per event
- [x] coalesce the resize storm — `resize()` re-runs the whole layout engine, and
      `app.js` has a second listener that can trigger it again via `setInsets()`
- [x] stop the render loop on `visibilitychange`; a hidden tab was drawing ~20k arc
      fills a frame for a map nobody was looking at
- [x] `100dvh` + `env(safe-area-inset-*)` — `100vh` is taller than the visible
      viewport under a collapsing mobile URL bar, which also pushed the canvas
      centre off by half the difference

## Perf, still open
- [ ] add a dirty flag so `draw()` is skipped when spin is off or the layout is
      flat and nothing is settling — deferred deliberately, it needs every mutation
      path audited or the canvas silently stops updating
- [ ] cache the two `createRadialGradient` calls in `_vignette`/`_center`; they are
      rebuilt every frame and are constant except for camera translation
- [ ] batch the ring-band dots into one path per alpha bucket, or pre-render one
      band to an OffscreenCanvas and rotate it — currently up to ~20k individual
      `arc()` fills per frame
- [ ] hoist the per-frame `filter().sort()` and `measureText()` out of `_labels()`
- [ ] cache `vault.load_all()` + `vault.graph()` behind an mtime check —
      `/api/doc` re-reads and re-parses the whole vault on every single note click.
      Verify: time-to-open a note before and after, same vault

## Responsive, still open
- [ ] give the phone back the four controls `.rail { display: none }` removes:
      layout switcher, recency scrubber, ring toggles, filter chip. They have no
      mobile equivalent and the `1`-`4`/`0` shortcuts need a keyboard
- [ ] show something on mobile instead of `.telemetry { display: none }` — a phone
      currently reports nothing at all about the vault
- [ ] make graph edges reachable without hover: `_edges()` only draws bright edges
      when `this.hover` is set, so on touch the edges are effectively invisible
- [ ] add a breakpoint between 901px and 1180px — a 460px dock plus a 176px rail
      over the canvas leaves the map squeezed with no rule covering it

## Information the server already sends and the UI discards
- [ ] `POST /api/run/{name}` — radar, distill, research. Zero references in any JS
      file. No button, no palette command. Biggest single feature gap
- [ ] `vault.stats().by_layer` / `.words` / `.newest` — sent on every load, only
      `docs` is read
- [ ] `index.exists` and `index.error` — a missing index currently renders as
      "0 chunks", which reads as an empty vault rather than a broken one
- [ ] `index.embed` — embedding model and health, never shown anywhere
- [ ] `reindex_pending` — the server knows a setting change needs a reindex
- [ ] `graph.missing` — unresolved wikilinks across the vault, currently
      `console.info` only. This is real vault health
- [ ] search `score` and `counts` (keyword vs semantic vs fused), and the `ask`
      `retrieval.counts` frame — all captured client-side and never rendered

## Blocked, needs a decision from the user
- [ ] **Does Hermes go on this box?** Measured 2026-08-31: t3.micro, 913 MB total,
      **104 MB free / 128 MB available**, and the three existing units already
      declare 1168 MB of caps on a 913 MB box. No Docker. Hermes Agent is a full
      Python agent with a learning loop, skills and memory. It does not fit.
      Options, in cost order: run it off-box and integrate over its
      OpenAI-compatible endpoint; resize to t3.small (2 GB, ~+$8/mo); resize to
      t3.medium (4 GB, ~+$23/mo) if it is to share with the vault and harness.
      Note the open `$20/mo` billing alarm in STATE.md before choosing
- [ ] **What is the "activities button"?** No activity feature, route, tab, command
      or element exists anywhere in this repo — confirmed exhaustively; the only
      "activit" match is an unrelated comment in `server/index.py:145`. The nav
      item in the reference screenshots belongs to Claude Code OS, a different
      product. Closest things here are the Recency scrubber and the Timeline
      layout, and both are load-bearing, so this needs confirming before deleting
- [ ] **Codebase knowledge graph** (the graphify-style view in the screenshots:
      files, imports, clusters, map confidence, spend). This is a different graph
      from the one that exists — the current map plots vault *notes*, that one
      plots *code*. Needs a parser backend and is its own loop, not a step here

# Notes
The existing motion vocabulary is deliberately tiny — one easing
(`cubic-bezier(.16,1,.3,1)`), two durations (`--fast: 120ms`, `--mid: 260ms`), and
one entrance animation (`rise`). "More animations" must be built from those or the
UI stops looking like itself. There is no `--slow` token; adding longer motion means
adding a third token, not inventing a one-off duration.

Anything animated needs handling in three places, not one: the
`prefers-reduced-motion` media query, the server-driven `body.reduced-motion` class,
and `orbit.reducedMotion`.

The CSP ships without `'unsafe-inline'`, so no inline `style=` attributes in HTML
strings and no inline `<script>`. Style through classes or CSSOM property writes.

`layouts.js` has a real self-check harness (`node server/static/js/layouts.js`).
Run it after touching any layout — it asserts frame containment, determinism and
no lane collisions.
