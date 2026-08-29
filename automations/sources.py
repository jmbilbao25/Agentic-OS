"""Keyless signal sources.

Every source here works with **no API key and no account**, verified by probe.
That constraint is deliberate: a routine that needs a credential is a routine
that breaks silently when the credential expires, on a box nobody is watching.

Each fetcher returns a list of Item dicts. Failures are captured per-source and
reported, never raised — one dead feed must not kill a scheduled run.
"""
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

UA = "AgentOS/1.0 (personal second brain; +https://github.com/jmbilbao25/Agentic-OS)"
TIMEOUT = 25


def _get(url, parse="json"):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json,text/xml,*/*",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read()
    if parse == "json":
        return json.loads(raw)
    return raw.decode("utf-8", "replace")


def _item(source, title, url, summary="", score=None, when=None, extra=None):
    return {
        "source": source,
        "title": (title or "").strip()[:300],
        "url": url or "",
        "summary": re.sub(r"\s+", " ", (summary or "")).strip()[:600],
        "score": score,
        "when": when or "",
        "extra": extra or {},
    }


# --------------------------------------------------------------------- sources

HN_QUERIES = ("AI", "LLM", "agent", "prompt", "model")


def hacker_news(queries=HN_QUERIES, days=4, min_points=25, limit=8):
    """Hacker News via the Algolia API — what practitioners are arguing about.

    Several narrow queries rather than one wide `A OR B OR C`. Algolia's relevance
    on a multi-term OR combined with a points floor returned almost nothing (two
    hits for a 48-hour window), while the same floor per single term returns a
    full page each. Downstream dedupe collapses the overlap, so the cost of
    running five queries is a few hundred milliseconds and much better recall.
    """
    since = int(datetime.now(timezone.utc).timestamp()) - days * 86400
    out = []
    for q in queries:
        url = ("https://hn.algolia.com/api/v1/search?"
               + urllib.parse.urlencode({
                   "query": q, "tags": "story",
                   "numericFilters": "created_at_i>%d,points>%d" % (since, min_points),
                   "hitsPerPage": limit}))
        try:
            hits = _get(url).get("hits", [])
        except Exception:                            # noqa: BLE001 - one term failing is fine
            continue
        for h in hits:
            oid = h.get("objectID")
            out.append(_item(
                "hackernews", h.get("title"),
                h.get("url") or "https://news.ycombinator.com/item?id=%s" % oid,
                summary="%s points · %s comments" % (h.get("points"), h.get("num_comments")),
                score=h.get("points"), when=h.get("created_at"),
                extra={"hn": "https://news.ycombinator.com/item?id=%s" % oid}))
    return out


def arxiv(categories=("cs.AI", "cs.CL", "cs.LG"), limit=12):
    """arXiv Atom feed, newest first. Note the API is HTTPS-only — the http://
    endpoint 301s and an unprepared client silently gets nothing."""
    q = "+OR+".join("cat:%s" % c for c in categories)
    url = ("https://export.arxiv.org/api/query?search_query=%s"
           "&sortBy=submittedDate&sortOrder=descending&max_results=%d" % (q, limit))
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(_get(url, parse="text"))
    out = []
    for e in root.findall("a:entry", ns):
        title = (e.findtext("a:title", "", ns) or "").strip()
        out.append(_item(
            "arxiv", title, e.findtext("a:id", "", ns),
            summary=e.findtext("a:summary", "", ns),
            when=e.findtext("a:published", "", ns),
            extra={"authors": [a.findtext("a:name", "", ns)
                               for a in e.findall("a:author", ns)][:4]}))
    return out


def hf_papers(limit=12):
    """Hugging Face daily papers — community-curated, so it filters arXiv volume
    down to what people actually read."""
    out = []
    for p in _get("https://huggingface.co/api/daily_papers?limit=%d" % limit):
        paper = p.get("paper", {}) or {}
        pid = paper.get("id", "")
        out.append(_item(
            "hf-papers", paper.get("title") or p.get("title"),
            "https://huggingface.co/papers/%s" % pid if pid else "",
            summary=paper.get("summary", ""),
            score=paper.get("upvotes"), when=p.get("publishedAt", ""),
            extra={"arxiv": "https://arxiv.org/abs/%s" % pid if pid else ""}))
    return out


def hf_models(limit=12):
    """Trending models. The useful signal is *what shape* of model is climbing —
    size, modality, license — not the leaderboard position."""
    url = ("https://huggingface.co/api/models?sort=trendingScore&direction=-1"
           "&limit=%d&full=false" % limit)
    out = []
    for m in _get(url):
        mid = m.get("modelId") or m.get("id", "")
        out.append(_item(
            "hf-models", mid, "https://huggingface.co/%s" % mid,
            summary="%s · %s downloads · %s likes" % (
                m.get("pipeline_tag", "?"), m.get("downloads", 0), m.get("likes", 0)),
            score=m.get("likes"), when=m.get("createdAt", ""),
            extra={"task": m.get("pipeline_tag", "")}))
    return out


def github(query="ai agent", days=30, limit=12):
    """GitHub search, unauthenticated (60 req/hr — fine for a daily routine).
    Filtered to recently *created* repos so it surfaces new tools rather than
    the same perennial giants."""
    since = datetime.now(timezone.utc).timestamp() - days * 86400
    d = datetime.fromtimestamp(since, timezone.utc).strftime("%Y-%m-%d")
    url = ("https://api.github.com/search/repositories?"
           + urllib.parse.urlencode({
               "q": "%s created:>%s stars:>25" % (query, d),
               "sort": "stars", "order": "desc", "per_page": limit}))
    out = []
    for r in _get(url).get("items", []):
        out.append(_item(
            "github", r.get("full_name"), r.get("html_url"),
            summary=r.get("description") or "",
            score=r.get("stargazers_count"), when=r.get("created_at"),
            extra={"lang": r.get("language") or "", "stars": r.get("stargazers_count")}))
    return out


def lobsters(limit=12):
    """Lobsters AI tag — smaller and more engineering-flavoured than HN."""
    out = []
    for s in _get("https://lobste.rs/t/ai.json")[:limit]:
        out.append(_item(
            "lobsters", s.get("title"), s.get("url") or s.get("short_id_url", ""),
            summary="%s points · %s comments" % (s.get("score"), s.get("comment_count")),
            score=s.get("score"), when=s.get("created_at", ""),
            extra={"tags": s.get("tags", [])}))
    return out


FEEDS = {
    "hackernews": hacker_news,
    "arxiv": arxiv,
    "hf-papers": hf_papers,
    "hf-models": hf_models,
    "github": github,
    "lobsters": lobsters,
}


def gather(only=None):
    """Run every feed. Returns (items, errors) — a dead feed is reported, not fatal."""
    items, errors = [], {}
    for name, fn in FEEDS.items():
        if only and name not in only:
            continue
        try:
            got = fn()
            items.extend(got)
        except Exception as e:                       # noqa: BLE001
            errors[name] = "%s: %s" % (type(e).__name__, e)
    return items, errors


def dedupe(items):
    """Collapse by normalised URL, then by normalised title. The same paper
    routinely arrives via arXiv, HF papers, and HN on the same morning."""
    seen_url, seen_title, out = set(), set(), []

    def norm_url(u):
        u = re.sub(r"^https?://(www\.)?", "", u or "").rstrip("/")
        u = re.sub(r"[?#].*$", "", u)
        return re.sub(r"^arxiv\.org/(abs|pdf)/", "arxiv/", u).replace("v1", "")

    def norm_title(t):
        return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()

    for it in sorted(items, key=lambda x: -(x.get("score") or 0)):
        u, t = norm_url(it["url"]), norm_title(it["title"])
        if (u and u in seen_url) or (t and t in seen_title):
            continue
        if u:
            seen_url.add(u)
        if t:
            seen_title.add(t)
        out.append(it)
    return out
