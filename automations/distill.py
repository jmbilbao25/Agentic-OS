"""Turn raw captures into a written digest.

    python -m automations.distill                 # newest unprocessed capture
    python -m automations.distill --file "brain/raw/2026-08-29 AI radar.md"
    python -m automations.distill --dry

Reads from `brain/raw/`, writes to `brain/output/`. It deliberately does NOT
write to `brain/wiki/`: a machine may summarise, but only a human (or a human's
explicit instruction) promotes something to knowledge. Automated promotion is how
a vault fills up with confident material nobody has read.

The digest is graded, not flat. Its job is to tell you what deserves your
attention and what to ignore — a summary that treats 87 items as equally
important has done nothing useful.
"""
import argparse
import asyncio
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server import llm                                # noqa: E402
from server import settings as srv_settings            # noqa: E402

RAW = ROOT / "brain" / "raw"
OUT = ROOT / "brain" / "output"

PROMPT = """You are triaging an automated feed capture for someone who runs a \
personal agentic OS: a markdown second brain in git, a hybrid-search server, and \
scheduled routines. They are technical, time-poor, and allergic to hype.

From the capture below, produce a digest in this exact structure:

## Worth your time
Up to 4 items. For each: **[title](url)** then ONE sentence on why it matters to \
someone building agent infrastructure. Only include something if you can name a \
concrete consequence. If nothing qualifies, write "Nothing this run."

## Worth knowing about
Up to 6 items, one line each, same link format. Things to recognise the name of \
without reading.

## Patterns
2-3 bullets on what the capture as a whole suggests — where effort is \
concentrating, what is repeating, what is conspicuously absent. This is the part \
with actual value; be specific and avoid restating the items.

## Skip
One or two lines naming what dominated the capture but does not deserve \
attention, and why.

Rules:
- Never invent a title, URL, or finding. Only use what is in the capture.
- No preamble, no "in conclusion", no praise for the papers.
- Prefer plain words. If a sentence would survive being deleted, delete it.
- Judge relevance to *agent infrastructure and personal knowledge systems*, not \
to AI research in general.

CAPTURE:
"""


def newest_capture():
    files = sorted([p for p in RAW.glob("*.md") if p.name != "README.md"],
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def already_done(capture_stem):
    """A digest names its source in frontmatter, so re-runs are detectable."""
    for p in OUT.glob("*.md"):
        if capture_stem in p.read_text(encoding="utf-8")[:400]:
            return p
    return None


async def run(text):
    """One non-streaming call.

    `llm.complete()` rather than `llm.stream()`: a digest is written to a file,
    so nobody is watching it arrive token by token, and complete() hands back a
    structured {text, model, usage, error} instead of an event stream this caller
    would only have to reassemble.
    """
    messages = [
        {"role": "system", "content": "You write terse, honest technical digests."},
        {"role": "user", "content": PROMPT + text[:24000]},
    ]
    return await llm.complete(messages, temperature=0.2)


def model_chain():
    """Primary + fallbacks, for the log line. Reads settings so it reflects
    whatever the UI last saved, not just what is in .env."""
    primary = srv_settings.get("LLM_MODEL") or "(unset)"
    extra = srv_settings.get("LLM_FALLBACK_MODELS") or []
    if isinstance(extra, str):
        extra = [m.strip() for m in extra.split(",") if m.strip()]
    return [primary] + list(extra)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-digest even if done")
    args = ap.parse_args()

    src = Path(args.file) if args.file else newest_capture()
    if not src or not src.exists():
        print("distill: no capture found in brain/raw/ — run: bin/os radar",
              file=sys.stderr)
        return 1

    if not args.force and not args.dry:
        prev = already_done(src.stem)
        if prev:
            print("distill: already digested (%s) — use --force to redo"
                  % prev.relative_to(ROOT))
            return 0

    if not llm.configured():
        print("distill: no inference key. Set OPENROUTER_API_KEY in server/.env",
              file=sys.stderr)
        return 1

    text = src.read_text(encoding="utf-8")
    chain = model_chain()
    print("distill: reading %s (%d chars) via %s"
          % (src.name, len(text), ", ".join(chain)), file=sys.stderr)

    res = asyncio.run(run(text))
    body = (res.get("text") or "").strip()
    used = res.get("model") or chain[0]

    if res.get("error"):
        print("distill: %s" % res["error"], file=sys.stderr)
        return 1
    # An empty answer is a failure, not a result. Some free models return no
    # content at all and put everything in a reasoning field; writing the empty
    # string to a file would look like a successful run that produced nothing.
    if not body:
        print("distill: %s returned an empty digest — nothing written" % used,
              file=sys.stderr)
        return 1

    when = datetime.now(timezone.utc)
    n_items = re.search(r"^items:\s*(\d+)", text, re.M)
    doc = "\n".join([
        "---",
        "created: %s" % when.strftime("%Y-%m-%d"),
        "status: draft",
        "channel: internal",
        "kind: digest",
        "source_capture: %s" % src.stem,
        "model: %s" % used,
        "---",
        "",
        "# AI digest — %s" % when.strftime("%Y-%m-%d"),
        "",
        "Distilled from `%s` (%s items) by `automations/distill.py`. "
        "Machine-written triage: trust the links, verify the claims."
        % (src.relative_to(ROOT), n_items.group(1) if n_items else "?"),
        "",
        body,
        "",
        "---",
        "Drew on: `%s`" % src.relative_to(ROOT),
        "",
    ])

    if args.dry:
        print(doc)
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / ("%s AI digest.md" % when.strftime("%Y-%m-%d"))
    dest.write_text(doc, encoding="utf-8")
    print("digest → %s" % dest.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
