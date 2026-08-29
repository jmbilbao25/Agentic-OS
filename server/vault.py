"""Read the markdown vault. No dependencies — the vault must stay readable by
anything, forever.

This module is the only place that knows what the vault looks like on disk.
Everything downstream (index, search, UI) consumes Doc/Chunk objects.
"""
import hashlib
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from . import config

WIKILINK = re.compile(r"\[\[([^\]|#]+)")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.M)
CODEFENCE = re.compile(r"```.*?```", re.S)
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?", re.S)
TAGSPLIT = re.compile(r"[,\s]+")

# Which ARMS ring each vault layer belongs to. The orbit UI reads this.
RING = {
    "wiki": "memory",
    "raw": "memory",
    "journal": "memory",
    "decisions": "memory",
    "output": "applications",
    "loops": "routines",
    "skills": "skills",
    "config": "skills",
}


@dataclass
class Chunk:
    doc_id: str
    ord: int
    heading: str
    text: str


@dataclass
class Doc:
    id: str            # stable: layer/stem
    layer: str
    ring: str
    title: str
    path: str          # repo-relative
    body: str          # frontmatter stripped
    raw: str           # as on disk
    fm: Dict[str, str] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    links: List[str] = field(default_factory=list)
    mtime: float = 0.0
    size: int = 0
    sha: str = ""

    def public(self):
        d = asdict(self)
        d.pop("raw", None)
        return d


def parse_frontmatter(text):
    m = FRONTMATTER.match(text)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip("[]")
    return fm, text[m.end():]


def _tags(fm):
    raw = fm.get("tags", "") or ""
    return [t.strip().strip("'\"") for t in TAGSPLIT.split(raw) if t.strip()]


def _title(body, fallback, fm=None):
    """Prefer an explicit frontmatter title, then a *sole* H1, then the filename.

    The sole-H1 rule matters: loop ledgers use top-level headings as section
    markers (`# Goal`, `# Steps`, `# Notes`), so taking the first H1 would title
    every loop "Goal". A document with one H1 is using it as a title; a document
    with several is using them as structure.
    """
    fm = fm or {}
    for key in ("title", "loop"):
        if fm.get(key):
            return fm[key].strip()
    h1 = re.findall(r"^#\s+(.+)$", body, re.M)
    if len(h1) == 1:
        return h1[0].strip()
    return fallback


def load_system() -> List[Doc]:
    """The OS's own files: the kernel and the skills.

    These are not vault content, but they belong on the orbit map — the whole
    point of an ARMS view is seeing skills and memory in one picture. The kernel
    is the centre; skills form the innermost ring.
    """
    out = []
    root = config.VAULT.parent

    kernel = root / "AGENTS.md"
    if kernel.is_file():
        d = _read(kernel, "kernel", id_override="kernel/AGENTS")
        d.ring = "core"
        d.title = "AGENTS.md"
        out.append(d)

    for skill in sorted((root / "config" / "skills").glob("*/SKILL.md")):
        d = _read(skill, "skills", id_override="skills/%s" % skill.parent.name)
        d.ring = "skills"
        d.title = d.fm.get("name") or skill.parent.name
        out.append(d)

    for steer in sorted((root / "config").glob("**/*.md")):
        if steer.name == "SKILL.md":
            continue
        d = _read(steer, "config",
                  id_override="config/%s" % steer.stem)
        d.ring = "skills"
        out.append(d)

    return out


def load() -> List[Doc]:
    """Every content document in the vault, in a stable order."""
    docs = []
    for layer in config.LAYERS:
        d = config.VAULT / layer
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.md")):
            if f.name == "README.md":     # layer docs describe, they don't contain
                continue
            docs.append(_read(f, layer))

    # STATE.md and lessons.md are top-level but are real content
    for name, layer in (("STATE.md", "wiki"), ("lessons.md", "wiki")):
        f = config.VAULT / name
        if f.is_file():
            docs.append(_read(f, layer, id_override="core/" + f.stem))
    return docs


def _read(f, layer, id_override=None):
    raw = f.read_text(encoding="utf-8", errors="replace")
    fm, body = parse_frontmatter(raw)
    st = f.stat()
    try:
        rel = str(f.relative_to(config.VAULT.parent))
    except ValueError:
        rel = str(f)
    return Doc(
        id=id_override or "%s/%s" % (layer, f.stem),
        layer=layer,
        ring=RING.get(layer, "memory"),
        title=_title(body, f.stem, fm),
        path=rel,
        body=body.strip(),
        raw=raw,
        fm=fm,
        tags=_tags(fm),
        links=sorted(set(l.strip() for l in WIKILINK.findall(CODEFENCE.sub("", body)))),
        mtime=st.st_mtime,
        size=st.st_size,
        sha=hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12],
    )


def chunk(doc: Doc) -> List[Chunk]:
    """Split on headings first, then hard-wrap long sections.

    Heading-aware because a markdown note's structure is already a semantic
    outline — splitting on it beats a blind sliding window.
    """
    text = doc.body
    if not text.strip():
        return []

    parts = []
    marks = list(HEADING.finditer(text))
    if marks:
        if marks[0].start() > 0:
            parts.append(("", text[:marks[0].start()]))
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            parts.append((m.group(2).strip(), text[m.end():end]))
    else:
        parts.append(("", text))

    out = []
    for heading, seg in parts:
        seg = seg.strip()
        if not seg:
            continue
        for piece in _wrap(seg, config.CHUNK_CHARS, config.CHUNK_OVERLAP):
            out.append(Chunk(doc.id, len(out), heading or doc.title, piece))
    return out


def _wrap(s, size, overlap):
    if len(s) <= size:
        return [s]
    out, start = [], 0
    while start < len(s):
        end = min(start + size, len(s))
        if end < len(s):                      # prefer a paragraph or sentence break
            for sep in ("\n\n", "\n", ". "):
                cut = s.rfind(sep, start + size // 2, end)
                if cut != -1:
                    end = cut + len(sep)
                    break
        out.append(s[start:end].strip())
        if end >= len(s):
            break
        start = max(end - overlap, start + 1)
    return [c for c in out if c]


def graph(docs: List[Doc]):
    """Nodes and resolved wikilink edges, for the orbit map."""
    by_title = {}
    for d in docs:
        by_title.setdefault(d.title.lower(), d.id)
        by_title.setdefault(d.path.rsplit("/", 1)[-1][:-3].lower(), d.id)

    edges, missing = [], []
    for d in docs:
        for link in d.links:
            tgt = by_title.get(link.lower())
            if tgt and tgt != d.id:
                edges.append({"source": d.id, "target": tgt})
            elif not tgt:
                missing.append({"source": d.id, "label": link})
    return edges, missing


def stats(docs: List[Doc]):
    counts = {}
    for d in docs:
        counts[d.layer] = counts.get(d.layer, 0) + 1
    return {
        "docs": len(docs),
        "by_layer": counts,
        "words": sum(len(d.body.split()) for d in docs),
        "newest": max((d.mtime for d in docs), default=0),
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ"),
    }
