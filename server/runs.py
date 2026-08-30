"""A registry of activity runs, so a run outlives the connection that started it.

The first version of the Activities panel streamed a run over one long-lived SSE
response. It worked on a laptop and failed on a phone: the doctor takes 80 seconds
against three captures, the browser gave up at 50, and the user saw "network
error" on a run that had in fact completed — the server finished it and wrote
everything. The connection was the only casualty, and it was also the only thing
reporting.

So the run and its transport are separated. `POST /api/activities/run` starts a
background task and answers immediately with a `run_id`; the events accumulate
here; the panel polls. Three properties fall out, and they are the reason this is
worth a module rather than a clever `retry`:

- **A dropped connection costs nothing.** The work continues. The feed reconnects
  and catches up from an offset, so a tunnel, a lock screen or a lift are all
  survivable.
- **A reload is survivable too.** State lives on the server, so the panel can find
  a run already in progress and rejoin it rather than orphaning it.
- **Two clients can watch the same run.** Not a goal, but it follows, and it is
  the honest test that the run is not owned by a socket.

What this is deliberately not: durable. The log is in memory and bounded, and a
restart of `agentos` loses it. Persisting it would mean choosing a schema and a
retention policy for something whose whole audience is a panel open right now —
and the *outputs* are already durable, because every step commits to git. The log
is a view of work, not a record of it.
"""
import time
import uuid
from typing import Any, Dict, List, Optional

#: Runs kept in memory. Small: the panel shows a handful and the rest are noise.
MAX_RUNS = 12

#: Events per run. The doctor emits a few per capture; a pathological activity
#: emitting thousands should lose its history rather than the box losing its RAM.
MAX_EVENTS = 2000


class Run:
    __slots__ = ("id", "name", "started", "finished", "ok", "events", "message")

    def __init__(self, name: str):
        self.id = uuid.uuid4().hex[:12]
        self.name = name
        self.started = time.time()
        self.finished: Optional[float] = None
        self.ok: Optional[bool] = None
        self.message = ""
        self.events: List[Dict[str, Any]] = []

    @property
    def running(self) -> bool:
        return self.finished is None

    def head(self) -> Dict:
        """Enough to list a run without shipping its whole log."""
        return {
            "run_id": self.id, "name": self.name, "started": self.started,
            "finished": self.finished, "running": self.running, "ok": self.ok,
            "message": self.message, "events": len(self.events),
            "elapsed": round((self.finished or time.time()) - self.started, 1),
        }


_RUNS: "Dict[str, Run]" = {}
_ORDER: List[str] = []


def start(name: str) -> Run:
    run = Run(name)
    _RUNS[run.id] = run
    _ORDER.append(run.id)
    # Evict finished runs first: dropping a live one would strand the panel
    # watching it, which is the one failure this module exists to prevent.
    while len(_ORDER) > MAX_RUNS:
        victim = next((r for r in _ORDER if not _RUNS[r].running), None)
        if victim is None:
            break
        _ORDER.remove(victim)
        _RUNS.pop(victim, None)
    return run


def append(run: Run, event: Dict) -> None:
    if len(run.events) >= MAX_EVENTS:
        # Keep the beginning and drop the middle: the start of a run explains what
        # it is, and the tail is what you are watching. The middle of a runaway
        # log is the least informative part of it.
        run.events = run.events[:200] + [{
            "type": "notice",
            "message": "log truncated — this run emitted more than %d events"
                       % MAX_EVENTS}] + run.events[-600:]
    ev = dict(event)
    ev.setdefault("at", round(time.time(), 3))
    run.events.append(ev)


def finish(run: Run, ok: bool, message: str = "") -> None:
    run.finished = time.time()
    run.ok = ok
    run.message = message or run.message


def get(run_id: str) -> Optional[Run]:
    return _RUNS.get(run_id)


def slice_events(run: Run, after: int = 0) -> Dict:
    """Everything since `after`, plus where to ask from next.

    The cursor is an index rather than a timestamp: indexes cannot collide, and a
    poll that arrives during the same millisecond as an append would otherwise
    either duplicate an event or skip one.
    """
    after = max(0, int(after or 0))
    tail = run.events[after:]
    out = run.head()
    out["events"] = tail
    out["next"] = after + len(tail)
    return out


def recent(limit: int = 6) -> List[Dict]:
    return [_RUNS[r].head() for r in reversed(_ORDER[-limit:])]


def active(name: Optional[str] = None) -> Optional[Run]:
    """A run still in progress, newest first. Used to rejoin after a reload."""
    for rid in reversed(_ORDER):
        run = _RUNS.get(rid)
        if run and run.running and (name is None or run.name == name):
            return run
    return None
