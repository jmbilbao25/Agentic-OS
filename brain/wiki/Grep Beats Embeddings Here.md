---
created: 2026-08-19
updated: 2026-08-29
tags: [memory, retrieval]
---

# Grep Beats Embeddings Here

Retrieval over this vault is keyword-first, and for the *agent* it stays that way. Not
because semantic search is bad, but because at this scale the ranking gain rarely pays
for the machinery — and because grep's failure mode is honest.

What a vector-only store adds: an embedding service, an index that must be rebuilt when
notes change, a similarity threshold to tune, a process to run, and a silent failure mode
where the index is stale and recall quietly degrades.

What grep costs: nothing. It is exact, instant on thousands of files, and zero hits means
zero hits.

The structure does the work embeddings would otherwise do:

- `STATE.md` is a hot cache — the highest-value context is already loaded, so most queries
  never need retrieval at all.
- `[[wikilinks]]` are a hand-built relevance graph. Following links from one hit finds the
  neighbours a similarity search would surface.
- Atomic notes with descriptive filenames make filename matching a decent first pass.

## Update 2026-08-29: the revisit condition fired

The original note named its own exit condition — *"add semantic search as a second pass
over grep, keeping markdown as the source of truth so the index stays disposable."* Two
things triggered it:

1. A **human** browsing a visual second brain searches by half-remembered concept, not by
   keyword. "That thing about why memory should be diffable" has no reliable search term.
2. A **RAG answer** needs passages ranked across the whole vault, which is exactly the job
   keyword search is worst at.

So `server/` now runs **hybrid** retrieval, built to honour the original constraint rather
than abandon it:

| Decision | Why it keeps the note's spirit |
|---|---|
| SQLite **FTS5 + BM25** for the keyword half | zero new dependency; grep-grade honesty, better ranking |
| **sqlite-vec** for the vector half | a file, not a service — no daemon to keep alive |
| Quantised MiniLM, CPU-only, ~90 MB | runs on a `t3.micro`; no GPU, no API call to embed |
| **Reciprocal Rank Fusion** to combine them | keyword hits still surface even when embeddings whiff |
| Index rebuilt from markdown, never authored | the index is disposable; delete it and reindex |

The load-bearing rule is unchanged and non-negotiable: **markdown is the source of truth
and the index is a cache.** `bin/os recall` still greps, because an agent mid-task wants a
deterministic answer. Semantic search is a *second* pass for humans and for RAG, exactly as
this note originally prescribed.

The distinction worth keeping: **agents recall, humans browse.** Those want different
retrieval, and it is fine to run both as long as only one of them is authoritative.

Related: [[Git Is The Disk]], [[Harness Capability Matrix]], [[Local Runtime Closes The Gaps]]
