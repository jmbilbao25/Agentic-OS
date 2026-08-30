"""The visual second brain.

The HTTP API does not *author* markdown: no endpoint here composes a note from a
request body. What it renders, searches and reasons over is written elsewhere, so
that every change to memory goes through git and stays reviewable. See
brain/wiki/Git Is The Disk.md

Three things do write, all deliberate, and the distinction that matters is that
none of them takes note content from an HTTP caller:

  - settings.local.json is machine state rather than memory — it holds an API key
    and a model choice, neither of which belongs in a git history.
  - `/api/run/{name}` and `/api/activities/run` execute the same automation
    modules the systemd timers do. They write captures, digests and — via the
    `doctor` step — wiki notes. The request chooses *which routine runs*, never
    what it writes; the vocabulary of runnable steps is code, in
    server/activities.py, and there is no step that runs an arbitrary command.
  - /mcp, when `AGENTOS_MCP_TOKEN` is set, exposes the vault to an external agent
    *including* write tools. It is a separate surface with separate auth (bearer
    token, loopback-only by default), it is absent entirely when unconfigured, and
    every write it performs is its own git commit. See server/mcp.py for the
    threat model.
"""
import asyncio
import json
import logging
import secrets
import subprocess
import sys
from typing import AsyncGenerator

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse, StreamingResponse)
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import (activities, auth, config, embed, llm, mcp, runs, search, settings,
               vault)
from .authoring import WriteRefused

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("agentos")

# No schema endpoints: there is no third-party client to generate one for, and
# an unauthenticated /openapi.json would enumerate the whole API for free.
app = FastAPI(title="AgentOS Second Brain", docs_url=None, redoc_url=None,
              openapi_url=None)

app.add_middleware(
    SessionMiddleware,
    secret_key=config.SESSION_SECRET or secrets.token_urlsafe(32),
    session_cookie="agentos",
    max_age=config.SESSION_DAYS * 86400,
    same_site="lax",
    https_only=bool(config.BASE_URL.startswith("https")),
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])

# The MCP endpoint for the JM Agentic-OS Harness. Registers nothing at all unless
# AGENTOS_MCP_TOKEN is set, so the default deployment has no write surface.
MCP_MOUNTED = mcp.register(app)
log.info("MCP endpoint: %s", "/mcp (bearer auth)" if MCP_MOUNTED
         else "disabled (set AGENTOS_MCP_TOKEN to enable)")

if config.STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=str(config.STATIC)), name="static")


# Everything is same-origin and there is no third-party anything, so the policy
# can be tight. No 'unsafe-inline' for scripts or styles: the UI uses external
# files and the CSSOM, never a style attribute or an inline handler.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; "
       "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
       "form-action 'self'; base-uri 'none'; frame-ancestors 'none'; "
       "object-src 'none'")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    r = await call_next(request)
    r.headers.setdefault("Content-Security-Policy", CSP)
    r.headers.setdefault("X-Content-Type-Options", "nosniff")
    r.headers.setdefault("Referrer-Policy", "no-referrer")
    r.headers.setdefault("X-Frame-Options", "DENY")
    r.headers.setdefault("Permissions-Policy",
                         "geolocation=(), camera=(), microphone=()")
    if config.BASE_URL.startswith("https"):
        r.headers.setdefault("Strict-Transport-Security",
                             "max-age=31536000; includeSubDomains")
    return r


@app.on_event("startup")
async def startup():
    for p in config.problems() + mcp.problems():
        log.warning("config: %s", p)
    if not config.SESSION_SECRET:
        log.warning("SESSION_SECRET unset — using an ephemeral key; sessions drop "
                    "on restart")
    log.info("vault=%s db=%s", config.VAULT, config.DB)
    log.info("provider=%s model=%s", settings.get("LLM_BASE_URL"),
             settings.get("LLM_MODEL"))
    embed.warm()


def user(request: Request):
    return auth.require(request)


# ---------------------------------------------------------------- SSE plumbing

def _frame(event: str, data) -> str:
    return "event: %s\ndata: %s\n\n" % (event, json.dumps(data))


def _sse(gen: AsyncGenerator) -> StreamingResponse:
    return StreamingResponse(gen, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "Connection": "keep-alive",
                                      "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- public routes

@app.get("/healthz")
async def healthz():
    """Unauthenticated liveness. Deliberately leaks nothing about the vault."""
    return {"ok": True}


@app.get("/")
async def root(request: Request):
    if not auth.current_user(request):
        return RedirectResponse("/auth/login")
    idx = config.STATIC / "index.html"
    if not idx.is_file():
        return HTMLResponse("<h1>AgentOS</h1><p>static/index.html missing</p>",
                            status_code=500)
    return FileResponse(str(idx), headers={"Cache-Control": "no-store"})


# -------------------------------------------------------------------- status

@app.get("/api/status")
async def status(u=Depends(user)):
    return {
        "user": u,
        "index": search.index_status(),
        "vault": str(config.VAULT),
        "model": settings.get("LLM_MODEL"),
        "provider": settings.get("LLM_BASE_URL"),
        "is_openrouter": llm.is_openrouter(),
        "llm_configured": llm.configured(),
        "reindex_pending": settings.reindex_pending(),
        "repo_url": settings.get("REPO_URL"),
        "ui": {
            "reduced_motion": settings.get("UI_REDUCED_MOTION"),
            "orbit_spin": settings.get("UI_ORBIT_SPIN"),
            "label_density": settings.get("UI_LABEL_DENSITY"),
        },
        "problems": config.problems() + mcp.problems() + activities.problems(),
        "mcp": {"enabled": MCP_MOUNTED,
                "loopback_only": MCP_MOUNTED and not mcp.ALLOW_REMOTE,
                "tools": len(mcp.TOOLS) if MCP_MOUNTED else 0},
    }


# --------------------------------------------------------------------- vault

@app.get("/api/graph")
async def api_graph(u=Depends(user)):
    """The whole vault as nodes + edges. Small enough to send at once — a
    personal vault is thousands of files, not millions."""
    docs = vault.load_all()
    edges, missing = vault.graph(docs)

    backlinks = {}
    for e in edges:
        backlinks.setdefault(e["target"], []).append(e["source"])

    nodes = []
    for d in docs:
        nodes.append({
            "id": d.id, "title": d.title, "layer": d.layer, "ring": d.ring,
            "path": d.path, "tags": d.tags, "links": d.links,
            "size": d.size, "mtime": d.mtime,
            "words": len(d.body.split()),
            "backlinks": len(backlinks.get(d.id, [])),
            "excerpt": d.body[:220].replace("\n", " ").strip(),
        })
    return {"nodes": nodes, "edges": edges, "missing": missing,
            "stats": vault.stats(docs)}


@app.get("/api/doc")
async def api_doc(id: str, u=Depends(user)):
    """One document, plus what points at it.

    Reads load_all() so the kernel and the skills open like anything else — they
    are on the map, so they have to be openable from it.
    """
    docs = vault.load_all()
    doc = next((d for d in docs if d.id == id), None)
    if doc is None:
        raise HTTPException(404, "no document %r" % id)

    edges, _ = vault.graph(docs)
    by_id = {d.id: d for d in docs}

    def brief(doc_id):
        d = by_id.get(doc_id)
        return None if d is None else {"id": d.id, "title": d.title,
                                       "layer": d.layer, "ring": d.ring}

    payload = doc.public()
    payload["backlinks"] = [b for b in
                            (brief(e["source"]) for e in edges
                             if e["target"] == id) if b]
    payload["outgoing"] = [b for b in
                           (brief(e["target"]) for e in edges
                            if e["source"] == id) if b]
    payload["words"] = len(doc.body.split())

    repo = settings.get("REPO_URL")
    if repo:
        payload["repo_url"] = "%s/blob/main/%s" % (repo.rstrip("/"), doc.path)
    return payload


@app.get("/api/search")
async def api_search(q: str, k: int = 0, layers: str = "", u=Depends(user)):
    return search.search(q, top_k=k or None,
                         layers=[l for l in layers.split(",") if l] or None)


# ----------------------------------------------------------------------- ask

@app.post("/api/ask")
async def api_ask(request: Request, u=Depends(user)):
    body = await request.json()
    question = (body.get("q") or "").strip()
    if not question:
        raise HTTPException(400, "empty question")
    model = (body.get("model") or "").strip() or None

    found = search.search(question, top_k=body.get("k") or settings.get("TOP_K"))
    hits = found["hits"]
    messages = llm.build_prompt(question, hits)

    async def gen():
        # Citations first so the UI can render sources before the answer streams.
        yield _frame("sources", [
            {"n": i, "title": h["title"], "path": h["path"], "doc_id": h["doc_id"],
             "heading": h["heading"], "layer": h["layer"], "matched": h["matched"],
             "text": h["text"][:600]}
            for i, h in enumerate(hits, 1)])
        yield _frame("retrieval", {"mode": found.get("mode"),
                                   "counts": found.get("counts")})
        try:
            async for ev in llm.stream(messages, model=model):
                yield _frame(ev.get("type", "delta"), ev)
        except asyncio.CancelledError:      # client closed the tab mid-answer
            raise
        yield _frame("done", {})

    return _sse(gen())


# ---------------------------------------------------------------- activities

@app.get("/api/activities")
async def api_activities(u=Depends(user)):
    """Every activity, plus the step vocabulary the panel documents.

    `will_not_run` carries files that exist but do not parse. A malformed activity
    that silently vanished from the list was indistinguishable from one that was
    never written, which sent people looking in the wrong place.
    """
    found = activities.load_all()
    return {
        "activities": [a.public() for a in found],
        "steps": {verb: {"arg": v.arg, "summary": v.summary, "detail": v.detail,
                         "writes": v.writes}
                  for verb, v in activities.STEPS.items()},
        "will_not_run": activities.problems(),
        "llm_configured": llm.configured(),
    }


#: Live task handles. Held so the event loop cannot garbage-collect a run that
#: nobody is currently awaiting — which is the normal state here, by design.
_RUN_TASKS = set()


async def _drive(run: runs.Run) -> None:
    """Consume an activity's events into its run log. Never raises."""
    ok, message = False, ""
    try:
        async for ev in activities.run(run.name):
            runs.append(run, ev)
            if ev.get("type") == "done":
                ok = bool(ev.get("ok"))
                message = ev.get("message", "")
    except WriteRefused as e:
        # A refusal is the activity being unrunnable, not a server fault, and its
        # message names the fix — so it belongs in the log the panel renders.
        runs.append(run, {"type": "error", "message": str(e)})
        message = str(e)
    except asyncio.CancelledError:
        runs.append(run, {"type": "error", "message": "the run was cancelled"})
        runs.finish(run, False, "cancelled")
        raise
    except Exception as e:                                  # noqa: BLE001
        log.exception("activity %r failed", run.name)
        runs.append(run, {"type": "error",
                          "message": "%s: %s" % (type(e).__name__, e)})
        message = "%s: %s" % (type(e).__name__, e)
    finally:
        if run.running:
            runs.finish(run, ok, message)


@app.post("/api/activities/run")
async def api_activities_run(request: Request, u=Depends(user)):
    """Start an activity in the background and answer with its run id.

    Deliberately not a stream. The first version held one SSE response open for
    the whole run, which works until the run is long: the doctor takes ~80 seconds
    over three captures, a phone on cellular gave up at 50, and the user was shown
    "network error" for a run the server went on to complete successfully. The
    connection was the only thing that failed, and it was also the only thing
    reporting.

    So the run outlives its caller. Poll /api/activities/runs/{id} for the log —
    a dropped connection, a lock screen or a page reload all become survivable,
    and the feed rejoins from an offset instead of orphaning the work.
    """
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "no activity named")

    # Refuse a second copy rather than running two. These steps write to the vault
    # and commit; two radars racing would fight over the same dated capture.
    busy = runs.active(name)
    if busy is not None:
        return {"run_id": busy.id, "name": name, "running": True,
                "already_running": True}

    try:
        activities.load(name)          # fail here, with the reason, not in the log
    except WriteRefused as e:
        raise HTTPException(400, str(e))

    run = runs.start(name)
    task = asyncio.create_task(_drive(run))
    _RUN_TASKS.add(task)
    task.add_done_callback(_RUN_TASKS.discard)
    return {"run_id": run.id, "name": name, "running": True}


@app.get("/api/activities/runs")
async def api_activity_runs(u=Depends(user)):
    """Recent runs, newest first, plus whichever is live — so a reload can rejoin."""
    live = runs.active()
    return {"runs": runs.recent(), "active": live.id if live else None}


@app.get("/api/activities/runs/{run_id}")
async def api_activity_run(run_id: str, after: int = 0, u=Depends(user)):
    """The log from `after` onwards, with the cursor to ask from next."""
    run = runs.get(run_id)
    if run is None:
        # A run this server never had, or one already evicted. 404 rather than an
        # empty log, so the panel stops polling instead of spinning forever.
        raise HTTPException(404, "no run %r — it may have finished long ago" % run_id)
    return runs.slice_events(run, after)


# ------------------------------------------------------------------- settings

@app.get("/api/settings")
async def api_settings(u=Depends(user)):
    return settings.public()


@app.put("/api/settings")
async def api_settings_put(patch: dict = Body(...), u=Depends(user)):
    changed, errors = settings.update(patch)
    if errors:
        return JSONResponse({"errors": errors, "changed": []}, status_code=422)

    # An embedding change makes the loaded model wrong, not just the index.
    if any(k.startswith("EMBED_") for k in changed):
        embed.invalidate()

    return {"changed": changed,
            "restart_required": settings.restart_required(changed),
            "reindex_pending": settings.reindex_pending(),
            "settings": settings.public()}


@app.post("/api/settings/reset")
async def api_settings_reset(payload: dict = Body(default={}), u=Depends(user)):
    keys = payload.get("keys") or None
    cleared = settings.reset(keys)
    if any(k.startswith("EMBED_") for k in cleared):
        embed.invalidate()
    return {"cleared": cleared, "settings": settings.public()}


@app.get("/api/models")
async def api_models(refresh: bool = False, u=Depends(user)):
    res = await llm.list_models(force=refresh)
    res["current"] = settings.get("LLM_MODEL")
    res["fallbacks"] = settings.get("LLM_FALLBACK_MODELS")
    return res


# -------------------------------------------------------------- index / sync

@app.post("/api/reindex")
async def api_reindex(full: bool = False, u=Depends(user)):
    from .index import build
    return await asyncio.to_thread(build, full)


@app.post("/api/sync")
async def api_sync(u=Depends(user)):
    """git pull, then reindex. The button version of the cron job."""
    try:
        out = await asyncio.to_thread(
            subprocess.run, ["git", "pull", "--ff-only"],
            capture_output=True, text=True, timeout=60, cwd=str(config.ROOT))
        pull = (out.stdout + out.stderr).strip()
        ok = out.returncode == 0
    except Exception as e:                          # noqa: BLE001
        pull, ok = "git pull failed: %s" % e, False
    from .index import build
    return {"pull": pull, "pull_ok": ok,
            "index": await asyncio.to_thread(build, False)}


# ------------------------------------------------------------- automations

# The same modules the systemd timers run, so a button press and a scheduled run
# take identical code paths. A dashboard that reimplements its own routines
# drifts from them, and the drift is only discovered when one of them is wrong.
AUTOMATIONS = {
    "radar":    ([sys.executable, "-m", "automations.radar", "--json"], 180),
    "distill":  ([sys.executable, "-m", "automations.distill"], 420),
    "research": ([sys.executable, "-m", "automations.research"], 300),
}


@app.post("/api/run/{name}")
async def api_run(name: str, request: Request, u=Depends(user)):
    if name not in AUTOMATIONS:
        raise HTTPException(404, "unknown automation %r" % name)
    cmd, timeout = AUTOMATIONS[name]
    cmd = list(cmd)

    if name == "research":
        try:
            body = await request.json()
        except Exception:                            # noqa: BLE001
            body = {}
        topic = (body.get("topic") or "").strip()
        if not topic:
            raise HTTPException(400, "research needs a topic")
        cmd.append(topic)

    try:
        p = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True,
            timeout=timeout, cwd=str(config.ROOT))
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "%s timed out after %ss" % (name, timeout))

    ok = p.returncode == 0
    # Reindex on success so whatever was just captured is immediately findable.
    # Without it you run the radar, search for what it found, and get nothing.
    indexed = None
    if ok:
        from .index import build
        indexed = await asyncio.to_thread(build, False)

    return {"ok": ok, "name": name, "code": p.returncode,
            "stdout": (p.stdout or "")[-4000:], "stderr": (p.stderr or "")[-2000:],
            "index": indexed}


@app.exception_handler(HTTPException)
async def on_http_error(request: Request, exc: HTTPException):
    if exc.status_code == 401 and not request.url.path.startswith("/api/"):
        return RedirectResponse("/auth/login?next=%s" % request.url.path)
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
