"""Research a topic across every keyless source, then write a sourced brief.

    python -m automations.research "context engineering for agents"
    python -m automations.research "sqlite vector search" --fetch 4
    python -m automations.research "prompt caching" --dry

Writes to `brain/raw/` with full provenance. This is a *gatherer*, not an author:
it collects and attributes, and the distillation into `brain/wiki/` stays a
deliberate human step. See brain/wiki/Provenance Or It Didn't Happen.md
"""
import argparse
import html
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automations import sources                       # noqa: E402

RAW = ROOT / "brain" / "raw"

TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
STRIP_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\n{3,}")


def readable(url, limit=2600):
    """Crude HTML-to-text. Deliberately not a dependency: the goal is enough
    context to judge whether a source is worth opening properly, not a faithful
    reproduction of the page."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": sources.UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            ctype = r.headers.get("Content-Type", "")
            raw = r.read(400_000)
        if "html" not in ctype and "text" not in ctype:
            return "(not text: %s)" % ctype.split(";")[0]
        text = raw.decode("utf-8", "replace")
        text = TAG_RE.sub(" ", text)
        text = STRIP_RE.sub(" ", text)
        text = html.unescape(text)
        text = re.sub(r"[ \t]+", " ", text)
        text = WS_RE.sub("\n\n", text).strip()
        return text[:limit] + ("…" if len(text) > limit else "")
    except Exception as e:                            # noqa: BLE001
        return "(fetch failed: %s: %s)" % (type(e).__name__, str(e)[:80])


def gather(topic, per_source=6):
    """Query every source with the topic. Each is best-effort."""
    found, errors = {}, {}

    attempts = [
        ("hackernews", lambda: sources.hacker_news(
            queries=(topic,), days=1400, min_points=5, limit=per_source)),
        ("arxiv", lambda: _arxiv_search(topic, per_source)),
        ("github", lambda: sources.github(query=topic, days=1400, limit=per_source)),
        ("hf-papers", lambda: [i for i in sources.hf_papers(40)
                               if _match(topic, i)][:per_source]),
        ("hf-models", lambda: [i for i in sources.hf_models(60)
                               if _match(topic, i)][:per_source]),
        ("lobsters", lambda: [i for i in sources.lobsters(40)
                              if _match(topic, i)][:per_source]),
    ]
    for name, fn in attempts:
        try:
            got = fn()
            if got:
                found[name] = got
        except Exception as e:                        # noqa: BLE001
            errors[name] = "%s: %s" % (type(e).__name__, str(e)[:90])
    return found, errors


def _match(topic, item):
    words = [w for w in re.split(r"\W+", topic.lower()) if len(w) > 3]
    blob = ("%s %s" % (item.get("title", ""), item.get("summary", ""))).lower()
    return any(w in blob for w in words) if words else False


def _arxiv_search(topic, limit):
    """AND the significant terms rather than requiring the exact phrase.

    `all:"context engineering for LLM agents"` returned zero results while the
    same words ANDed returned a full page — arXiv has the papers, it just does
    not have that literal string in that order.
    """
    import xml.etree.ElementTree as ET
    terms = [w for w in re.split(r"\W+", topic) if len(w) > 3]
    expr = " AND ".join('all:%s' % t for t in terms) if terms else 'all:"%s"' % topic
    q = urllib.parse.quote(expr)
    url = ("https://export.arxiv.org/api/query?search_query=%s"
           "&sortBy=relevance&max_results=%d" % (q, limit))
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(sources._get(url, parse="text"))
    out = []
    for e in root.findall("a:entry", ns):
        out.append(sources._item(
            "arxiv", (e.findtext("a:title", "", ns) or "").strip(),
            e.findtext("a:id", "", ns),
            summary=e.findtext("a:summary", "", ns),
            when=e.findtext("a:published", "", ns)))
    return out


def render(topic, found, errors, fetched, when):
    total = sum(len(v) for v in found.values())
    L = ["---",
         "captured: %s" % when.strftime("%Y-%m-%d"),
         "captured_at: %s" % when.strftime("%Y-%m-%dT%H:%M:%SZ"),
         "kind: research",
         "topic: %s" % topic,
         "source: automations/research.py",
         "results: %d" % total,
         "---", "",
         "# Research — %s" % topic, "",
         "Gathered from %d source(s), %d result(s). **Unverified capture** — "
         "distil into `brain/wiki/` in your own words before relying on any of it."
         % (len(found), total), ""]

    if errors:
        L += ["> Sources that failed: "
              + "; ".join("`%s` (%s)" % (k, v) for k, v in errors.items()), ""]

    for name in ("arxiv", "hf-papers", "github", "hf-models", "hackernews", "lobsters"):
        items = found.get(name)
        if not items:
            continue
        L += ["## %s" % name, ""]
        for it in items:
            sc = " · **%s**" % it["score"] if it.get("score") is not None else ""
            L.append("- [%s](%s)%s" % (it["title"].replace("]", ")"), it["url"], sc))
            if it["summary"]:
                L.append("  %s" % it["summary"][:320])
        L.append("")

    if fetched:
        L += ["---", "", "## Fetched page text", "",
              "Rough extraction, for judging relevance only. Open the source "
              "before quoting it.", ""]
        for url, text in fetched:
            L += ["### %s" % url, "", "```", text, "```", ""]

    L += ["---", "", "## Open questions", "",
          "- [ ] what does this change about how the OS should work?",
          "- [ ] which single claim here would be most expensive to be wrong about?",
          "- [ ] is there an existing note this contradicts? reconcile, don't append.",
          ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("topic", nargs="+")
    ap.add_argument("--fetch", type=int, default=0,
                    help="also fetch page text for the top N results")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    topic = " ".join(args.topic).strip()
    when = datetime.now(timezone.utc)

    print("research: gathering on %r…" % topic, file=sys.stderr)
    found, errors = gather(topic)
    total = sum(len(v) for v in found.values())
    if not total:
        print("research: nothing found. Try broader terms.", file=sys.stderr)
        if errors:
            for k, v in errors.items():
                print("  %s: %s" % (k, v), file=sys.stderr)
        return 1

    fetched = []
    if args.fetch:
        ranked = sources.dedupe([i for v in found.values() for i in v])
        for it in ranked[:args.fetch]:
            if not it["url"].startswith("http"):
                continue
            print("  fetching %s" % it["url"][:80], file=sys.stderr)
            fetched.append((it["url"], readable(it["url"])))

    body = render(topic, found, errors, fetched, when)
    if args.dry:
        print(body)
        return 0

    RAW.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w\s-]", "", topic)[:60].strip()
    dest = RAW / ("%s research — %s.md" % (when.strftime("%Y-%m-%d"), slug))
    dest.write_text(body, encoding="utf-8")
    print("research → %s (%d results from %d sources)"
          % (dest.relative_to(ROOT), total, len(found)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
