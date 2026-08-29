"""Measure retrieval quality instead of guessing at it.

    python -m server.tools.eval_retrieval          # score current config
    python -m server.tools.eval_retrieval --sweep   # grid-search the knobs

Each probe is a paraphrase that deliberately shares little vocabulary with its
target note, plus a few exact-match probes that keyword search must still win.
That mix is the point: a config that aces paraphrases but loses filename lookups
is not an improvement.

Add a probe whenever you catch the UI failing to find something you knew was
there. A benchmark that only contains queries you already pass is decoration.
"""
import argparse
import contextlib
import sys

from .. import config, search, settings


@contextlib.contextmanager
def _knobs(over):
    """Temporarily override runtime settings for one scored run.

    config reads through to settings, so the sweep has to move the settings layer
    rather than assigning module attributes that no longer exist.
    """
    before = {k: settings.get(k) for k in over}
    try:
        settings.update({k: v for k, v in over.items()})
        yield
    finally:
        settings.update(before)
from ..index import connect, load_vec

# (query, expected top document title)
PROBES = [
    # paraphrase — semantic should carry these
    ("how do I stop my assistant forgetting everything overnight", "Git Is The Disk"),
    ("why keep memory in version control instead of a database", "Git Is The Disk"),
    ("is a similarity index worth the hassle for a small collection",
     "Grep Beats Embeddings Here"),
    ("can I use my subscription from one company in another company's tool",
     "Model Access Is Not Transferable"),
    ("what if the agent tries the same broken thing over and over", "Ralph Loop"),
    ("checking which features a new tool actually supports",
     "Harness Capability Matrix"),
    ("the config file that runs at the start of every conversation",
     "Steering as Boot Loader"),
    ("putting the notes on a server that is always awake",
     "Local Runtime Closes The Gaps"),
    # exact / near-exact — keyword must still win these
    ("Grep Beats Embeddings", "Grep Beats Embeddings Here"),
    ("deploy-always-on", "deploy-always-on"),
    # Name lookups. Added after watching the UI fail every one of these: typing a
    # note's name is the most common query in a personal vault, and before the
    # name nudge went in "AGENTS.md" did not return AGENTS.md at all.
    ("ralph", "Ralph Loop"),
    ("AGENTS.md", "AGENTS.md"),
    ("second-brain", "second-brain"),
    ("loop-engineering", "loop-engineering"),
    ("vault conventions", "10-vault-conventions"),
    ("harden-agentos", "harden-agentos"),
]


def _titles(db, rows):
    out = []
    for r in rows:
        d = db.execute("SELECT title FROM docs WHERE id=?",
                       (r["doc_id"],)).fetchone()
        t = d["title"] if d else "?"
        if t not in out:
            out.append(t)
    return out


def score(db, pool_mult, w_kw, w_sem, rrf_k, mode="hybrid", w_title=None):
    """Score every probe.

    Fusion is search.fuse(), not a copy of it. The evaluator used to reimplement
    the fusion inline, so a change to how the app ranks results was invisible to
    the benchmark whose entire job is catching ranking regressions.
    """
    h1 = h5 = 0
    misses = []
    saved = {k: getattr(config, k) for k in
             ("W_KEYWORD", "W_SEMANTIC", "RRF_K", "W_TITLE")}
    over = {"W_KEYWORD": w_kw, "W_SEMANTIC": w_sem, "RRF_K": rrf_k}
    if w_title is not None:
        over["W_TITLE"] = w_title
    for q, want in PROBES:
        pool = max(config.TOP_K * pool_mult, 20)
        kw = search._keyword(db, q, pool) if mode != "sem" else []
        sem = search._semantic(db, q, pool) if mode != "kw" else []
        with _knobs(over):
            fused, _ = search.fuse(db, q, kw, sem)
        by = {r["rowid"]: r for r in list(kw) + list(sem)}
        ordered = [by[rid] for rid, _ in sorted(fused.items(), key=lambda kv: -kv[1])]
        titles = _titles(db, ordered)
        if titles[:1] == [want]:
            h1 += 1
        if want in titles[:5]:
            h5 += 1
        else:
            misses.append((q, want, titles[:3]))
    del saved
    return h1, h5, misses


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true")
    args = ap.parse_args()

    db = connect()
    if not load_vec(db):
        print("sqlite-vec unavailable — keyword-only, semantic probes will fail",
              file=sys.stderr)
    n = len(PROBES)

    if args.sweep:
        print("%-6s %-5s %-6s %-4s %-7s %-8s %s"
              % ("poolx", "w_kw", "w_sem", "k", "w_title", "top-1", "top-5"))
        print("-" * 56)
        best = None
        for pm in (4, 6, 8):
            for wk, ws in ((1, 1), (1, 1.5), (1, 2), (1, 3), (0.7, 1.3)):
                for k in (10, 20, 60):
                    for wt in (0.0, 0.04, 0.08, 0.15, 0.3):
                        h1, h5, _ = score(db, pm, wk, ws, k, "hybrid", wt)
                        if best is None or (h1, h5) > best[:2]:
                            best = (h1, h5, pm, wk, ws, k, wt)
                        print("%-6s %-5s %-6s %-4s %-7s %d/%-6d %d/%d"
                              % (pm, wk, ws, k, wt, h1, n, h5, n))
        print("\nbest: top1=%d/%d top5=%d/%d  POOL_MULT=%d W_KEYWORD=%s "
              "W_SEMANTIC=%s RRF_K=%d W_TITLE=%s"
              % (best[0], n, best[1], n, *best[2:]))
        return

    print("config: POOL_MULT=%d W_KEYWORD=%s W_SEMANTIC=%s W_TITLE=%s RRF_K=%d "
          "TOP_K=%d\n"
          % (config.POOL_MULT, config.W_KEYWORD, config.W_SEMANTIC,
             config.W_TITLE, config.RRF_K, config.TOP_K))
    for mode in ("kw", "sem", "hybrid"):
        h1, h5, misses = score(db, config.POOL_MULT, config.W_KEYWORD,
                               config.W_SEMANTIC, config.RRF_K, mode,
                               config.W_TITLE)
        print("%-7s top-1 %d/%d   top-5 %d/%d" % (mode, h1, n, h5, n))
        if mode == "hybrid" and misses:
            print("\n  misses:")
            for q, want, got in misses:
                print("    %-52s want %-28s got %s" % (q[:52], want, got))


if __name__ == "__main__":
    main()
