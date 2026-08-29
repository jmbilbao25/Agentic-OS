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


WORDS = re.compile(r"[a-z0-9]+")


def _norm(s: str):
    return WORDS.findall((s or "").lower())


def name_affinity(query: str, title: str, path: str) -> float:
    """How much a query looks like it is *naming* a document, from 0 to 1.

    Why this exists: neither half of the hybrid can see a title.

    BM25 indexes `title`, but every chunk of a document carries the *same* title,
    so a title match lifts all of a document's chunks equally and never
    distinguishes that document from any other — it cancels out in the ranking.
    The vector side embeds `heading + text`, so the title is not in the vector at
    all. The result was that the single most common query in a personal vault —
    typing a note's name to jump to it — was the thing the ranker was worst at.
    Measured before this: "AGENTS.md" did not return AGENTS.md in the top four,
    and "ralph" put Ralph Loop third behind two notes that merely mention it.

    Deliberately a small bounded nudge, not an override: a strong agreement
    between keyword and vector search should still be able to win, because
    sometimes the words you typed really are a topic and not a filename.
    """
    q = _norm(query)
    if not q:
        return 0.0

    stem = path.rsplit("/", 1)[-1]
    if stem.endswith(".md"):
        stem = stem[:-3]

    best = 0.0
    for cand in (title, stem):
        c = _norm(cand)
        if not c:
            continue
        if q == c:
            return 1.0                          # named it exactly
        # A prefix either way: "ralph" for "Ralph Loop", or someone typing the
        # title plus a stray word.
        if len(q) < len(c) and c[:len(q)] == q:
            best = max(best, 0.85)
        elif len(c) < len(q) and q[:len(c)] == c:
            best = max(best, 0.7)
        cset, qset = set(c), set(q)
        covered = len(qset & cset) / len(qset)
        if qset <= cset:
            best = max(best, 0.75)              # every word you typed is in the name
        elif covered >= 0.5:
            best = max(best, 0.5 * covered)
    return best


def fuse(db, q: str, kw: List[Dict], sem: List[Dict]):
    """Combine the two rankings and apply the name nudge.

    Lives here, and is imported by tools/eval_retrieval.py, so that the thing the
    benchmark measures is the thing the app runs. The evaluator used to reimplement
    fusion inline, which meant any change to ranking was invisible to the
    benchmark that existed to catch ranking regressions.

    Returns (scores_by_rowid, name_affinity_by_doc_id).
    """
    fused = _rrf([(l, w) for l, w in ((kw, config.W_KEYWORD),
                                      (sem, config.W_SEMANTIC)) if l],
                 config.RRF_K)
    if not fused:
        return {}, {}

    rows = {r["rowid"]: r for r in list(kw) + list(sem)}
    doc_ids = {r["doc_id"] for r in rows.values()}

    named: Dict[str, float] = {}
    w_title = config.W_TITLE
    if w_title:
        marks = ",".join("?" * len(doc_ids))
        for d in db.execute(
                "SELECT id, title, path FROM docs WHERE id IN (%s)" % marks,
                tuple(doc_ids)):
            aff = name_affinity(q, d["title"], d["path"])
            if aff:
                named[d["id"]] = aff

        # An EXACT name match is a different intent from a topical one. Typing a
        # document's whole name is navigation: you know what you want and you want
        # it first. A partial match is a guess, and stays a gentle nudge.
        #
        # Without the split, "AGENTS.md" lost to a note that merely mentions the
        # kernel — the kernel appeared only in the keyword pool while that note
        # appeared in both, and RRF's two contributions beat one plus a 0.08
        # nudge. Raising W_TITLE globally would have over-boosted every fuzzy
        # match in order to fix one navigational case.
        w_exact = getattr(config, "W_TITLE_EXACT", 0.45)
        for rowid, row in rows.items():
            aff = named.get(row["doc_id"])
            if not aff:
                continue
            fused[rowid] += w_exact if aff >= 1.0 else w_title * aff

    return fused, named


def search(q: str, top_k: Optional[int] = None, layers: Optional[List[str]] = None,
           max_per_doc: Optional[int] = None):
    """Return ranked chunks with their parent document metadata.

    `max_per_doc` keeps one verbose note from monopolising the result set. Three
    chunks of the same file is a worse answer context than three different files,
    and it makes the citation list look padded.
    """
    top_k = top_k or config.TOP_K
    max_per_doc = max_per_doc or config.MAX_PER_DOC
    if not q or not q.strip():
        return {"query": q, "mode": "empty", "hits": []}

    db = connect()
    vec_ok = load_vec(db)
    pool = max(top_k * config.POOL_MULT, 20)

    kw = _keyword(db, q, pool)
    sem = _semantic(db, q, pool) if vec_ok else []

    fused, named = fuse(db, q, kw, sem)
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
