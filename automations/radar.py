"""AI trend radar — scheduled capture into brain/raw/.

    python -m automations.radar              # capture today's signal
    python -m automations.radar --dry        # print, write nothing
    python -m automations.radar --only hackernews,arxiv

Writes ONE dated file per run into `brain/raw/`, with full provenance. It never
writes to `brain/wiki/` — raw capture is not knowledge, and the boundary is the
whole point of the layer. Distillation is a separate, deliberate step
(`automations/distill.py`), because an automation that promotes its own output to
knowledge is how a vault fills with unread material.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import sources

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "brain" / "raw"

GROUP_TITLES = {
    "hackernews": "Discussion — Hacker News",
    "lobsters": "Discussion — Lobsters",
    "arxiv": "Papers — arXiv (newest)",
    "hf-papers": "Papers — Hugging Face daily (community-curated)",
    "hf-models": "Models — trending on Hugging Face",
    "github": "Tools — new GitHub repos gaining stars",
}


def render(items, errors, when):
    by = {}
    for it in items:
        by.setdefault(it["source"], []).append(it)

    L = []
    L.append("---")
    L.append("captured: %s" % when.strftime("%Y-%m-%d"))
    L.append("captured_at: %s" % when.strftime("%Y-%m-%dT%H:%M:%SZ"))
    L.append("kind: radar")
    L.append("source: automations/radar.py")
    L.append("feeds: [%s]" % ", ".join(sorted(by)))
    L.append("items: %d" % len(items))
    L.append("---")
    L.append("")
    L.append("# AI radar — %s" % when.strftime("%Y-%m-%d"))
    L.append("")
    L.append("Automated capture. **Unread and unverified** — this is `raw/`, not "
             "knowledge. Distil anything that matters into `brain/wiki/` in your "
             "own words, then let this file rot.")
    L.append("")

    if errors:
        L.append("> Feeds that failed this run: "
                 + "; ".join("`%s` (%s)" % (k, v) for k, v in errors.items()))
        L.append("")

    for src in ["hf-papers", "arxiv", "github", "hf-models", "hackernews", "lobsters"]:
        got = by.get(src)
        if not got:
            continue
        L.append("## %s" % GROUP_TITLES.get(src, src))
        L.append("")
        for it in got:
            score = " · **%s**" % it["score"] if it.get("score") is not None else ""
            L.append("- [%s](%s)%s" % (it["title"].replace("]", ")"), it["url"], score))
            if it["summary"]:
                L.append("  %s" % it["summary"][:280])
            extra = it.get("extra") or {}
            bits = []
            if extra.get("authors"):
                bits.append(", ".join(extra["authors"]))
            if extra.get("lang"):
                bits.append(extra["lang"])
            if extra.get("hn"):
                bits.append("[HN](%s)" % extra["hn"])
            if extra.get("arxiv"):
                bits.append("[arXiv](%s)" % extra["arxiv"])
            if bits:
                L.append("  <sub>%s</sub>" % " · ".join(bits))
        L.append("")

    L.append("---")
    L.append("")
    L.append("## Triage")
    L.append("")
    L.append("- [ ] anything here that changes how the OS should work → "
             "`bin/os note \"<Title>\"` and write it in your own words")
    L.append("- [ ] anything that only *might* matter → leave it here, it will be "
             "in git history if you need it")
    L.append("- [ ] nothing worth keeping → delete this file, that is a valid outcome")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="print, write nothing")
    ap.add_argument("--only", default="", help="comma-separated feed names")
    ap.add_argument("--json", action="store_true", help="machine-readable summary")
    args = ap.parse_args()

    only = [s.strip() for s in args.only.split(",") if s.strip()] or None
    when = datetime.now(timezone.utc)

    items, errors = sources.gather(only)
    before = len(items)
    items = sources.dedupe(items)
    body = render(items, errors, when)

    summary = {
        "items_raw": before,
        "items_kept": len(items),
        "deduped": before - len(items),
        "feeds_ok": sorted({i["source"] for i in items}),
        "feeds_failed": errors,
        "when": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    if args.dry:
        print(body)
        print(json.dumps(summary, indent=2), file=sys.stderr)
        return 0

    if not items:
        print("radar: every feed failed, writing nothing", file=sys.stderr)
        print(json.dumps(summary, indent=2))
        return 1

    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / ("%s AI radar.md" % when.strftime("%Y-%m-%d"))
    path.write_text(body, encoding="utf-8")
    summary["path"] = str(path.relative_to(ROOT))
    print(json.dumps(summary, indent=2) if args.json
          else "radar → %s (%d items, %d deduped)"
               % (summary["path"], len(items), summary["deduped"]))
    if errors:
        print("  feeds failed: %s" % ", ".join(errors), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
