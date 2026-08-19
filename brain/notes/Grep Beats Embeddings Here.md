---
created: 2026-08-19
tags: [memory, retrieval]
---

# Grep Beats Embeddings Here

Retrieval over this vault is `rg`, not a vector database. Not because semantic
search is bad, but because at this scale the ranking gain doesn't pay for the
machinery.

What a vector store would add: an embedding service, an index that must be
rebuilt when notes change, a similarity threshold to tune, a process to run, and
a silent failure mode where the index is stale and recall quietly degrades.

What grep costs: nothing. It is exact, instant on thousands of files, and its
failure mode is honest — zero hits means zero hits.

The structure does the work that embeddings would otherwise do:

- `STATE.md` is a hot cache — the highest-value context is already loaded, so most
  queries never need retrieval at all.
- `[[wikilinks]]` are a hand-built relevance graph. Following links from one hit
  finds the neighbours a similarity search would surface.
- Atomic notes with descriptive filenames make filename matching a decent first
  pass on its own.

When to revisit: a vault in the thousands of notes where you routinely search for
a *concept* you can't name a keyword for. Then add semantic search as a second
pass over grep, keeping markdown as the source of truth so the index stays
disposable.

Related: [[Git Is The Disk]], [[Kiro Web Capability Matrix]]
