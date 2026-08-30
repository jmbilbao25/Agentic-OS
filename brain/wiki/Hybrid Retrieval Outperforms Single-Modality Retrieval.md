---
created: 2026-08-30
tags: [doctor, draft]
---

# Hybrid Retrieval Outperforms Single-Modality Retrieval

BM25 lexical retrieval excels at exact term matches, rare tokens, and named entities. Dense vector retrieval excels at paraphrases and semantic similarity where surface forms diverge from meaning. The two retriever classes fail in different places — neither subsumes the other — so hybrid pipelines that fuse both signals (typically via Reciprocal Rank Fusion) followed by cross-encoder reranking consistently outperform either alone on standard IR benchmarks as of 2026-08-29. This refines rather than contradicts [[Grep Beats Embeddings Here]]: pure lexical still wins for narrow exact-match queries and small corpora, but hybrid covers the general case where query vocabulary drifts from document vocabulary.

Distilled from `2026-08-29 research — hybrid retrieval bm25 vectors.md` by the doctor. Review before relying on it.
Related: 
