"""End-to-end smoke test. One command, no server, no framework.

    python -m server.tools.smoke

Drives the real ASGI app through Starlette's TestClient, so every check goes
through the actual routing, middleware, session and auth stack. Uses a temporary
index and a temporary settings file, so running it never touches your real ones.

What it is for: the things that break silently. An auth gate that stops gating, a
settings write that half-applies, a document the map can draw but not open. Each
assertion carries the failure it is there to catch.

Network is optional. The model catalogue check reports a skip rather than failing
when the provider is unreachable — a smoke test that needs the internet is a smoke
test people stop running.
"""
import json
import os
import shutil
import sys
import tempfile

# Configure before importing the app: config.py reads the environment at import
# time, and auth has to be genuinely on for the gate checks to mean anything.
_TMP = tempfile.mkdtemp(prefix="agentos-smoke-")
_PW = "smoke-test-password-9271"

os.environ.update(
    AGENTOS_DB=os.path.join(_TMP, "index.db"),
    AGENTOS_SETTINGS=os.path.join(_TMP, "settings.json"),
    AGENTOS_HOST="127.0.0.1",
    DEV_NO_AUTH="false",
    AGENTOS_USER="smoke",
    SESSION_SECRET="smoke-secret-000000000000000000000000",
    LOGIN_MAX_FAILS="3",
    LOGIN_LOCKOUT_SECONDS="60",
    AGENTOS_TRUST_PROXY="false",
)

from ..passwd import hash_password                              # noqa: E402
os.environ["AGENTOS_PASSWORD_HASH"] = hash_password(_PW, iterations=20000)

from starlette.testclient import TestClient                     # noqa: E402
from .. import app as app_module, index, settings, vault         # noqa: E402

PASS, FAIL, SKIP = [], [], []


def check(name):
    def wrap(fn):
        try:
            note = fn()
            PASS.append((name, note or ""))
            print("  ok    %s%s" % (name, (" — %s" % note) if note else ""))
        except AssertionError as e:
            FAIL.append((name, str(e)))
            print("  FAIL  %s\n          %s" % (name, e))
        except Exception as e:                                  # noqa: BLE001
            FAIL.append((name, "%s: %s" % (e.__class__.__name__, e)))
            print("  ERROR %s\n          %s: %s" % (name, e.__class__.__name__, e))
        return fn
    return wrap


def skip(name, why):
    SKIP.append((name, why))
    print("  skip  %s — %s" % (name, why))


def sse(client, path, body):
    """Collect an SSE response into a list of (event, data)."""
    out = []
    with client.stream("POST", path, json=body) as r:
        assert r.status_code == 200, "SSE endpoint returned %d" % r.status_code
        buf = ""
        for chunk in r.iter_text():
            buf += chunk
            while "\n\n" in buf:
                frame, buf = buf.split("\n\n", 1)
                ev, data = "message", []
                for line in frame.split("\n"):
                    if line.startswith("event:"):
                        ev = line[6:].strip()
                    elif line.startswith("data:"):
                        data.append(line[5:].strip())
                if data:
                    try:
                        out.append((ev, json.loads("\n".join(data))))
                    except json.JSONDecodeError:
                        pass
    return out


def csrf(client):
    """Fetch a fresh CSRF token, signing out first if a session is already live.

    Needed because GET /auth/login redirects an authenticated caller straight to
    the app, and the app's HTML has no token in it — scraping that page silently
    yields nothing instead of failing where the problem is.
    """
    if client.get("/api/status").status_code == 200:
        client.get("/auth/logout")
    page = client.get("/auth/login")
    assert page.status_code == 200, "login page returned %d" % page.status_code
    marker = 'name="csrf" value="'
    assert marker in page.text, \
        "no CSRF token in the login page (%d bytes)" % len(page.text)
    return page.text.split(marker, 1)[1].split('"', 1)[0]


def login(client, next_to="/"):
    token = csrf(client)
    return client.post("/auth/login", data={
        "username": "smoke", "password": _PW, "csrf": token, "next": next_to},
        follow_redirects=False)


def main():
    print("AgentOS smoke test")
    print("index:    %s" % os.environ["AGENTOS_DB"])
    print("settings: %s\n" % os.environ["AGENTOS_SETTINGS"])

    print("build the index")
    summary = index.build(full=True)
    print("  %s · %d docs · %d chunks · %d vectors\n"
          % (summary["mode"], summary["docs"], summary["chunks_total"],
             summary["vectors_total"]))

    with TestClient(app_module.app) as client:

        # ---------------------------------------------------------- the gate
        print("auth gate")

        @check("healthz is public")
        def _():
            r = client.get("/healthz")
            assert r.status_code == 200 and r.json() == {"ok": True}, r.text

        @check("every API route refuses an unauthenticated caller")
        def _():
            gets = ["/api/status", "/api/graph", "/api/settings", "/api/models",
                    "/api/search?q=x", "/api/doc?id=wiki/Ralph%20Loop",
                    "/api/activities", "/api/activities/runs",
                    "/api/activities/runs/nope"]
            posts = ["/api/ask", "/api/reindex", "/api/sync",
                     "/api/settings/reset", "/api/activities/run"]
            for p in gets:
                assert client.get(p).status_code == 401, "GET %s was not gated" % p
            for p in posts:
                assert client.post(p, json={}).status_code == 401, \
                    "POST %s was not gated" % p
            assert client.put("/api/settings", json={}).status_code == 401, \
                "PUT /api/settings was not gated"
            return "%d routes" % (len(gets) + len(posts) + 1)

        @check("the app root redirects to sign-in instead of rendering")
        def _():
            r = client.get("/", follow_redirects=False)
            assert r.status_code in (302, 307), r.status_code
            assert "/auth/login" in r.headers["location"], r.headers["location"]

        @check("no schema endpoint is exposed")
        def _():
            assert client.get("/openapi.json").status_code == 404, \
                "openapi.json would enumerate the whole API unauthenticated"

        @check("security headers are set")
        def _():
            h = client.get("/healthz").headers
            csp = h.get("content-security-policy", "")
            assert "default-src 'self'" in csp, "no CSP"
            assert "unsafe-inline" not in csp, "CSP allows inline — it should not"
            assert h.get("x-content-type-options") == "nosniff"
            assert h.get("referrer-policy") == "no-referrer"
            assert h.get("x-frame-options") == "DENY"

        # ------------------------------------------------------ credentials
        print("\ncredentials")

        @check("a wrong password is refused")
        def _():
            token = csrf(client)
            r = client.post("/auth/login", data={
                "username": "smoke", "password": "wrong", "csrf": token},
                follow_redirects=False)
            assert r.status_code == 303, r.status_code
            assert "error=" in r.headers["location"], r.headers["location"]
            assert client.get("/api/status").status_code == 401, \
                "a failed login still produced a session"

        @check("a missing CSRF token is refused")
        def _():
            r = client.post("/auth/login", data={
                "username": "smoke", "password": _PW}, follow_redirects=False)
            assert r.status_code == 303 and "error=expired" in r.headers["location"]
            assert client.get("/api/status").status_code == 401, \
                "login succeeded without a CSRF token"

        @check("the lockout engages and ignores the correct password")
        def _():
            from .. import auth
            auth._attempts.clear()
            token = csrf(client)
            for i in range(3):
                client.post("/auth/login", data={
                    "username": "smoke", "password": "no%d" % i, "csrf": token},
                    follow_redirects=False)
            r = client.post("/auth/login", data={
                "username": "smoke", "password": _PW, "csrf": token},
                follow_redirects=False)
            assert r.status_code == 429, \
                "the correct password signed in while locked out (%d)" % r.status_code
            auth._attempts.clear()
            return "locked after 3"

        @check("the right password signs in")
        def _():
            r = login(client)
            assert r.status_code == 303, r.status_code
            assert client.get("/api/status").status_code == 200, "no session"

        @check("an off-site `next` is not honoured")
        def _():
            for bad in ("//evil.example", "https://evil.example/x",
                        "http:/evil.example", "\\\\evil.example"):
                r = login(client, next_to=bad)
                dest = r.headers.get("location", "")
                assert "evil.example" not in dest, \
                    "open redirect: next=%r sent the user to %r" % (bad, dest)
            assert login(client, next_to="/api/status").headers["location"] \
                .endswith("/api/status"), "a local next path was discarded"
            return "4 hostile values"

        @check("signing out drops the session")
        def _():
            client.get("/auth/logout")
            assert client.get("/api/status").status_code == 401
            login(client)

        # ------------------------------------------------------------ vault
        print("\nvault")

        @check("the map and the index agree on what exists")
        def _():
            g = client.get("/api/graph").json()
            st = client.get("/api/status").json()
            drawn = len(g["nodes"])
            indexed = st["index"]["docs"]
            assert drawn == indexed, (
                "the map draws %d notes but only %d are indexed — the SKILLS ring "
                "and the kernel would be unsearchable" % (drawn, indexed))
            return "%d notes, %d edges" % (drawn, len(g["edges"]))

        @check("every node the map draws can be opened")
        def _():
            g = client.get("/api/graph").json()
            broken = []
            for n in g["nodes"]:
                r = client.get("/api/doc", params={"id": n["id"]})
                if r.status_code != 200:
                    broken.append("%s -> %d" % (n["id"], r.status_code))
            assert not broken, "unopenable nodes: %s" % ", ".join(broken)
            return "%d nodes" % len(g["nodes"])

        @check("the kernel, skills and steering all have chunks in the index")
        def _():
            # The direct assertion for the second half of the load_all() bug: the
            # system files were on the map but absent from the index, so Ask could
            # never cite the kernel or a skill. Checking chunk counts rather than
            # a search ranking, because ranking depends on what else is in the
            # vault and would make this test fail for an unrelated reason.
            from ..index import connect
            db = connect()
            counts = {r["doc_id"]: r["n"] for r in db.execute(
                "SELECT doc_id, COUNT(*) n FROM chunks GROUP BY doc_id")}
            db.close()
            system = [d.id for d in vault.load_system()]
            assert system, "load_system() returned nothing"
            missing = [i for i in system if not counts.get(i)]
            assert not missing, "indexed no chunks for: %s" % ", ".join(missing)
            return "%d system docs, %d chunks" % (
                len(system), sum(counts[i] for i in system))

        @check("a document carries its resolved links both ways")
        def _():
            d = client.get("/api/doc",
                           params={"id": "wiki/Git Is The Disk"}).json()
            assert d["backlinks"], "a note this linked-to has no backlinks"
            assert d["outgoing"], "no outgoing links resolved"
            return "%d in, %d out" % (len(d["backlinks"]), len(d["outgoing"]))

        @check("a missing document is a 404, not a 500")
        def _():
            r = client.get("/api/doc", params={"id": "nope/nothing"})
            assert r.status_code == 404, r.status_code
            assert "error" in r.json()

        # -------------------------------------------------------- retrieval
        print("\nretrieval")

        @check("naming a note returns that note first")
        def _():
            # The failure this exists to catch: neither BM25 nor the vectors can
            # see a title, so before W_TITLE went in "AGENTS.md" did not return
            # AGENTS.md at all and "ralph" put Ralph Loop third.
            cases = [("ralph", "wiki/Ralph Loop"),
                     ("AGENTS.md", "kernel/AGENTS"),
                     ("second-brain", "skills/second-brain"),
                     ("deploy-always-on", "loops/deploy-always-on")]
            bad = []
            for q, want in cases:
                hits = client.get("/api/search",
                                  params={"q": q, "k": 3}).json()["hits"]
                top = hits[0]["doc_id"] if hits else "(nothing)"
                if top != want:
                    bad.append("%r -> %s, wanted %s" % (q, top, want))
            assert not bad, "; ".join(bad)
            return "%d name lookups" % len(cases)

        @check("a paraphrase still finds the right note")
        def _():
            hits = client.get("/api/search", params={
                "q": "why keep memory in version control instead of a database",
                "k": 5}).json()["hits"]
            ids = [h["doc_id"] for h in hits]
            assert "wiki/Git Is The Disk" in ids, ids
            return ids[0]

        @check("a hostile query does not break FTS5")
        def _():
            for q in ['"', 'a AND OR NEAR(', '*', ')(', 'x" OR "y', '-- ;drop',
                      'the and of', '🙂']:
                r = client.get("/api/search", params={"q": q, "k": 3})
                assert r.status_code == 200, "%r returned %d" % (q, r.status_code)
                assert "hits" in r.json()
            return "8 inputs"

        @check("an empty query is handled rather than searched")
        def _():
            r = client.get("/api/search", params={"q": "   "}).json()
            assert r["mode"] == "empty" and r["hits"] == [], r

        # --------------------------------------------------------- settings
        print("\nsettings")

        @check("the schema ships everything the form needs")
        def _():
            s = client.get("/api/settings").json()
            assert len(s["schema"]) >= 25, len(s["schema"])
            groups = {g["id"] for g in s["groups"]}
            assert {"inference", "retrieval", "embeddings",
                    "interface"} <= groups, groups
            for f in s["schema"]:
                assert f["label"], "%s has no label" % f["key"]
            return "%d fields, %d groups" % (len(s["schema"]), len(groups))

        @check("a valid change persists and is reported")
        def _():
            r = client.put("/api/settings", json={"TOP_K": 11, "W_SEMANTIC": 2.5})
            assert r.status_code == 200, r.text
            assert set(r.json()["changed"]) == {"TOP_K", "W_SEMANTIC"}
            assert client.get("/api/settings").json()["values"]["TOP_K"] == 11
            assert settings.get("TOP_K") == 11, "the running app did not see it"

        @check("one invalid field blocks the whole write")
        def _():
            before = client.get("/api/settings").json()["values"]["RRF_K"]
            r = client.put("/api/settings", json={"RRF_K": 33, "TOP_K": 9999})
            assert r.status_code == 422, r.status_code
            assert "TOP_K" in r.json()["errors"]
            after = client.get("/api/settings").json()["values"]["RRF_K"]
            assert after == before, \
                "RRF_K was applied even though the write failed (%s -> %s)" % (
                    before, after)

        @check("the API key never comes back to the browser")
        def _():
            client.put("/api/settings", json={"LLM_API_KEY": "sk-or-v1-secrettail"})
            s = client.get("/api/settings").json()
            blob = json.dumps(s)
            assert "sk-or-v1-secrettail" not in blob, "the key was serialised"
            assert s["values"]["LLM_API_KEY"] == ""
            assert s["secrets"]["LLM_API_KEY"] == {"set": True, "hint": "…tail"}
            assert settings.get("LLM_API_KEY") == "sk-or-v1-secrettail"

        @check("a blank secret keeps the stored one; null clears it")
        def _():
            client.put("/api/settings", json={"LLM_API_KEY": ""})
            assert settings.get("LLM_API_KEY") == "sk-or-v1-secrettail", \
                "an untouched masked field wiped the key"
            client.put("/api/settings", json={"LLM_API_KEY": None})
            assert settings.get("LLM_API_KEY") == ""

        @check("an embedding change raises the stale-index flag")
        def _():
            client.post("/api/settings/reset", json={})
            assert not settings.reindex_pending()
            client.put("/api/settings", json={"CHUNK_CHARS": 900})
            assert client.get("/api/status").json()["reindex_pending"] is True, \
                "changing chunk size did not mark the index stale"
            client.post("/api/settings/reset", json={"keys": ["CHUNK_CHARS"]})

        @check("reset falls back to defaults")
        def _():
            client.put("/api/settings", json={"TOP_K": 7})
            r = client.post("/api/settings/reset", json={"keys": ["TOP_K"]})
            assert r.status_code == 200
            assert client.get("/api/settings").json()["values"]["TOP_K"] == 8

        @check("an unknown setting is rejected")
        def _():
            r = client.put("/api/settings", json={"NOT_A_SETTING": 1})
            assert r.status_code == 422, r.status_code
            assert "NOT_A_SETTING" in r.json()["errors"]

        # ------------------------------------------------------- inference
        print("\ninference")

        @check("Ask streams sources and a usable error when no key is set")
        def _():
            client.post("/api/settings/reset", json={"keys": ["LLM_API_KEY"]})
            events = sse(client, "/api/ask", {"q": "why is git the disk"})
            kinds = [e for e, _ in events]
            assert "sources" in kinds, kinds
            assert "error" in kinds, "a missing key produced no error event"
            assert kinds[-1] == "done", "the stream did not close with done"
            msg = next(d["message"] for e, d in events if e == "error")
            assert "key" in msg.lower(), msg
            srcs = next(d for e, d in events if e == "sources")
            assert srcs and srcs[0]["doc_id"], "no citations were emitted"
            return "%d events, %d citations" % (len(events), len(srcs))

        @check("Ask refuses an empty question")
        def _():
            assert client.post("/api/ask", json={"q": "  "}).status_code == 400

        # ------------------------------------------------------ activities
        print("\nactivities")

        @check("the panel lists every activity with its resolved steps")
        def _():
            r = client.get("/api/activities")
            assert r.status_code == 200, r.status_code
            body = r.json()
            names = {a["name"] for a in body["activities"]}
            assert {"fetch-ai-news", "doctor"} <= names, names
            assert not body["will_not_run"], body["will_not_run"]
            news = next(a for a in body["activities"] if a["name"] == "fetch-ai-news")
            assert [s["verb"] for s in news["steps"]] == ["radar", "distill"], news
            assert "brain/raw/" in news["writes"], news["writes"]
            return "%d activities, %d steps in the vocabulary" % (
                len(names), len(body["steps"]))

        @check("an unknown activity is refused before a run is created")
        def _():
            r = client.post("/api/activities/run", json={"name": "does-not-exist"})
            assert r.status_code == 400, r.status_code
            # The refusal has to name what does exist, or the only way to discover
            # the real names is to read the filesystem.
            assert "fetch-ai-news" in r.json()["error"], r.json()

        @check("a run outlives the request that started it")
        def _():
            r = client.post("/api/activities/run", json={"name": "doctor"})
            assert r.status_code == 200, r.text
            rid = r.json()["run_id"]
            assert r.json()["running"] is True, r.json()

            # The log is addressable immediately, by id, from a second request —
            # which is the property that makes a dropped connection survivable.
            got = client.get("/api/activities/runs/%s" % rid)
            assert got.status_code == 200, got.text
            body = got.json()
            assert body["run_id"] == rid and body["name"] == "doctor", body
            assert "next" in body and isinstance(body["events"], list), body

            listed = client.get("/api/activities/runs").json()
            assert any(x["run_id"] == rid for x in listed["runs"]), listed
            return "run %s addressable after the POST returned" % rid

        @check("a cursor never replays or skips an event")
        def _():
            rid = client.post("/api/activities/run",
                              json={"name": "doctor"}).json()["run_id"]
            first = client.get("/api/activities/runs/%s?after=0" % rid).json()
            again = client.get("/api/activities/runs/%s?after=%d"
                               % (rid, first["next"])).json()
            assert again["next"] >= first["next"], (first, again)
            for ev in again["events"]:
                assert ev not in first["events"], "event replayed across the cursor"

        @check("an unknown run id is a 404, so the panel stops polling")
        def _():
            assert client.get("/api/activities/runs/deadbeef").status_code == 404

        @check("running an activity needs a name")
        def _():
            assert client.post("/api/activities/run", json={}).status_code == 400

        @check("no activity can name a shell command")
        def _():
            from server import activities as act
            from server.authoring import WriteRefused
            assert "shell" not in act.STEPS, \
                "a shell verb exists — brain/raw/ is untrusted input"
            body = ("---\nname: x\ndescription: %s\n---\n\n## Steps\n\n- shell: id\n"
                    % ("d" * 40))
            for step in ("- shell: id", "- bash: id", "- run: rm -rf /", "- eval: x"):
                try:
                    act.parse(body.replace("- shell: id", step), "x")
                except WriteRefused:
                    continue
                raise AssertionError("%r was accepted as a step" % step)
            return "4 injection shapes refused"

        @check("the model catalogue normalises whatever the provider returns")
        def _():
            r = client.get("/api/models")
            assert r.status_code == 200, r.status_code
            body = r.json()
            if body.get("error") and not body.get("models"):
                raise RuntimeError("offline: %s" % body["error"])
            models = body["models"]
            assert models, "empty catalogue"
            for m in models[:40]:
                assert set(m) >= {"id", "name", "context", "prompt_per_m",
                                  "completion_per_m", "free"}, m
                assert m["id"]
            return "%d models" % len(models)

        # ----------------------------------------------------------- index
        print("\nindexing")

        @check("an incremental reindex is a no-op when nothing changed")
        def _():
            r = client.post("/api/reindex").json()
            assert r["changed"] == 0, \
                "reindex rewrote %d unchanged docs" % r["changed"]
            assert r["chunks_total"] > 0

        @check("a full reindex reproduces the same chunk count")
        def _():
            before = client.get("/api/status").json()["index"]["chunks"]
            r = client.post("/api/reindex", params={"full": "true"}).json()
            assert r["chunks_total"] == before, \
                "full rebuild changed the chunk count (%d -> %d)" % (
                    before, r["chunks_total"])
            return "%d chunks, mode=%s" % (r["chunks_total"], r["mode"])

        @check("chunking covers every document")
        def _():
            docs = vault.load_all()
            empty = [d.id for d in docs if d.body.strip() and not vault.chunk(d)]
            assert not empty, "documents that produced no chunks: %s" % empty
            return "%d documents" % len(docs)

    # --------------------------------------------------------------- verdict
    print("\n%s" % ("-" * 58))
    print("%d passed, %d failed, %d skipped" % (len(PASS), len(FAIL), len(SKIP)))
    if FAIL:
        print("\nfailures:")
        for n, why in FAIL:
            print("  %s\n    %s" % (n, why))
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(code)
