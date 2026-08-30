"""Run an activity from the command line.

    python -m automations.activity --list
    python -m automations.activity fetch-ai-news

The same `server.activities.run()` the Activities panel streams. One code path,
two entry points — the rule recorded above `AUTOMATIONS` in server/app.py: a
surface that reimplements a routine drifts from it, and the drift is only
discovered when one of them is wrong.

Lives in `automations/` rather than as `python -m server.activities` because that
spelling is already taken: every `server/` module answers `python -m` with its own
self-check, and `config/steering/30-lazy-senior.md` treats that as the convention.
"""
import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import activities                              # noqa: E402
from server.authoring import WriteRefused                  # noqa: E402


def show_list() -> int:
    found = activities.load_all()
    problems = activities.problems()
    if not found:
        print("No activities in config/activities/ yet.")
        print("\nSteps an activity can be made of:\n%s" % activities.vocabulary())
        return 0
    width = max(len(a.name) for a in found)
    for a in found:
        print("%-*s  %s" % (width, a.name, " -> ".join(s.render() for s in a.steps)))
        print("%-*s  %s" % (width, "", a.description))
    if problems:
        print("\nwill not run:")
        for p in problems:
            print("  %s" % p)
    return 0


async def run_one(name: str, quiet: bool = False) -> int:
    ok = True
    async for ev in activities.run(name):
        kind = ev.get("type")
        if kind == "start" and not quiet:
            print("%s — %d step(s): %s"
                  % (ev["name"], ev["of"], " -> ".join(ev["steps"])))
        elif kind == "step" and not quiet:
            print("[%d/%d] %s — %s" % (ev["n"], ev["of"], ev["render"], ev["summary"]))
        elif kind == "step_done":
            if ev.get("ok"):
                tail = (ev.get("output") or "").strip().splitlines()
                if tail and not quiet:
                    print("        %s" % tail[-1][:160])
            else:
                ok = False
                print("        failed: %s" % (ev.get("error") or "").strip()[:400],
                      file=sys.stderr)
        elif kind == "reindexed" and not quiet:
            print("        reindexed (%s chunks)" % ev.get("chunks"))
        elif kind == "done":
            ok = ok and bool(ev.get("ok"))
            print(ev.get("message", ""), file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m automations.activity")
    ap.add_argument("name", nargs="?", default="", help="activity to run")
    ap.add_argument("--list", action="store_true", help="list activities and exit")
    ap.add_argument("--quiet", action="store_true", help="only report the outcome")
    args = ap.parse_args()

    if args.list or not args.name:
        return show_list()

    try:
        return asyncio.run(run_one(args.name, quiet=args.quiet))
    except WriteRefused as e:
        # A refusal names the fix, so it is the whole error message.
        print("activity: %s" % e, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nactivity: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
