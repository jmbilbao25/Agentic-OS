"""Build the search index from markdown.

The index is a cache and nothing else: it is derived entirely from `brain/`, and
deleting it is a valid repair step. Markdown is the source of truth.
See brain/wiki/Grep Beats Embeddings Here.md

  python -m server.index          # incremental (skips unchanged files)
  python -m server.index --full   # rebuild from scratch
"""
import json
import logging
import sqlite3
import struct
import sys
import time

from . import config, embed, vault

log = logging.getLogger("agentos.index")

SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (
  id TEXT PRIMARY KEY, layer TEXT, ring TEXT, title TEXT, path TEXT,
  body TEXT, fm TEXT, tags TEXT, links TEXT,
  mtime REAL, size INTEGER, sha TEXT
);
CREATE TABLE IF NOT EXISTS chunks (
  rowid INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id TEXT, ord INTEGER, heading TEXT, text TEXT
);
CREATE INDEX IF NOT EXISTS chunks_doc ON chunks(doc_id);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  text, heading, title, tags, doc_id UNINDEXED,
  tokenize = 'porter unicode61'
);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def connect(path=None):
    db = sqlite3.connect(str(path or config.DB))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    return db


def load_vec(db) -> bool:
    """Attach sqlite-vec if present. Vectors are optional by design."""
    try:
        import sqlite_vec
        db.enable_load_extension(True)
        sqlite_vec.load(db)
        db.enable_load_extension(False)
        db.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0("
            "chunk_id INTEGER PRIMARY KEY, embedding FLOAT[%d])" % config.EMBED_DIM)
        return True
    except Exception as e:                       # noqa: BLE001
        log.info("sqlite-vec unavailable (%s) — keyword-only index", e)
        return False


def pack(v):
    return struct.pack("%df" % len(v), *v)


def build(full=False):
    t0 = time.time()
    config.DB.parent.mkdir(parents=True, exist_ok=True)
    db = connect()
    db.executescript(SCHEMA)
    vec_ok = load_vec(db)

    docs = vault.load()
    if not docs:
        log.warning("no documents found under %s", config.VAULT)

    if full:
        for t in ("docs", "chunks", "chunks_fts"):
            db.execute("DELETE FROM %s" % t)
        if vec_ok:
            db.execute("DELETE FROM chunks_vec")

    known = {r["id"]: r["sha"] for r in db.execute("SELECT id, sha FROM docs")}
    seen, changed = set(), []

    for d in docs:
        seen.add(d.id)
        if known.get(d.id) == d.sha and not full:
            continue
        changed.append(d)

    # Drop rows for documents that changed or vanished.
    gone = [i for i in known if i not in seen]
    for doc_id in [d.id for d in changed] + gone:
        ids = [r["rowid"] for r in
               db.execute("SELECT rowid FROM chunks WHERE doc_id=?", (doc_id,))]
        db.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
        db.execute("DELETE FROM chunks_fts WHERE doc_id=?", (doc_id,))
        if vec_ok and ids:
            db.executemany("DELETE FROM chunks_vec WHERE chunk_id=?",
                           [(i,) for i in ids])
        if doc_id in gone:
            db.execute("DELETE FROM docs WHERE id=?", (doc_id,))

    n_chunks = 0
    pending = []          # (rowid, text) awaiting embedding

    for d in changed:
        db.execute(
            "INSERT OR REPLACE INTO docs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (d.id, d.layer, d.ring, d.title, d.path, d.body, json.dumps(d.fm),
             json.dumps(d.tags), json.dumps(d.links), d.mtime, d.size, d.sha))
        for c in vault.chunk(d):
            cur = db.execute(
                "INSERT INTO chunks (doc_id, ord, heading, text) VALUES (?,?,?,?)",
                (c.doc_id, c.ord, c.heading, c.text))
            rid = cur.lastrowid
            db.execute(
                "INSERT INTO chunks_fts (rowid, text, heading, title, tags, doc_id) "
                "VALUES (?,?,?,?,?,?)",
                (rid, c.text, c.heading, d.title, " ".join(d.tags), d.id))
            pending.append((rid, "%s\n%s" % (c.heading, c.text)))
            n_chunks += 1

    db.commit()

    # Backfill: any chunk without a vector, regardless of whether its document
    # changed. Without this an incremental run can never repair a partial index —
    # unchanged documents are skipped by content hash, so chunks orphaned by a
    # failed embed batch would stay vector-less until someone thought to run
    # --full. Self-healing matters more than the few queries this costs.
    if vec_ok and embed.available():
        have = {r[0] for r in pending}
        try:
            orphans = db.execute(
                "SELECT rowid, heading, text FROM chunks "
                "WHERE rowid NOT IN (SELECT chunk_id FROM chunks_vec)").fetchall()
        except sqlite3.OperationalError:
            orphans = []
        added = 0
        for row in orphans:
            if row["rowid"] in have:
                continue
            pending.append((row["rowid"], "%s\n%s" % (row["heading"], row["text"])))
            added += 1
        if added:
            log.info("backfilling %d chunk(s) that had no vector", added)

    embedded, failed = 0, 0
    if vec_ok and pending and embed.available():
        B = 32
        for i in range(0, len(pending), B):
            batch = pending[i:i + B]
            vecs = embed.encode([t for _, t in batch])
            if not vecs:
                # Keep going rather than break. Aborting on the first bad batch
                # used to leave the index silently partial while still reporting
                # itself as hybrid; a gap that is counted and surfaced can be
                # repaired by re-running, a gap that is hidden cannot.
                failed += len(batch)
                log.warning("embed batch %d-%d failed; continuing",
                            i, i + len(batch))
                continue
            db.executemany(
                "INSERT OR REPLACE INTO chunks_vec (chunk_id, embedding) VALUES (?,?)",
                [(rid, pack(v)) for (rid, _), v in zip(batch, vecs)])
            embedded += len(batch)
            db.commit()
            log.info("embedded %d/%d", embedded, len(pending))
        if failed:
            log.warning("%d chunk(s) have no vector — re-run to repair", failed)

    total = db.execute("SELECT COUNT(*) c FROM chunks").fetchone()["c"]
    vtotal = (db.execute("SELECT COUNT(*) c FROM chunks_vec").fetchone()["c"]
              if vec_ok else 0)

    # Mode describes the INDEX, not this run. An incremental run with nothing to
    # do embeds zero chunks, and deriving the mode from that count made a fully
    # hybrid index report itself as keyword-only the first time the sync timer
    # fired. What matters is whether vectors are present and loadable.
    mode = "hybrid" if (vec_ok and vtotal) else "keyword"
    for k, v in (("built", str(int(time.time()))), ("mode", mode),
                 ("docs", str(len(docs))), ("embed_model", config.EMBED_MODEL),
                 ("vault", str(config.VAULT))):
        db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (k, v))
    db.commit()
    db.close()

    return {
        "mode": mode, "docs": len(docs), "changed": len(changed),
        "removed": len(gone), "chunks_written": n_chunks,
        "chunks_total": total, "vectors_total": vtotal,
        "embedded_now": embedded, "embed_failed": failed,
        "coverage": round(vtotal / total, 3) if total else 0.0,
        "seconds": round(time.time() - t0, 2),
        "embed": embed.status(),
    }


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    full = "--full" in sys.argv
    s = build(full=full)
    print(json.dumps(s, indent=2))
    if s["mode"] == "keyword":
        print("\nnote: keyword-only. Install sqlite-vec + fastembed for semantic "
              "search:\n  pip install sqlite-vec fastembed", file=sys.stderr)


if __name__ == "__main__":
    main()
