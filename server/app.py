"""The visual second brain.

Read-only over the vault by design: this app renders and searches markdown, it
never authors it. Writing is `bin/os`, so that every change to memory goes through
git and stays reviewable. See brain/wiki/Git Is The Disk.md
"""
import logging
import secrets
import subprocess
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse, StreamingResponse)
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import auth, config, embed, llm, search, vault

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("agentos")

app = FastAPI(title="AgentOS Second Brain", docs_url=None, redoc_url=None)

app.add_middleware(
    SessionMiddleware,
    secret_key=config.SESSION_SECRET or secrets.token_urlsafe(32),
    session_cookie="agentos",
    max_age=config.SESSION_DAYS * 86400,
    same_site="lax",
    https_only=bool(config.BASE_URL.startswith("https")),
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])

if config.STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=str(config.STATIC)), name="static")


@app.on_event("startup")
async def startup():
    for p in config.problems():
        log.warning("config: %s", p)
    if not config.SESSION_SECRET:
        log.warning("SESSION_SECRET unset — using an ephemeral key; sessions drop "
                    "on restart")
    log.info("vault=%s db=%s", config.VAULT, config.DB)
    embed.warm()


def user(request: Request):
    return auth.require(request)


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
    return FileResponse(str(idx))


# --------------------------------------------------------------- authed API

@app.get("/api/status")
async def status(u=Depends(user)):
    return {
        "user": u,
        "index": search.index_status(),
        "vault": str(config.VAULT),
        "model": config.LLM_MODEL,
        "provider": config.LLM_BASE_URL,
        "llm_configured": llm.configured(),
        "problems": config.problems(),
    }


@app.get("/api/graph")
async def api_graph(u=Depends(user)):
    """The whole vault as nodes + edges. Small enough to send at once — a
    personal vault is thousands of files, not millions."""
    docs = vault.load() + vault.load_system()
    edges, missing = vault.graph(docs)
    nodes = []
    for d in docs:
        nodes.append({
            "id": d.id, "title": d.title, "layer": d.layer, "ring": d.ring,
            "path": d.path, "tags": d.tags, "links": d.links,
            "size": d.size, "mtime": d.mtime,
            "words": len(d.body.split()),
            "excerpt": d.body[:220].replace("\n", " ").strip(),
        })
    return {"nodes": nodes, "edges": edges, "missing": missing,
            "stats": vault.stats(docs)}


@app.get("/api/doc")
async def api_doc(id: str, u=Depends(user)):
    for d in vault.load():
        if d.id == id:
            return d.public()
    raise HTTPException(404, "no document %r" % id)


@app.get("/api/search")
async def api_search(q: str, k: int = 0, layers: str = "", u=Depends(user)):
    return search.search(q, top_k=k or None,
                         layers=[l for l in layers.split(",") if l] or None)


@app.post("/api/ask")
async def api_ask(request: Request, u=Depends(user)):
    body = await request.json()
    question = (body.get("q") or "").strip()
    if not question:
        raise HTTPException(400, "empty question")

    found = search.search(question, top_k=body.get("k") or config.TOP_K)
    hits = found["hits"]
    messages = llm.build_prompt(question, hits)

    async def gen():
        # Citations first so the UI can render sources before the answer streams.
        import json as _json
        yield "event: sources\ndata: %s\n\n" % _json.dumps([
            {"n": i, "title": h["title"], "path": h["path"], "doc_id": h["doc_id"],
             "heading": h["heading"], "layer": h["layer"], "matched": h["matched"]}
            for i, h in enumerate(hits, 1)])
        async for delta in llm.stream(messages):
            yield "event: delta\ndata: %s\n\n" % _json.dumps(delta)
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.post("/api/reindex")
async def api_reindex(u=Depends(user)):
    from .index import build
    return build(full=False)


@app.post("/api/sync")
async def api_sync(u=Depends(user)):
    """git pull, then reindex. The button version of the cron job."""
    try:
        out = subprocess.run(["git", "pull", "--ff-only"], cwd=str(config.ROOT),
                             capture_output=True, text=True, timeout=60)
        pull = (out.stdout + out.stderr).strip()
    except Exception as e:                          # noqa: BLE001
        pull = "git pull failed: %s" % e
    from .index import build
    return {"pull": pull, "index": build(full=False)}


@app.exception_handler(HTTPException)
async def on_http_error(request: Request, exc: HTTPException):
    if exc.status_code == 401 and not request.url.path.startswith("/api/"):
        return RedirectResponse("/auth/login")
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
