"""Hybrid retrieval: BM25 (FTS5) + vectors (sqlite-vec), fused with RRF.

Why fuse instead of picking one: keyword search nails exact terms — a filename, an
error string, a person — and whiffs on paraphrase. Vectors do the opposite.
Reciprocal Rank Fusion combines the two by *rank* rather than score, which means
the two systems' incomparable score scales never need normalising.

    RRF(d) = Σ  1 / (k + rank_i(d))

k damps the influence of any single list's top hit; 60 is the value from the
original Cormack et al. formulation and is a sane default.
"""
import re
import sqlite3
from typing import Dict, List, Optional

from . import config, embed
from .index import connect, load_vec, pack

FTS_SPECIAL = re.compile(r'[^\w\s"*]')

# FTS5's porter tokenizer does not remove stopwords, so an OR query built from a
# natural-language question gets dominated by terms that match everything. A
# question like "why is git the disk" otherwise ranks by "is"/"the" density and
# buries the note actually titled "Git Is The Disk".
STOP = {
    "a", "an", "and", "any", "are", "as", "at", "be", "because", "been",
    "but", "by", "can", "did", "do", "does", "for", "from", "get", "had", "has",
    "have", "how", "i", "if", "in", "into", "is", "it", "its", "just", "me",
    "my", "no", "not", "of", "on", "or", "our", "out", "so", "than", "that",
    "the", "their", "them", "then", "there", "these", "they", "this", "to",
    "up", "us", "was", "we", "were", "what", "when", "where", "which", "who",
    "why", "will", "with", "would", "you", "your",
}


def _fts_query(q: str) -> str:
    """Make user input safe for FTS5 and forgiving.

    FTS5 treats punctuation as syntax and raises on malformed input, so strip it
    and OR the terms with prefix matching — a user typing three words wants
    documents about any of them, ranked, not an exact conjunction returning
    nothing. Stopwords are dropped unless that would empty the query.
    """
    cleaned = FTS_SPECIAL.sub(" ", q).strip()
    if not cleaned:
        return ""
    if '"' in q:                       # respect an explicit phrase search
        return cleaned
    terms = [t for t in cleaned.split() if t]
    kept = [t for t in terms if t.lower() not in STOP and len(t) > 1]
    if not kept:                       # query was all stopwords — use it as given
        kept = terms
    return " OR ".join('%s*' % t for t in kept)


def _keyword(db, q: str, limit: int) -> List[Dict]:
    fq = _fts_query(q)
    if not fq:
        return []
    try:
        rows = db.execute(
            "SELECT c.rowid, c.doc_id, c.heading, c.text, bm25(chunks_fts) AS score "
            "FROM chunks_fts f JOIN chunks c ON c.rowid = f.rowid "
            "WHERE chunks_fts MATCH ? ORDER BY score LIMIT ?", (fq, limit)).fetchall()
    except sqlite3.OperationalError:
        return []
    # bm25() returns negative numbers, lower is better; rank order is what matters.
    return [dict(r) for r in rows]


def _semantic(db, q: str, limit: int) -> List[Dict]:
    v = embed.encode_query(q)
    if v is None:
        return []
    try:
        rows = db.execute(
            "SELECT c.rowid, c.doc_id, c.heading, c.text, v.distance AS score "
            "FROM chunks_vec v JOIN chunks c ON c.rowid = v.chunk_id "
            "WHERE v.embedding MATCH ? AND k = ? ORDER BY v.distance",
            (pack(v), limit)).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


def _rrf(weighted_lists, k: int) -> Dict[int, float]:
    """Weighted Reciprocal Rank Fusion over (list, weight) pairs."""
    out: Dict[int, float] = {}
    for lst, w in weighted_lists:
        for rank, row in enumerate(lst, start=1):
            out[row["rowid"]] = out.get(row["rowid"], 0.0) + w / (k + rank)
    return out


def search(q: str, top_k: Optional[int] = None, layers: Optional[List[str]] = None,
           max_per_doc: int = 2):
    """Return ranked chunks with their parent document metadata.

    `max_per_doc` keeps one verbose note from monopolising the result set. Three
    chunks of the same file is a worse answer context than three different files,
    and it makes the citation list look padded.
    """
    top_k = top_k or config.TOP_K
    if not q or not q.strip():
        return {"query": q, "mode": "empty", "hits": []}

    db = connect()
    vec_ok = load_vec(db)
    pool = max(top_k * config.POOL_MULT, 20)

    kw = _keyword(db, q, pool)
    sem = _semantic(db, q, pool) if vec_ok else []

    fused = _rrf([(l, w) for l, w in ((kw, config.W_KEYWORD),
                                      (sem, config.W_SEMANTIC)) if l],
                 config.RRF_K)
    if not fused:
        db.close()
        return {"query": q, "mode": "hybrid" if sem else "keyword", "hits": []}

    by_row = {r["rowid"]: r for r in list(kw) + list(sem)}
    in_kw = {r["rowid"] for r in kw}
    in_sem = {r["rowid"] for r in sem}

    order = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
    doc_cache: Dict[str, Dict] = {}
    per_doc: Dict[str, int] = {}
    hits = []

    for rowid, score in order:
        if len(hits) >= top_k:
            break
        row = by_row[rowid]
        doc_id = row["doc_id"]
        if per_doc.get(doc_id, 0) >= max_per_doc:
            continue
        if doc_id not in doc_cache:
            d = db.execute(
                "SELECT id, layer, ring, title, path FROM docs WHERE id=?",
                (doc_id,)).fetchone()
            if not d:
                continue
            doc_cache[doc_id] = dict(d)
        doc = doc_cache[doc_id]
        if layers and doc["layer"] not in layers:
            continue
        per_doc[doc_id] = per_doc.get(doc_id, 0) + 1
        hits.append({
            "chunk_id": rowid,
            "doc_id": doc_id,
            "title": doc["title"],
            "path": doc["path"],
            "layer": doc["layer"],
            "ring": doc["ring"],
            "heading": row["heading"],
            "text": row["text"],
            "score": round(score, 6),
            "matched": ("keyword" if rowid in in_kw else "") +
                       ("+semantic" if rowid in in_sem and rowid in in_kw
                        else "semantic" if rowid in in_sem else ""),
        })

    db.close()
    return {
        "query": q,
        "mode": "hybrid" if sem else "keyword",
        "counts": {"keyword": len(kw), "semantic": len(sem), "fused": len(fused)},
        "hits": hits,
    }


def index_status():
    try:
        db = connect()
        meta = {r["k"]: r["v"] for r in db.execute("SELECT k, v FROM meta")}
        docs = db.execute("SELECT COUNT(*) c FROM docs").fetchone()["c"]
        chunks = db.execute("SELECT COUNT(*) c FROM chunks").fetchone()["c"]
        vectors = 0
        if load_vec(db):
            try:
                vectors = db.execute(
                    "SELECT COUNT(*) c FROM chunks_vec").fetchone()["c"]
            except sqlite3.OperationalError:
                pass
        db.close()
        return {"exists": True, "docs": docs, "chunks": chunks,
                "vectors": vectors, "meta": meta, "embed": embed.status()}
    except Exception as e:                        # noqa: BLE001
        return {"exists": False, "error": str(e), "embed": embed.status()}
