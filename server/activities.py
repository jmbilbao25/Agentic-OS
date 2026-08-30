"""Activities — automation recipes an agent writes and a button runs.

A skill tells an agent *how* to do something. An activity is the thing itself:
a named, ordered list of steps this server can execute without an agent present,
from the Activities panel or from `bin/os activity <name>`.

    config/activities/fetch-ai-news.md
    ---
    name: fetch-ai-news
    description: Capture today's AI signal into raw, then write a digest.
    ---

    # Fetch AI news

    ## Steps

    - radar
    - distill

That is the whole format. One file, frontmatter, a `## Steps` list.

WHY STEPS ARE A WHITELIST AND NOT SHELL
---------------------------------------
The obvious design is `- shell: bin/os brief`. It is also the one design that
cannot be allowed here, and the reason is specific rather than paranoid:

`brain/raw/` is text fetched from the internet — arXiv abstracts, HN titles,
whole pages. `server/mcp.py` already wraps it in an UNTRUSTED DATA envelope
because an agent that reads a poisoned capture is the threat model, not an
abstraction. Activities are authored *by that same agent*, and then executed by a
human clicking a button. A `shell:` verb would turn "summarise this captured
page" into a path to arbitrary code execution, with the user supplying the click.

So a step names a capability the server already has. An activity composes
existing automations; it cannot invent new ones. Adding a verb is a deliberate
edit to `STEPS` below, reviewed like any other code — which is exactly the
property that makes handing activity authorship to a small model safe.

WHY THE STEP LIST IS PROSE AND NOT YAML
--------------------------------------
`steps: [radar, distill]` parses fine until a step takes an argument containing a
comma — `research: hybrid retrieval, bm25` — and then it silently becomes two
broken steps. A markdown list gives every step its own line, which removes the
class of bug entirely and happens to be what a model writes unprompted.
"""
import asyncio
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional

from . import config, vault
from .authoring import WriteRefused

#: Where activities live. Sibling of `config/skills/`, and writable for the same
#: reason: an activity is additive capability, not the behavioural contract.
ACTIVITIES_DIR = "config/activities"

#: Same kebab-case rule as skills, so one naming convention covers both and
#: `bin/os selftest` can check them the same way.
_NAME = re.compile(r"\A[a-z0-9]+(?:-[a-z0-9]+)*\Z")

#: A list item in the `## Steps` section: `- radar`, `* radar`, `1. radar`.
_ITEM = re.compile(r"\A\s*(?:[-*+]|\d+[.)])\s+(.*)\Z")

_HEADING = re.compile(r"\A\s{0,3}#{1,6}\s")

#: A long activity is a script wearing a recipe's clothes. Twelve steps is far
#: past anything legitimate and bounds how long one button press can run.
MAX_STEPS = 12

MIN_DESCRIPTION = 20


@dataclass
class Verb:
    """One capability an activity may name."""
    arg: str                     # "" when the verb takes none
    summary: str
    detail: str
    timeout: int = 300
    writes: str = ""             # where its output lands, for the UI


#: The vocabulary. Everything an activity can do, and nothing else.
#:
#: Each entry is deliberately something the OS already does from another entry
#: point, so an activity run and a scheduled run and a CLI run are the same code
#: — the rule recorded above `AUTOMATIONS` in server/app.py.
STEPS: Dict[str, Verb] = {
    "radar": Verb(
        arg="", summary="Capture today's AI signal from six keyless feeds",
        detail="Runs automations.radar. Writes one dated capture.",
        timeout=240, writes="brain/raw/"),
    "research": Verb(
        arg="topic", summary="Deep-dive one topic and capture the sources",
        detail="Runs automations.research <topic>. Needs a topic argument.",
        timeout=420, writes="brain/raw/"),
    "distill": Verb(
        arg="", summary="Triage the newest capture into a digest",
        detail="Runs automations.distill. Needs an inference key.",
        timeout=600, writes="brain/output/"),
    "doctor": Verb(
        arg="", summary="Read every capture, distil it, and wikilink it into the vault",
        detail="Runs server.doctor. Promotes raw into wiki notes that link to "
               "existing knowledge. Needs an inference key.",
        timeout=900, writes="brain/wiki/"),
    "reindex": Verb(
        arg="", summary="Rebuild the search index",
        detail="Incremental. Runs automatically after any step that writes, so "
               "you rarely need it explicitly.",
        timeout=300, writes=""),
    "log": Verb(
        arg="text", summary="Append one line to today's journal",
        detail="Runs the same append-only path as `bin/os log`.",
        timeout=30, writes="brain/journal/"),
}

#: Steps after which the index is stale and a search would miss what just landed.
_REINDEX_AFTER = {"radar", "research", "distill", "doctor"}

#: How often to send a keepalive while a step is still working.
#:
#: Not decoration. A step here is genuinely slow — embedding 35 changed documents
#: on a t3.micro's CPU measured 15 minutes — and a stream that says nothing for
#: that long is dropped by something in the path (a mobile carrier's NAT, a proxy's
#: idle timeout, the browser), which surfaces to the user as "network error" on a
#: run that in fact succeeded. Every long await is now interleaved with a ping
#: carrying elapsed seconds, so the connection stays warm *and* the panel can say
#: how long it has been going instead of looking hung.
HEARTBEAT_SECONDS = 10.0

#: Sentinel event: carries a finished step's result back out of the ping loop.
#: An async generator cannot both yield progress and return a value, so the result
#: travels as one more event and `run()` unwraps it rather than re-yielding it.
_RESULT = "_result"


@dataclass
class Step:
    verb: str
    arg: str = ""

    def render(self) -> str:
        return "%s: %s" % (self.verb, self.arg) if self.arg else self.verb


@dataclass
class Activity:
    name: str
    description: str
    steps: List[Step] = field(default_factory=list)
    body: str = ""
    path: str = ""
    mtime: float = 0.0

    def public(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "steps": [{"verb": s.verb, "arg": s.arg, "render": s.render(),
                       "summary": STEPS[s.verb].summary,
                       "writes": STEPS[s.verb].writes} for s in self.steps],
            "path": self.path,
            "mtime": self.mtime,
            "id": "activities/%s" % self.name,
            "writes": sorted({STEPS[s.verb].writes for s in self.steps if STEPS[s.verb].writes}),
        }


# ------------------------------------------------------------------- paths

def root() -> Path:
    return (config.ROOT / ACTIVITIES_DIR).resolve()


def check_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise WriteRefused("An activity name is required.")
    if not _NAME.match(name):
        raise WriteRefused(
            "Activity names are kebab-case — lowercase letters, digits and single "
            "hyphens, for example 'fetch-ai-news'. Got %r." % name)
    if len(name) > 60:
        raise WriteRefused("That activity name is too long (max 60 characters).")
    return name


def vocabulary() -> str:
    """The step list, formatted for a refusal message or a tool description.

    Every validation failure ends with this. A model that gets told "unknown step"
    guesses again; a model that gets told "unknown step, here are the six that
    exist" fixes it on the next call, which is the difference between an activity
    a small model can author and one it cannot.
    """
    lines = []
    for verb, v in STEPS.items():
        head = "%s: <%s>" % (verb, v.arg) if v.arg else verb
        lines.append("  - %-24s %s" % (head, v.summary))
    return "\n".join(lines)


# ------------------------------------------------------------------- parse

def parse_steps(body: str) -> List[Step]:
    """Pull the `## Steps` list out of an activity body.

    Anything outside that section is prose for a human and is ignored, which is
    what lets an activity carry an explanation without the explanation being
    mistaken for instructions.
    """
    lines = body.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(r"\A\s{0,3}#{1,6}\s+steps\s*\Z", line, re.I):
            start = i + 1
            break
    if start is None:
        raise WriteRefused(
            "This activity has no `## Steps` section, so there is nothing to run. "
            "Add one, with a markdown list of steps:\n\n## Steps\n\n- radar\n"
            "- distill\n\nAvailable steps:\n%s" % vocabulary())

    raw: List[str] = []
    for line in lines[start:]:
        if _HEADING.match(line):
            break
        m = _ITEM.match(line)
        if m:
            raw.append(m.group(1).strip())

    if not raw:
        raise WriteRefused(
            "The `## Steps` section is empty. List at least one step.\n\n"
            "Available steps:\n%s" % vocabulary())
    if len(raw) > MAX_STEPS:
        raise WriteRefused(
            "That is %d steps; the ceiling is %d. An activity composes a handful of "
            "capabilities — if it needs more, it is a script and belongs in "
            "automations/." % (len(raw), MAX_STEPS))

    steps: List[Step] = []
    for item in raw:
        # Strip inline code ticks a model may add: `- \`radar\`` is a step too.
        item = item.strip().strip("`").strip()
        verb, _, arg = item.partition(":")
        verb = verb.strip().lower()
        arg = arg.strip().strip("`\"'").strip()

        if verb not in STEPS:
            raise WriteRefused(
                "Unknown step %r. An activity may only name a capability this "
                "server already has — there is deliberately no way to run an "
                "arbitrary command.\n\nAvailable steps:\n%s" % (verb, vocabulary()))
        spec = STEPS[verb]
        if spec.arg and not arg:
            raise WriteRefused(
                "The step %r needs an argument. Write it as `%s: <%s>` — for "
                "example `%s`." % (verb, verb, spec.arg,
                                   "research: retrieval-augmented generation"
                                   if verb == "research" else "log: ran the radar"))
        if not spec.arg and arg:
            raise WriteRefused(
                "The step %r takes no argument, but got %r. Write it as just `%s`."
                % (verb, arg, verb))
        if len(arg) > 400:
            raise WriteRefused("That argument to %r is too long (max 400 characters)." % verb)
        steps.append(Step(verb=verb, arg=arg))
    return steps


def parse(text: str, name_hint: str = "") -> Activity:
    fm, body = vault.parse_frontmatter(text)
    name = check_name(fm.get("name") or name_hint)
    description = " ".join((fm.get("description") or "").split())
    if len(description) < MIN_DESCRIPTION:
        raise WriteRefused(
            "An activity needs a description of at least %d characters — it is "
            "what the Activities panel shows and what tells you whether to press "
            "the button. Got %d." % (MIN_DESCRIPTION, len(description)))
    return Activity(name=name, description=description,
                    steps=parse_steps(body), body=body.strip())


def load_all() -> List[Activity]:
    """Every valid activity. Invalid ones are skipped, not fatal.

    One malformed file must not empty the whole panel: the file that fails is the
    one to fix, and you cannot fix it from a panel that will not render.
    """
    out: List[Activity] = []
    d = root()
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.md")):
        if f.name == "README.md":
            continue
        try:
            a = parse(f.read_text(encoding="utf-8", errors="replace"), f.stem)
        except (WriteRefused, OSError):
            continue
        a.path = "%s/%s" % (ACTIVITIES_DIR, f.name)
        a.mtime = f.stat().st_mtime
        out.append(a)
    return out


def problems() -> List[str]:
    """Activities that exist on disk but will not run — surfaced like config problems."""
    out = []
    d = root()
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.md")):
        if f.name == "README.md":
            continue
        try:
            parse(f.read_text(encoding="utf-8", errors="replace"), f.stem)
        except WriteRefused as e:
            out.append("%s/%s will not run: %s" % (ACTIVITIES_DIR, f.name,
                                                   str(e).splitlines()[0]))
        except OSError as e:
            out.append("%s/%s is unreadable: %s" % (ACTIVITIES_DIR, f.name, e))
    return out


def load(name: str) -> Activity:
    name = check_name(name)
    f = root() / ("%s.md" % name)
    if not f.is_file():
        known = ", ".join(a.name for a in load_all()) or "none yet"
        raise WriteRefused("No activity called %r. Known activities: %s." % (name, known))
    a = parse(f.read_text(encoding="utf-8", errors="replace"), name)
    a.path = "%s/%s" % (ACTIVITIES_DIR, f.name)
    a.mtime = f.stat().st_mtime
    return a


# --------------------------------------------------------------------- run

def _module_step(verb: str, arg: str) -> Optional[List[str]]:
    """The subprocess command for a step, or None if it runs in-process."""
    if verb == "radar":
        return [sys.executable, "-m", "automations.radar", "--json"]
    if verb == "research":
        return [sys.executable, "-m", "automations.research", arg]
    if verb == "distill":
        return [sys.executable, "-m", "automations.distill"]
    return None


async def _run_step(step: Step) -> Dict:
    """Execute one step. Returns {ok, output, error} — never raises for a step
    failure, because a failed step is a result the panel has to render."""
    spec = STEPS[step.verb]

    if step.verb == "reindex":
        from .index import build
        res = await asyncio.to_thread(build, False)
        return {"ok": True,
                "output": "indexed %s chunk(s) across %s document(s)"
                          % (res.get("chunks_total", "?"), res.get("docs", "?")),
                "detail": res}

    if step.verb == "log":
        from . import authoring
        res = await asyncio.to_thread(authoring.append_journal, step.arg)
        return {"ok": True, "output": "appended to %s" % res.get("path", "the journal"),
                "detail": res}

    cmd = _module_step(step.verb, step.arg)
    try:
        p = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True,
            timeout=spec.timeout, cwd=str(config.ROOT))
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": "",
                "error": "%s timed out after %ss" % (step.verb, spec.timeout)}
    ok = p.returncode == 0
    return {"ok": ok, "output": (p.stdout or "")[-4000:],
            "error": "" if ok else (p.stderr or p.stdout or "")[-2000:]}


async def _awaiting(coro, ping: Dict) -> AsyncGenerator[Dict, None]:
    """Await `coro`, emitting `ping` every HEARTBEAT_SECONDS until it finishes.

    Yields zero or more ping events, then exactly one `_RESULT` event. An
    unexpected exception becomes a failed-step result rather than escaping: a step
    that blows up should end the activity with a message, not by killing the stream
    the panel is reading, because a dead stream is indistinguishable from a dead
    network and sends the user looking in the wrong place.
    """
    task = asyncio.ensure_future(coro)
    t0 = time.monotonic()
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=HEARTBEAT_SECONDS)
            if done:
                break
            out = dict(ping)
            out["elapsed"] = round(time.monotonic() - t0, 1)
            yield out
    except asyncio.CancelledError:
        # The client closed the tab. Do not leave the work running unobserved.
        task.cancel()
        raise
    try:
        result = task.result()
    except Exception as e:                                  # noqa: BLE001
        result = {"ok": False, "output": "",
                  "error": "%s: %s" % (type(e).__name__, e)}
    yield {"type": _RESULT, "result": result,
           "elapsed": round(time.monotonic() - t0, 1)}


async def _doctor_events(n: int, of: int) -> AsyncGenerator[Dict, None]:
    """Forward the doctor's own narration, then one `_RESULT`.

    The doctor is the only step that reports on itself, because it is the only one
    where the interesting part is *what it decided* — which capture, which notes,
    which links it had to drop — rather than whether it exited zero. Its events are
    passed through with a `doctor_` prefix so the panel can style them apart from
    step machinery without having to know what they mean.
    """
    from . import doctor

    summary = {"ok": False, "summary": "", "error": "the doctor produced no result"}
    async for ev in doctor.run():
        if ev.get("type") == "done":
            summary = ev
            continue
        out = dict(ev)
        out["type"] = "doctor_%s" % ev.get("type", "notice")
        out["n"] = n
        out["of"] = of
        yield out
    yield {"type": _RESULT,
           "result": {"ok": bool(summary.get("ok")),
                      "output": summary.get("summary", ""),
                      "error": summary.get("error", ""),
                      "detail": summary}}


async def run(name: str) -> AsyncGenerator[Dict, None]:
    """Execute an activity, yielding one event per step.

    Stops at the first failing step. A recipe is ordered for a reason — distilling
    a capture that was never written produces a confident digest of yesterday's
    news, which is worse than a visible failure.
    """
    a = load(name)
    yield {"type": "start", "name": a.name, "description": a.description,
           "steps": [s.render() for s in a.steps], "of": len(a.steps)}

    wrote = False
    for i, step in enumerate(a.steps, 1):
        spec = STEPS[step.verb]
        yield {"type": "step", "n": i, "of": len(a.steps), "verb": step.verb,
               "arg": step.arg, "render": step.render(), "summary": spec.summary,
               "writes": spec.writes}

        res = {"ok": False, "error": "the step produced no result"}
        elapsed = 0.0
        started = time.monotonic()
        source = (_doctor_events(i, len(a.steps)) if step.verb == "doctor"
                  else _awaiting(_run_step(step),
                                 {"type": "ping", "n": i, "of": len(a.steps),
                                  "verb": step.verb, "render": step.render()}))
        async for ev in source:
            if ev["type"] == _RESULT:
                res = ev["result"]
                elapsed = ev.get("elapsed") or round(time.monotonic() - started, 1)
            else:
                yield ev

        yield {"type": "step_done", "n": i, "verb": step.verb, "ok": res.get("ok"),
               "output": res.get("output", ""), "error": res.get("error", ""),
               "elapsed": elapsed}
        if not res.get("ok"):
            yield {"type": "done", "ok": False, "ran": i, "of": len(a.steps),
                   "message": "%s failed at step %d (%s)." % (a.name, i, step.render())}
            return
        if step.verb in _REINDEX_AFTER:
            wrote = True

    # One reindex at the end rather than after every step: two writing steps in a
    # row would otherwise pay for indexing twice and the first index is thrown away.
    if wrote and not any(s.verb == "reindex" for s in a.steps):
        from .index import build
        # This is the slowest thing in the whole run — embedding is CPU-bound and
        # measured 15 minutes for 35 changed documents on the target box — so it
        # gets the same heartbeat as a step. Silence here was the original
        # "network error".
        summary = {}
        async for ev in _awaiting(asyncio.to_thread(build, False),
                                  {"type": "ping", "verb": "reindex",
                                   "render": "reindex"}):
            if ev["type"] == _RESULT:
                summary = ev["result"] if isinstance(ev["result"], dict) else {}
            else:
                yield ev
        yield {"type": "reindexed", "chunks": summary.get("chunks_total"),
               "docs": summary.get("docs"), "detail": summary}

    yield {"type": "done", "ok": True, "ran": len(a.steps), "of": len(a.steps),
           "message": "%s finished all %d step%s."
                      % (a.name, len(a.steps), "" if len(a.steps) == 1 else "s")}


# -------------------------------------------------------------- diagnostics

def _selfcheck() -> int:
    """`python -m server.activities` — parser cases, no fixtures, no network."""
    ok = True

    def case(label, fn, expect_ok=True):
        nonlocal ok
        try:
            fn()
            good = expect_ok
            why = "parsed"
        except WriteRefused as e:
            good = not expect_ok
            why = str(e).splitlines()[0]
        if not good:
            ok = False
        print("%s %-52s %s" % ("ok  " if good else "FAIL", label, why[:70]))

    good = "---\nname: t\ndescription: %s\n---\n\n## Steps\n\n- radar\n- distill\n" % ("x" * 30)
    case("a well-formed activity", lambda: parse(good))
    case("numbered list items", lambda: parse(good.replace("- radar", "1. radar")))
    case("backticked steps", lambda: parse(good.replace("- radar", "- `radar`")))
    case("a step with an argument",
         lambda: parse(good.replace("- radar", "- research: bm25, vectors")))
    case("no Steps section",
         lambda: parse(good.replace("## Steps", "## Notes")), expect_ok=False)
    case("an unknown step",
         lambda: parse(good.replace("- radar", "- rm -rf /")), expect_ok=False)
    case("shell is not a step",
         lambda: parse(good.replace("- radar", "- shell: bin/os brief")), expect_ok=False)
    case("research without a topic",
         lambda: parse(good.replace("- radar", "- research")), expect_ok=False)
    case("radar with a stray argument",
         lambda: parse(good.replace("- radar", "- radar: today")), expect_ok=False)
    case("a thin description",
         lambda: parse(good.replace("x" * 30, "too short")), expect_ok=False)
    case("a bad name",
         lambda: parse(good.replace("name: t", "name: Not Kebab")), expect_ok=False)
    case("more than MAX_STEPS",
         lambda: parse(good.replace("- radar", "\n".join(["- radar"] * 13))),
         expect_ok=False)

    # The heartbeat, which exists because its absence read to the user as
    # "network error" on a run that had actually succeeded. Driven with a short
    # interval rather than the real one so the check stays fast.
    async def _hb():
        global HEARTBEAT_SECONDS
        keep = HEARTBEAT_SECONDS
        HEARTBEAT_SECONDS = 0.05
        try:
            async def slow():
                await asyncio.sleep(0.35)
                return {"ok": True, "output": "done"}
            pings, result = 0, None
            async for ev in _awaiting(slow(), {"type": "ping", "verb": "test"}):
                if ev["type"] == _RESULT:
                    result = ev["result"]
                else:
                    pings += 1
                    assert ev["elapsed"] >= 0, ev

            async def boom():
                raise RuntimeError("kaboom")
            crashed = None
            async for ev in _awaiting(boom(), {"type": "ping", "verb": "test"}):
                if ev["type"] == _RESULT:
                    crashed = ev["result"]
            return pings, result, crashed
        finally:
            HEARTBEAT_SECONDS = keep

    pings, result, crashed = asyncio.run(_hb())
    ok_hb = pings >= 2 and (result or {}).get("ok") is True
    if not ok_hb:
        ok = False
    print("%s %-52s %d ping(s)"
          % ("ok  " if ok_hb else "FAIL", "a slow step emits keepalive pings", pings))
    ok_crash = (crashed or {}).get("ok") is False and "kaboom" in (crashed or {}).get("error", "")
    if not ok_crash:
        ok = False
    print("%s %-52s %s"
          % ("ok  " if ok_crash else "FAIL", "a step that raises becomes a failed result",
             (crashed or {}).get("error", "")[:40]))

    found = load_all()
    print("\n%d activity file(s) on disk:" % len(found))
    for a in found:
        print("  %-22s %s" % (a.name, " -> ".join(s.render() for s in a.steps)))
    for p in problems():
        ok = False
        print("FAIL %s" % p)

    print("\n%s" % ("all activity checks passed" if ok else "activity checks FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
