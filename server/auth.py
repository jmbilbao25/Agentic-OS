"""Single-user password auth.

Threat model: one person's private notes, reachable from the public internet.
That means the password is the only thing between a scanner and the vault, so:

- stored as a PBKDF2-SHA256 hash, never plaintext at rest if avoidable
- compared with hmac.compare_digest, so failures leak no timing signal
- throttled with a per-IP lockout, because OAuth used to provide that for free
  and a bare password does not
- an unset password denies everyone rather than admitting everyone

There is no registration, no reset, and no second user. `python -m
server.tools.setpass` is the whole user-management surface.
"""
import base64
import hashlib
import hmac
import logging
import os
import time
from typing import Dict, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from . import config

log = logging.getLogger("agentos.auth")
router = APIRouter()

ITERATIONS = 200_000
_fails: Dict[str, Tuple[int, float]] = {}       # ip -> (count, first_attempt_ts)


# ------------------------------------------------------------------ hashing

def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    b64 = lambda b: base64.b64encode(b).decode()          # noqa: E731
    return "pbkdf2_sha256$%d$%s$%s" % (ITERATIONS, b64(salt), b64(dk))


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = encoded.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                 base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except (ValueError, TypeError):
        return False


def check(username: str, password: str) -> bool:
    """Always does the full comparison work, so a wrong username and a wrong
    password cost the same time."""
    user_ok = hmac.compare_digest(username.strip(), config.AUTH_USER)
    if config.AUTH_PASSWORD_HASH:
        pass_ok = verify_password(password, config.AUTH_PASSWORD_HASH)
    elif config.AUTH_PASSWORD:
        pass_ok = hmac.compare_digest(password, config.AUTH_PASSWORD)
    else:
        return False                                    # unset denies everyone
    return user_ok and pass_ok


# ------------------------------------------------------------------ throttle

def _client_ip(request: Request) -> str:
    # Trust X-Forwarded-For only because uvicorn runs with
    # --forwarded-allow-ips=127.0.0.1, i.e. only the local reverse proxy can set it.
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def locked_for(ip: str) -> int:
    """Seconds remaining on a lockout, or 0."""
    rec = _fails.get(ip)
    if not rec:
        return 0
    count, first = rec
    if count < config.MAX_ATTEMPTS:
        return 0
    left = int(config.LOCKOUT_SECONDS - (time.time() - first))
    if left <= 0:
        _fails.pop(ip, None)
        return 0
    return left


def note_failure(ip: str):
    count, first = _fails.get(ip, (0, time.time()))
    if time.time() - first > config.LOCKOUT_SECONDS:
        count, first = 0, time.time()
    _fails[ip] = (count + 1, first)


def clear_failures(ip: str):
    _fails.pop(ip, None)


# ------------------------------------------------------------------ session

def current_user(request: Request) -> Optional[dict]:
    if config.auth_bypassed():
        return {"user": "dev", "dev": True}
    u = request.session.get("user")
    if not u:
        return None
    # If the password changed, existing sessions must die. Binding the session to
    # a fingerprint of the current credential does that without a session store.
    if u.get("fp") != _fingerprint():
        request.session.pop("user", None)
        return None
    return u


def _fingerprint() -> str:
    secret = config.AUTH_PASSWORD_HASH or config.AUTH_PASSWORD or ""
    return hashlib.sha256((config.AUTH_USER + secret).encode()).hexdigest()[:16]


def require(request: Request) -> dict:
    u = current_user(request)
    if not u:
        raise HTTPException(status_code=401, detail="not authenticated")
    return u


# ------------------------------------------------------------------ routes

@router.get("/login")
async def login_form(request: Request, e: str = ""):
    if current_user(request):
        return RedirectResponse("/")
    if not config.auth_configured():
        return HTMLResponse(_page(
            note="No password is set on this instance.",
            detail="Run <code>python -m server.tools.setpass</code> on the server, "
                   "then restart: <code>sudo systemctl restart agentos</code>",
            form=False), status_code=503)
    left = locked_for(_client_ip(request))
    if left:
        return HTMLResponse(_page(
            note="Too many attempts.",
            detail="Try again in %d minute%s." % (max(1, left // 60),
                                                  "" if left < 120 else "s"),
            form=False), status_code=429)
    return HTMLResponse(_page(error=e))


@router.post("/login")
async def login_submit(request: Request):
    ip = _client_ip(request)
    left = locked_for(ip)
    if left:
        return HTMLResponse(_page(note="Too many attempts.",
                                  detail="Locked for %d more seconds." % left,
                                  form=False), status_code=429)

    form = await request.form()
    username = str(form.get("username", ""))
    password = str(form.get("password", ""))

    if not check(username, password):
        note_failure(ip)
        remaining = config.MAX_ATTEMPTS - _fails.get(ip, (0, 0))[0]
        log.warning("failed login from %s (%d attempts left)", ip, max(0, remaining))
        return HTMLResponse(_page(error="Wrong username or password."),
                            status_code=401)

    clear_failures(ip)
    request.session["user"] = {"user": config.AUTH_USER, "fp": _fingerprint(),
                               "since": int(time.time())}
    log.info("signed in from %s", ip)
    return RedirectResponse("/", status_code=303)


@router.get("/logout")
@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/auth/login", status_code=303)


@router.get("/me")
async def me(request: Request):
    u = current_user(request)
    return {"authenticated": bool(u), "user": u,
            "configured": config.auth_configured(),
            "bypassed": config.auth_bypassed()}


# ------------------------------------------------------------------ the page

def _page(error: str = "", note: str = "", detail: str = "", form: bool = True):
    msg = ""
    if note:
        msg = '<p class="note">%s</p>' % note
    if detail:
        msg += '<p class="detail">%s</p>' % detail
    if error:
        msg += '<p class="err">%s</p>' % error

    body = """
  <form method="post" action="/auth/login" autocomplete="on">
    <label>Username<input name="username" value="%s" autocapitalize="none"
      autocomplete="username" required autofocus></label>
    <label>Password<input name="password" type="password"
      autocomplete="current-password" required></label>
    <button type="submit">Enter</button>
  </form>""" % (config.AUTH_USER if form else "") if form else ""

    return """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>AgentOS</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#04060b;
color:#d7e0ec;font:14px/1.6 ui-sans-serif,-apple-system,Segoe UI,sans-serif}
.wrap{width:min(360px,92vw);padding:34px 30px;border:1px solid #1a2230;
border-radius:14px;background:linear-gradient(180deg,#0b0f17,#070a11);
box-shadow:0 24px 70px rgba(0,0,0,.6)}
.orb{width:38px;height:38px;margin:0 auto 20px;position:relative}
.orb i{position:absolute;inset:0;border-radius:50%%;border:1px dotted #b06cff;
opacity:.65;animation:spin 9s linear infinite}
.orb i:nth-child(2){inset:6px;border-color:#ffb03d;animation-duration:6s;
animation-direction:reverse}
.orb b{position:absolute;inset:14px;border-radius:50%%;
background:radial-gradient(circle at 32%% 32%%,#ffe0b8,#ff8a3d 60%%,#a3491a);
box-shadow:0 0 20px rgba(255,138,61,.8)}
@keyframes spin{to{transform:rotate(360deg)}}
h1{font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:#7c8798;
text-align:center;margin:0 0 22px;font-weight:500}
h1 b{color:#d7e0ec}
label{display:block;font-size:11px;letter-spacing:.13em;text-transform:uppercase;
color:#7c8798;margin-bottom:13px}
input{width:100%%;margin-top:6px;background:#070a10;border:1px solid #253040;
border-radius:8px;padding:10px 12px;color:#d7e0ec;font:inherit;font-size:14px;
outline:none;letter-spacing:normal;text-transform:none}
input:focus{border-color:#ff8a3d}
button{width:100%%;margin-top:8px;background:#ff8a3d;border:0;border-radius:8px;
padding:11px;color:#1a0d04;font:inherit;font-weight:600;font-size:14px;
letter-spacing:.05em;cursor:pointer}
button:hover{background:#ffa05c}
p{margin:0 0 14px;font-size:12.5px;text-align:center}
.note{color:#ffcf9a;font-weight:600}
.detail{color:#7c8798}
.err{color:#ff9b8a;background:rgba(90,26,20,.4);border:1px solid #6b2a22;
border-radius:7px;padding:8px}
code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11.5px;
background:#0b0e14;border:1px solid #1a2230;border-radius:4px;padding:1px 5px;
color:#f0b98a}
.foot{margin:18px 0 0;font-size:10.5px;color:#4c5567;letter-spacing:.1em;
text-transform:uppercase}
</style></head><body>
<div class="wrap">
  <div class="orb"><i></i><i></i><b></b></div>
  <h1>Agent<b>OS</b> · second brain</h1>
  %s%s
  <p class="foot">private instance</p>
</div></body></html>""" % (msg, body)
