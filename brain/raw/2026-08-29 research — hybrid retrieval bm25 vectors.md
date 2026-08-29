---
captured: 2026-08-29
captured_at: 2026-08-29T06:21:45Z
kind: research
topic: hybrid retrieval bm25 vectors
source: automations/research.py
results: 18
---

# Research — hybrid retrieval bm25 vectors

Gathered from 4 source(s), 18 result(s). **Unverified capture** — distil into `brain/wiki/` in your own words before relying on any of it.

## arxiv

- [Deep Retrieval at CheckThat! 2025: Identifying Scientific Papers from Implicit Social Media Mentions via Hybrid Retrieval and Re-Ranking](http://arxiv.org/abs/2505.23250v2)
  We present the methodology and results of the Deep Retrieval team for subtask 4b of the CLEF CheckThat! 2025 competition, which focuses on retrieving relevant scientific literature for given social media posts. To address this task, we propose a hybrid retrieval pipeline that combines lexical precision, semantic genera
- [Improving Biomedical Information Retrieval with Neural Retrievers](http://arxiv.org/abs/2201.07745v1)
  Information retrieval (IR) is essential in search engines and dialogue systems as well as natural language processing tasks such as open-domain question answering. IR serve an important function in the biomedical domain, where content and sources of scientific knowledge may evolve rapidly. Although neural retrievers ha
- [COS-Mix: Cosine Similarity and Distance Fusion for Improved Information Retrieval](http://arxiv.org/abs/2406.00638v1)
  This study proposes a novel hybrid retrieval strategy for Retrieval-Augmented Generation (RAG) that integrates cosine similarity and cosine distance measures to improve retrieval performance, particularly for sparse data. The traditional cosine similarity measure is widely used to capture the similarity between vectors
- [Evaluating Embedding APIs for Information Retrieval](http://arxiv.org/abs/2305.06300v2)
  The ever-increasing size of language models curtails their widespread availability to the community, thereby galvanizing many companies into offering access to large language models through APIs. One particular type, suitable for dense retrieval, is a semantic embedding service that builds vector representations of inp
- [Anserini Gets Dense Retrieval: Integration of Lucene's HNSW Indexes](http://arxiv.org/abs/2304.12139v1)
  Anserini is a Lucene-based toolkit for reproducible information retrieval research in Java that has been gaining traction in the community. It provides retrieval capabilities for both "traditional" bag-of-words retrieval models such as BM25 as well as retrieval using learned sparse representations such as SPLADE. With 
- [Benchmarking Retrieval Strategies for Biomedical Retrieval-Augmented Generation: A Controlled Empirical Study](http://arxiv.org/abs/2605.02520v1)
  Retrieval-Augmented Generation (RAG) offers a well-established path to grounding large language model (LLM) outputs in external knowledge, yet the question of which retrieval strategy works best in a high-stakes domain such as biomedicine has not received the controlled, multi-metric treatment it deserves. This paper p

## hf-papers

- [CaSKG: Counterfactual-Causal Skill Graphs for Scalable Agent Skill Retrieval](https://huggingface.co/papers/2608.25500) · **5**
  Reusable skill libraries allow large language model (LLM) agents to reuse procedural knowledge across tasks, but they also turn memory access into a challenging retrieval problem. Full-library prompting preserves coverage at high context cost, vector retrieval returns compact neighborhoods but treats skills as independ
- [RetrievalRouter: Joint Modality and Architecture Selection for Document Retrieval](https://huggingface.co/papers/2608.25625) · **3**
  Document retrieval increasingly supports high-stakes information access in finance, healthcare, and law. Modern retrieval pipelines vary both in modality (text or multimodal) and in retrieval architecture (dense or late-interaction). These choices impose a hard compromise: the most effective pipelines are too slow and 
- [VoiceMem: Streaming Dual-Brain Memory for Real-Time Interaction](https://huggingface.co/papers/2608.26005) · **164**
  Conversational systems, such as duplex speech language models (SLMs), still lack a streaming, accurate, and empathetic memory system as their soul. We introduce VoiceMem, a simple memory architecture with a parallel informational left brain, an emotional right brain, and streaming memory I/O mechanisms. We further buil

## github

- [CortexReach/memory-lancedb-pro](https://github.com/CortexReach/memory-lancedb-pro) · **4462**
  Enhanced LanceDB memory plugin for OpenClaw — Hybrid Retrieval (Vector + BM25), Cross-Encoder Rerank, Multi-Scope Isolation, Management CLI
- [0xnyn/comet](https://github.com/0xnyn/comet) · **131**
  A Vector Store written in Go - Supports hybrid retrieval over BM25, Flat, HNSW, IVF, PQ and IVFPQ Index with Quantization, Metadata Filtering, Reranking, Reciprocal Rank Fusion, Soft Deletes, Index Rebuilds and much much more
- [Happy-Chen-CH/Educational_RAG_System](https://github.com/Happy-Chen-CH/Educational_RAG_System) · **125**
  End-to-end educational RAG system: dual-engine retrieval (BM25 + BGE-M3 hybrid vector search), adaptive query strategies (HyDE/sub-query/backtracking), BERT intent classification, BGE-Reranker precision ranking, Chinese-optimized text splitting, and FastAPI SSE streaming — from documents to real-time answers.
- [flupkede/codesearch](https://github.com/flupkede/codesearch) · **72**
  Multi-repo semantic code search MCP server in Rust — hybrid vector + BM25 retrieval, tree-sitter AST chunking, fully offline. For OpenCode, Claude Code, Cursor, and any MCP client.
- [cortrix/cortrix](https://github.com/cortrix/cortrix) · **57**
  Agent-first semantic data infrastructure: durable, queryable memory and document understanding for AI agents. Hybrid retrieval (P-HNSW vector + BM25 full-text), cross-namespace semantic query, SPC ingestion pipeline, MCP server & Python SDK. AGPL-3.0.
- [YASSERRMD/barq-db](https://github.com/YASSERRMD/barq-db) · **29**
  Rust-based retrieval system with hybrid search (vector + BM25), async ingestion, and gRPC-first API

## hackernews

- [Show HN: RAG in 3 Lines of Python](https://pypi.org/project/piragi/) · **41**
  41 points · 6 comments
- [Show HN: PMB – local-first memory for AI coding agents over MCP](https://github.com/oleksiijko/pmb/blob/main/README.md) · **7**
  7 points · 6 comments
- [Launch HN: Danswer (YC W24) – Open-source AI search and chat over private data](https://news.ycombinator.com/item?id=39467413) · **231**
  231 points · 129 comments

---

## Open questions

- [ ] what does this change about how the OS should work?
- [ ] which single claim here would be most expensive to be wrong about?
- [ ] is there an existing note this contradicts? reconcile, don't append.
