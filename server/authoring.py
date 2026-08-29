"""Author the vault — the only module under server/ permitted to write to disk.

`app.py` says the server is read-only over the vault by design, and until now that
was true: writing was `bin/os` and the automations. That design assumed the only
author was a person at a terminal. Once a model gets an editor, three things stop
being optional.

**A path jail.** `bin/os note "../../.ssh/authorized_keys"` writes exactly where
you would fear. That is defensible for a shell alias a human types, and
indefensible for a tool driven by text that arrived from the internet. Every path
here is derived from a sanitised slug, resolved, and then *proved* to sit inside
`config.VAULT` before anything is opened. Symlinks are resolved before the check,
so a symlinked layer directory cannot be used to climb out.

**Provenance.** Every mutation is its own git commit. Not because commits are
tidy, but because the vault is the memory of the system: an edit nobody can find,
attribute or revert is indistinguishable from corruption. `git log --follow` on a
note is the audit trail, and `git revert` is the undo.

**Append-only journal.** The journal is a record of what happened. A tool that can
rewrite history can rewrite the evidence of its own mistakes, so `journal/` accepts
appends and nothing else.

What is deliberately *not* here: any way to reach `AGENTS.md`, `config/`, `server/`
or `bin/`. The kernel and the skills define how the agent behaves; a agent that can
edit its own instructions has no stable behaviour to reason about. Those files are
readable — `vault.load_system()` still surfaces them — and unwritable.
"""
import os
import re
import shutil
import subprocess
import tempfile
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import config, vault

# ----------------------------------------------------------------- policy

#: Layers a tool may create notes in. `config.LAYERS` minus nothing today, but
#: kept separate so tightening this never means editing the vault's own model.
WRITABLE_LAYERS = tuple(config.LAYERS)

#: Appends only. See the module docstring.
APPEND_ONLY_LAYERS = ("journal",)

#: The two top-level vault files that are real content rather than a layer.
#: `vault.load()` gives them the id `core/<stem>`, so writes have to resolve that.
CORE_FILES = {"core/STATE": "STATE.md", "core/lessons": "lessons.md"}

#: A single note is prose, not a data dump. 512 KiB is ~80k words: far past any
#: legitimate note, and low enough that a runaway loop cannot fill the disk.
MAX_BYTES = 512 * 1024

#: Filenames are titles here — they show up in the UI and in wikilinks — so the
#: cap is about staying inside every filesystem's 255-byte component limit once
#: a date prefix and the .md suffix are added.
MAX_SLUG = 180

#: Rejected outright rather than sanitised. Silently rewriting a path the caller
#: asked for is how you get a tool that writes somewhere surprising.
_UNSAFE = re.compile(r"[\x00-\x1f\x7f/\\:*?\"<>|]")
_DOTS = re.compile(r"(?:^|[\\/])\.\.?(?:[\\/]|$)")


class WriteRefused(Exception):
    """A write was rejected by policy. The message is safe to show a model."""


# A single process serialises its own writes: read-modify-write plus `git add`
# plus `git commit` is not atomic, and two concurrent tool calls interleaving
# there would commit each other's half-finished trees.
_LOCK = threading.RLock()


# ------------------------------------------------------------------ paths

def slug(title: str) -> str:
    """A filename component from a human title, or raise.

    Whitespace and case are preserved: this vault's filenames *are* its titles
    (`brain/wiki/Context Rot.md`), and slugifying to `context-rot` would break
    every existing `[[wikilink]]`.
    """
    s = (title or "").strip()
    if not s:
        raise WriteRefused("A title is required.")
    if _DOTS.search(s) or s in (".", ".."):
        raise WriteRefused("Path traversal is not allowed in a title: %r" % title)
    if _UNSAFE.search(s):
        bad = sorted({c for c in s if _UNSAFE.match(c)})
        raise WriteRefused(
            "These characters cannot appear in a note title: %s" % " ".join(repr(c) for c in bad))
    s = s.lstrip(".").rstrip(" .")          # leading dot hides it; trailing dot breaks Windows
    if not s:
        raise WriteRefused("That title reduces to an empty filename.")
    if len(s.encode("utf-8")) > MAX_SLUG:
        raise WriteRefused("That title is too long (max %d bytes)." % MAX_SLUG)
    return s


def _jail(p: Path) -> Path:
    """Resolve `p` and prove it is inside the vault. The last line of defence."""
    root = config.VAULT.resolve()
    # strict=False: the file usually does not exist yet, but every existing
    # parent — and any symlink among them — is still resolved.
    full = Path(p).resolve()
    if full != root and root not in full.parents:
        raise WriteRefused("Refusing to write outside the vault: %s" % p)
    if full.suffix.lower() != ".md":
        raise WriteRefused("Only markdown notes can be written: %s" % full.name)
    return full


def check_layer(layer: str) -> str:
    if layer not in WRITABLE_LAYERS:
        raise WriteRefused("Unknown layer %r. Choose one of: %s"
                           % (layer, ", ".join(WRITABLE_LAYERS)))
    return layer


def path_for(layer: str, title: str, dated: Optional[bool] = None) -> Path:
    """Where a new note in `layer` titled `title` belongs.

    `raw` and `decisions` are date-prefixed, matching `bin/os capture` and
    `bin/os decide`, so a tool-authored note sorts and reads like a hand-authored
    one. Anything else would make the vault's own history look inconsistent.
    """
    check_layer(layer)
    name = slug(title)
    if dated is None:
        dated = layer in ("raw", "decisions")
    stem = "%s %s" % (date.today().isoformat(), name) if dated else name
    return _jail(config.VAULT / layer / ("%s.md" % stem))


def resolve_id(doc_id: str) -> Path:
    """Map a `Doc.id` back to a writable file, or refuse.

    This is where the read-only zones are enforced: `kernel/AGENTS`,
    `skills/<name>` and `config/<name>` are all legitimate document ids that
    `vault.load_all()` will happily hand a model, and none of them resolve here.
    """
    doc_id = (doc_id or "").strip()
    if not doc_id:
        raise WriteRefused("A note id is required.")
    if doc_id in CORE_FILES:
        return _jail(config.VAULT / CORE_FILES[doc_id])

    layer, _, stem = doc_id.partition("/")
    if not stem:
        raise WriteRefused("Malformed note id %r — expected '<layer>/<name>'." % doc_id)
    if layer in ("kernel", "skills", "config"):
        raise WriteRefused(
            "%r is part of the operating system, not the vault. The kernel, the "
            "skills and the steering files are readable but not writable." % doc_id)
    check_layer(layer)
    # `stem` is the filename, so it goes through the same sanitiser as a title.
    return _jail(config.VAULT / layer / ("%s.md" % slug(stem)))


def rel(p: Path) -> str:
    """Repo-relative path, for messages and git."""
    try:
        return str(Path(p).resolve().relative_to(config.ROOT.resolve()))
    except ValueError:
        return str(p)


def doc_id_for(p: Path) -> str:
    full = Path(p).resolve()
    root = config.VAULT.resolve()
    try:
        r = full.relative_to(root)
    except ValueError:
        return ""
    if len(r.parts) == 1:
        return "core/%s" % full.stem
    return "%s/%s" % (r.parts[0], full.stem)


# -------------------------------------------------------------- templates

_TODAY = lambda: date.today().isoformat()          # noqa: E731

def _template(layer: str, title: str, source: str = "") -> str:
    """The frontmatter and skeleton `bin/os` would have produced.

    Copied shape-for-shape on purpose: two authoring paths that disagree about
    frontmatter keys would quietly split the vault into two dialects, and the
    indexer reads those keys.
    """
    today = _TODAY()
    if layer == "wiki":
        return ("---\ncreated: %s\ntags: []\n---\n\n# %s\n\n\n\nRelated: \n"
                % (today, title))
    if layer == "raw":
        return ("---\ncaptured: %s\nsource: %s\nkind: scratch\n---\n\n# %s\n\n\n"
                % (today, source, title))
    if layer == "output":
        return ("---\ncreated: %s\nstatus: draft\nchannel: \nshipped: \nurl: \n"
                "---\n\n# %s\n\n\n\n---\nDrew on: \n" % (today, title))
    if layer == "decisions":
        return ("---\ndate: %s\nstatus: accepted\n---\n\n# %s\n\n## Context\n\n"
                "## Decision\n\n## Tradeoff\nWhat this costs us:\n\n"
                "## Alternatives rejected\n" % (today, title))
    if layer == "loops":
        return ("---\nloop: %s\nstatus: open\ncheck: \ncreated: %s\n---\n\n"
                "# Goal\n\n\n# Done when\n\n\n# Steps\n- [ ] \n\n# Notes\n"
                % (title, today))
    if layer == "journal":
        return "---\ndate: %s\n---\n\n# %s\n\n" % (today, title)
    return "---\ncreated: %s\n---\n\n# %s\n\n" % (today, title)


# ------------------------------------------------------------------ write

def _atomic_write(p: Path, text: str) -> None:
    """Replace `p`'s contents without ever leaving a half-written note on disk.

    A torn write here is worse than a failed one: the indexer would happily embed
    the truncated version, and the vault is the only copy.
    """
    data = text.encode("utf-8")
    if len(data) > MAX_BYTES:
        raise WriteRefused("That note is %d bytes; the limit is %d."
                           % (len(data), MAX_BYTES))
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".%s." % p.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)                  # atomic within a filesystem
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def create(layer: str, title: str, body: str = "", *, source: str = "",
           tags: Optional[List[str]] = None, overwrite: bool = False,
           commit: bool = True) -> Dict:
    """Create a note from the layer's template, with `body` filled in."""
    with _LOCK:
        p = path_for(layer, title)
        if p.exists() and not overwrite:
            raise WriteRefused(
                "%s already exists. Edit it rather than creating a duplicate — a "
                "second note on the same subject splits the memory." % rel(p))

        text = _template(layer, title, source)
        if body:
            # Slot the prose in under the H1 rather than appending after the
            # template's trailing scaffolding.
            marker = "# %s\n" % title
            if marker in text:
                head, _, tail = text.partition(marker)
                text = "%s%s\n%s\n%s" % (head, marker, body.strip(), tail.lstrip("\n"))
            else:
                text = "%s\n%s\n" % (text.rstrip("\n"), body.strip())
        if tags:
            text = _set_tags(text, tags)

        _atomic_write(p, text)
        out = _result("create", p, commit=commit,
                      message="brain: add %s" % rel(p))
        return out


def write(doc_id: str, content: str, *, mode: str = "replace",
          commit: bool = True) -> Dict:
    """Replace or append to an existing note.

    `mode="append"` is the only mode allowed for the journal.
    """
    if mode not in ("replace", "append"):
        raise WriteRefused("mode must be 'replace' or 'append', not %r." % mode)
    with _LOCK:
        p = resolve_id(doc_id)
        layer = doc_id.partition("/")[0]
        if layer in APPEND_ONLY_LAYERS and mode != "append":
            raise WriteRefused(
                "The journal is append-only: it records what happened, so it "
                "cannot be rewritten. Use mode='append'.")
        if not p.exists() and mode == "append":
            raise WriteRefused("%s does not exist yet." % doc_id)
        if not p.exists():
            raise WriteRefused("%s does not exist. Use create() to make it." % doc_id)

        if mode == "append":
            old = p.read_text(encoding="utf-8", errors="replace")
            sep = "" if old.endswith("\n") else "\n"
            text = "%s%s%s\n" % (old, sep, content.rstrip("\n"))
        else:
            text = content if content.endswith("\n") else content + "\n"

        _atomic_write(p, text)
        return _result(mode, p, commit=commit,
                       message="brain: %s %s" % (
                           "append to" if mode == "append" else "update", rel(p)))


def edit(doc_id: str, find: str, replace: str, *, count: int = 1,
         commit: bool = True) -> Dict:
    """Literal find-and-replace inside one note.

    Literal rather than regex, and it *fails* when `find` is absent or ambiguous.
    A model that silently no-ops on a failed edit will report success and move on,
    and the note it believed it changed is the one you will trust later.
    """
    if not find:
        raise WriteRefused("`find` cannot be empty.")
    with _LOCK:
        p = resolve_id(doc_id)
        layer = doc_id.partition("/")[0]
        if layer in APPEND_ONLY_LAYERS:
            raise WriteRefused("The journal is append-only and cannot be edited.")
        if not p.exists():
            raise WriteRefused("%s does not exist." % doc_id)

        old = p.read_text(encoding="utf-8", errors="replace")
        hits = old.count(find)
        if hits == 0:
            raise WriteRefused(
                "That exact text does not appear in %s. Read the note first — "
                "whitespace and indentation have to match." % doc_id)
        if count and hits > count:
            raise WriteRefused(
                "That text appears %d times in %s but count=%d. Include more "
                "surrounding context to make it unique, or raise count."
                % (hits, doc_id, count))

        text = old.replace(find, replace, count if count else -1)
        _atomic_write(p, text)
        out = _result("edit", p, commit=commit,
                      message="brain: edit %s" % rel(p))
        out["replacements"] = hits if not count else min(hits, count)
        return out


def delete(doc_id: str, *, commit: bool = True) -> Dict:
    """Remove a note. Recoverable from git, which is the point of committing."""
    with _LOCK:
        p = resolve_id(doc_id)
        layer = doc_id.partition("/")[0]
        if layer in APPEND_ONLY_LAYERS:
            raise WriteRefused("The journal cannot be deleted.")
        if doc_id in CORE_FILES:
            raise WriteRefused(
                "%s is core working memory, not a disposable note. Edit it "
                "instead." % doc_id)
        if not p.exists():
            raise WriteRefused("%s does not exist." % doc_id)
        p.unlink()
        return _result("delete", p, commit=commit,
                       message="brain: remove %s" % rel(p))


def append_journal(text: str, *, commit: bool = True) -> Dict:
    """Add a timestamped line to today's journal, creating it if needed.

    Mirrors `bin/os log` exactly, including the `- HH:MMZ — ...` shape, so the
    day's entries read as one list regardless of who wrote them.
    """
    with _LOCK:
        today = _TODAY()
        p = _jail(config.VAULT / "journal" / ("%s.md" % today))
        line = "- %s — %s" % (datetime.now(timezone.utc).strftime("%H:%MZ"),
                              " ".join((text or "").split()))
        if not p.exists():
            _atomic_write(p, "%s%s\n" % (_template("journal", today), line))
        else:
            old = p.read_text(encoding="utf-8", errors="replace")
            sep = "" if old.endswith("\n") else "\n"
            _atomic_write(p, "%s%s%s\n" % (old, sep, line))
        return _result("append", p, commit=commit,
                       message="brain: log %s" % today)


def _set_tags(text: str, tags: List[str]) -> str:
    clean = [re.sub(r"[^\w/-]", "", t).strip() for t in tags]
    clean = [t for t in clean if t]
    if not clean:
        return text
    line = "tags: [%s]" % ", ".join(clean)
    if re.search(r"^tags:.*$", text, re.M):
        return re.sub(r"^tags:.*$", line, text, count=1, flags=re.M)
    # Insert into existing frontmatter, or leave the note alone if it has none.
    m = vault.FRONTMATTER.match(text)
    if not m:
        return text
    return "%s%s\n%s" % (text[:m.end(1)], "\n" + line, text[m.end(1):])


# -------------------------------------------------------------------- git

def _git(*args: str, check: bool = False) -> Tuple[int, str]:
    """Run git in the repo root. Never raises on a non-zero exit unless asked."""
    if not shutil.which("git"):
        return 127, "git is not installed"
    try:
        r = subprocess.run(("git", "-C", str(config.ROOT)) + args,
                           capture_output=True, text=True, timeout=30)
    except (subprocess.SubprocessError, OSError) as e:
        return 1, str(e)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if check and r.returncode != 0:
        raise WriteRefused("git %s failed: %s" % (args[0], out))
    return r.returncode, out


def commit_paths(paths: List[Path], message: str) -> Dict:
    """Commit exactly these paths. No `-A`, ever.

    A write tool that runs `git add -A` commits whatever else happened to be dirty
    in the working tree — including a half-finished edit a human was in the middle
    of. Staging by explicit path keeps one tool call to one commit.
    """
    if not paths:
        return {"committed": False, "reason": "nothing to commit"}
    rc, _ = _git("rev-parse", "--git-dir")
    if rc != 0:
        return {"committed": False, "reason": "not a git repository"}

    args = ["add", "--"] + [str(p) for p in paths]
    rc, out = _git(*args)
    if rc != 0:
        return {"committed": False, "reason": "git add failed: %s" % out}

    rc, _ = _git("diff", "--cached", "--quiet")
    if rc == 0:
        return {"committed": False, "reason": "no change against HEAD"}

    rc, out = _git("commit", "-q", "-m", message)
    if rc != 0:
        return {"committed": False, "reason": "git commit failed: %s" % out}

    _, sha = _git("rev-parse", "--short", "HEAD")
    return {"committed": True, "sha": sha.strip(), "message": message}


def log_for(doc_id: str, limit: int = 10) -> List[Dict]:
    """Recent commits touching one note — the provenance of what it now says."""
    p = resolve_id(doc_id)
    rc, out = _git("log", "--follow", "-n", str(max(1, min(limit, 50))),
                   "--format=%h\x1f%an\x1f%ad\x1f%s", "--date=short", "--", str(p))
    if rc != 0 or not out:
        return []
    rows = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 4:
            rows.append({"sha": parts[0], "author": parts[1],
                         "date": parts[2], "subject": parts[3]})
    return rows


def _result(action: str, p: Path, *, commit: bool, message: str) -> Dict:
    out = {
        "action": action,
        "id": doc_id_for(p),
        "path": rel(p),
        "bytes": p.stat().st_size if p.exists() else 0,
    }
    out["git"] = commit_paths([p], message) if commit else {"committed": False,
                                                            "reason": "not requested"}
    return out


def reindex() -> Dict:
    """Make a write searchable. Best-effort: a failed reindex must not lose it.

    Imported lazily because `index` pulls in the embedding stack, and the write
    path has to work on a box too small to hold it.
    """
    try:
        from . import index
        return index.build(full=False)
    except Exception as e:                   # noqa: BLE001 - reported, not raised
        return {"error": "%s: %s" % (type(e).__name__, e)}


# ------------------------------------------------------------- selfcheck

def _selfcheck() -> int:
    """`python -m server.authoring` — exercises the jail against a temp vault."""
    import tempfile as _tf

    fails = []

    def ok(cond, msg):
        print(("  ok   " if cond else "  FAIL ") + msg)
        if not cond:
            fails.append(msg)

    def refuses(fn, label):
        try:
            fn()
        except WriteRefused as e:
            print("  ok   refused %s (%s)" % (label, str(e)[:58]))
            return
        except Exception as e:               # noqa: BLE001
            fails.append("%s raised %s instead of WriteRefused" % (label, type(e).__name__))
            print("  FAIL %s raised %s" % (label, type(e).__name__))
            return
        fails.append("%s was ALLOWED" % label)
        print("  FAIL %s was ALLOWED" % label)

    tmp = Path(_tf.mkdtemp(prefix="agentos-authoring-"))
    real_vault, real_root = config.VAULT, config.ROOT
    try:
        config.VAULT = tmp / "brain"
        config.ROOT = tmp
        for layer in config.LAYERS:
            (config.VAULT / layer).mkdir(parents=True, exist_ok=True)
        outside = tmp / "outside"
        outside.mkdir()
        (outside / "secret.md").write_text("do not touch\n", encoding="utf-8")

        print("\n== the jail ==")
        refuses(lambda: path_for("wiki", "../../../etc/passwd"), "../ in a title")
        refuses(lambda: path_for("wiki", "..%s.." % os.sep), "bare dots")
        refuses(lambda: path_for("wiki", "a/b"), "a slash in a title")
        refuses(lambda: path_for("wiki", "nul\x00byte"), "a NUL byte")
        refuses(lambda: path_for("nonsense", "X"), "an unknown layer")
        refuses(lambda: path_for("wiki", ""), "an empty title")
        refuses(lambda: path_for("wiki", "x" * 400), "an over-long title")
        refuses(lambda: resolve_id("kernel/AGENTS"), "writing the kernel")
        refuses(lambda: resolve_id("skills/taste"), "writing a skill")
        refuses(lambda: resolve_id("config/kernel-global"), "writing steering")
        refuses(lambda: resolve_id("wiki"), "an id with no name")

        # A symlink *inside* the vault pointing out of it is the real escape
        # attempt: the id looks entirely ordinary, and only resolving the link
        # before the containment check catches it.
        try:
            os.symlink(outside / "secret.md", config.VAULT / "wiki" / "pwned.md")
            refuses(lambda: write("wiki/pwned", "owned", commit=False),
                    "writing through a symlink out of the vault")
            refuses(lambda: delete("wiki/pwned", commit=False),
                    "deleting through a symlink out of the vault")
        except (OSError, NotImplementedError):
            print("  --   symlink check skipped (not permitted here)")

        print("\n== create / read back ==")
        r = create("wiki", "Hybrid Retrieval", body="BM25 and vectors, fused.",
                   tags=["retrieval", "search"], commit=False)
        ok(r["id"] == "wiki/Hybrid Retrieval", "id is %r" % r["id"])
        p = config.VAULT / "wiki" / "Hybrid Retrieval.md"
        ok(p.exists(), "file written to %s" % rel(p))
        text = p.read_text(encoding="utf-8")
        ok("# Hybrid Retrieval" in text, "H1 matches the title")
        ok("BM25 and vectors" in text, "body landed inside the note")
        ok("tags: [retrieval, search]" in text, "tags written into frontmatter")
        fm, _ = vault.parse_frontmatter(text)
        ok("created" in fm, "frontmatter parses back (keys: %s)" % ",".join(fm))
        refuses(lambda: create("wiki", "Hybrid Retrieval", commit=False),
                "creating a duplicate")

        print("\n== edit ==")
        r = edit("wiki/Hybrid Retrieval", "BM25 and vectors, fused.",
                 "BM25 and vectors, fused with RRF.", commit=False)
        ok("RRF" in p.read_text(encoding="utf-8"), "edit applied")
        refuses(lambda: edit("wiki/Hybrid Retrieval", "not present", "x", commit=False),
                "an edit whose anchor is absent")
        create("wiki", "Repeats", body="same\nsame\nsame", commit=False)
        refuses(lambda: edit("wiki/Repeats", "same", "other", count=1, commit=False),
                "an ambiguous edit")
        ok(edit("wiki/Repeats", "same", "other", count=3,
                commit=False)["replacements"] == 3, "count=3 replaces all three")

        print("\n== the journal is append-only ==")
        append_journal("first thing", commit=False)
        append_journal("second thing", commit=False)
        jp = config.VAULT / "journal" / ("%s.md" % _TODAY())
        jt = jp.read_text(encoding="utf-8")
        ok(jt.count("\n- ") >= 2, "two entries appended to one file")
        ok("first thing" in jt and "second thing" in jt, "both entries present")
        jid = "journal/%s" % _TODAY()
        refuses(lambda: write(jid, "wiped", mode="replace", commit=False),
                "replacing the journal")
        refuses(lambda: edit(jid, "first thing", "never happened", commit=False),
                "editing the journal")
        refuses(lambda: delete(jid, commit=False), "deleting the journal")
        ok(write(jid, "- appended directly", mode="append",
                 commit=False)["action"] == "append", "appending is allowed")

        print("\n== core files ==")
        (config.VAULT / "STATE.md").write_text("---\n---\n\n# State\n", encoding="utf-8")
        ok(resolve_id("core/STATE").name == "STATE.md", "core/STATE resolves")
        refuses(lambda: delete("core/STATE", commit=False), "deleting core memory")

        print("\n== size cap ==")
        refuses(lambda: create("wiki", "Huge", body="x" * (MAX_BYTES + 10), commit=False),
                "a note over the size cap")

        print("\n== nothing escaped ==")
        ok((outside / "secret.md").read_text(encoding="utf-8") == "do not touch\n",
           "the file outside the vault is untouched")
        # Everything under brain/ is fair game; the only file that should exist
        # outside it is the bait planted above.
        stray = [q for q in tmp.rglob("*.md")
                 if config.VAULT.resolve() not in q.resolve().parents
                 and q.resolve() != (outside / "secret.md").resolve()]
        ok(not stray, "nothing written outside brain/ (%s)"
           % (", ".join(str(q) for q in stray) or "clean"))

        print("\n== delete ==")
        r = delete("wiki/Repeats", commit=False)
        ok(not (config.VAULT / "wiki" / "Repeats.md").exists(), "note removed")
        refuses(lambda: delete("wiki/Repeats", commit=False), "deleting it twice")
    finally:
        config.VAULT, config.ROOT = real_vault, real_root
        shutil.rmtree(tmp, ignore_errors=True)

    print("\nauthoring selfcheck %s" % ("OK" if not fails else "FAILED (%d)" % len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
