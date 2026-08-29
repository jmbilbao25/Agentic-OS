"""Single-user credential auth.

Threat model: this is one person's private notes reachable from the public
internet. So the design is deliberately narrow — one username, one password hash,
no registration, no password reset, no second user, no recovery email. Every one
of those is an attack surface that exists to solve a problem a single operator
does not have. Losing the password means editing .env on the box, which is a
thing you can do and an attacker cannot.

What this file does defend against:

- Offline cracking if .env leaks — PBKDF2, 600k iterations, per-install salt.
- Online guessing — per-address failure counter with a lockout window.
- Username enumeration — a wrong username costs exactly as much as a wrong
  password, because we hash against a decoy either way.
- Login CSRF — a token minted into the form and checked on submit.
- Session fixation — the session id is regenerated on successful login.
- Open redirects — `next` is accepted only when it is a local path.

An empty credential config denies everyone rather than admitting anyone.
"""
import logging
import secrets
import time
from typing import Optional
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from . import config
from .passwd import hash_password, looks_hashed, verify

log = logging.getLogger("agentos.auth")
router = APIRouter()

# addr -> {"fails": int, "until": epoch}
_attempts: dict = {}
_ATTEMPT_CAP = 4096            # ponytail: flat dict, pruned on write. One
                               # operator means this never grows past a handful;
                               # the cap stops a spoofed-header flood from
                               # eating memory. Move to redis if this ever
                               # serves more than one person.


# ----------------------------------------------------------------- rate limit

def _client(request: Request) -> str:
    """Best-effort client identity.

    X-Forwarded-For is only trusted when the app is behind a proxy we told it
    about, because otherwise a client can set it freely and get a fresh failure
    budget per request — which would make the lockout decorative.
    """
    if config.TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _locked_for(addr: str) -> int:
    rec = _attempts.get(addr)
    if not rec:
        return 0
    left = int(rec.get("until", 0) - time.time())
    return max(0, left)


def _record_failure(addr: str):
    if len(_attempts) > _ATTEMPT_CAP:
        now = time.time()
        for k, v in list(_attempts.items()):
            if v.get("until", 0) < now:
                _attempts.pop(k, None)
    rec = _attempts.setdefault(addr, {"fails": 0, "until": 0})
    rec["fails"] += 1
    if rec["fails"] >= config.LOGIN_MAX_FAILS:
        rec["until"] = time.time() + config.LOGIN_LOCKOUT_SECONDS
        rec["fails"] = 0
        log.warning("locking out %s for %ss", addr, config.LOGIN_LOCKOUT_SECONDS)


def _clear_failures(addr: str):
    _attempts.pop(addr, None)


# --------------------------------------------------------------- credentials

def check_credentials(username: str, password: str) -> bool:
    """Constant-ish time credential check against the configured single user."""
    expected_user = config.AUTH_USER
    encoded = config.AUTH_PASSWORD_HASH

    if not encoded and config.AUTH_PASSWORD:
        # Plaintext fallback. Hash it on the fly so the comparison path is
        # identical; config.problems() nags about it separately.
        encoded = hash_password(config.AUTH_PASSWORD, iterations=1000)

    if not expected_user or not encoded:
        return False

    user_ok = secrets.compare_digest((username or "").strip().lower(),
                                     expected_user.lower())
    # Run the KDF unconditionally, against the real hash, and only *then* fold in
    # the username result. Short-circuiting on a wrong username would return in
    # microseconds while a wrong password took ~100ms, and that gap tells an
    # attacker the username they guessed was wrong — which is the whole of
    # username enumeration. Measured before this change: 0.008s vs 0.101s.
    pw_ok = verify(password or "", encoded)
    return user_ok and pw_ok


# ------------------------------------------------------------------ sessions

def current_user(request: Request) -> Optional[dict]:
    if config.auth_bypassed():
        return {"name": "Local Dev", "user": "dev", "dev": True}
    u = request.session.get("user")
    if not u:
        return None
    # Re-check against live config on every request: changing the username in
    # .env and restarting should invalidate old cookies immediately, not
    # whenever they happen to expire.
    if not config.AUTH_USER or \
            (u.get("user", "").lower() != config.AUTH_USER.lower()):
        request.session.pop("user", None)
        return None
    return u


def require(request: Request) -> dict:
    u = current_user(request)
    if not u:
        raise HTTPException(status_code=401, detail="not authenticated")
    return u


def _safe_next(raw: str) -> str:
    """Only local paths. `//evil.com` and `https://evil.com` are not local."""
    if not raw or not raw.startswith("/") or raw.startswith("//"):
        return "/"
    return raw


# -------------------------------------------------------------------- routes

@router.get("/login")
async def login_form(request: Request, next: str = "/", error: str = ""):
    if current_user(request):
        return RedirectResponse(_safe_next(next))

    if not config.auth_configured():
        return HTMLResponse(_page(
            "No credentials set",
            "<p>This instance has no username or password configured, so nobody "
            "can sign in — including you. That is the safe default, not a bug.</p>"
            "<p class='step'>Run <code>python -m server.passwd</code>, paste the "
            "two lines it prints into <code>server/.env</code>, and restart.</p>"),
            status_code=503)

    locked = _locked_for(_client(request))
    if locked:
        return HTMLResponse(_page(
            "Too many attempts",
            "<p>Locked for <b>%d</b> more seconds. The counter is per address and "
            "clears on its own.</p>" % locked), status_code=429)

    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token

    return HTMLResponse(_login_page(token, _safe_next(next), error))


async def _form(request: Request) -> dict:
    """Parse the login form with the standard library.

    Both of FastAPI's usual routes here — `Form()` parameters and Starlette's
    `request.form()` — hard-require python-multipart, even for a body that
    contains no multipart at all. We author this form, it is always
    application/x-www-form-urlencoded, and urllib parses that in one call. So
    this is a dependency avoided rather than a wheel reinvented.
    """
    ctype = request.headers.get("content-type", "")
    if not ctype.startswith("application/x-www-form-urlencoded"):
        return {}
    raw = (await request.body())[:8192]        # a login form is never large
    parsed = parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True)
    return {k: v[0] for k, v in parsed.items() if v}


@router.post("/login")
async def login_submit(request: Request):
    form = await _form(request)
    username = form.get("username", "")
    password = form.get("password", "")
    csrf = form.get("csrf", "")

    addr = _client(request)
    dest = _safe_next(form.get("next", "/"))

    locked = _locked_for(addr)
    if locked:
        return HTMLResponse(_page(
            "Too many attempts",
            "<p>Locked for <b>%d</b> more seconds.</p>" % locked), status_code=429)

    want = request.session.get("csrf", "")
    if not want or not secrets.compare_digest(csrf or "", want):
        # Usually a stale tab rather than an attack; send them back for a fresh
        # token instead of showing an error they cannot act on.
        return RedirectResponse("/auth/login?next=%s&error=expired" % dest,
                                status_code=303)

    if not check_credentials(username, password):
        _record_failure(addr)
        log.warning("failed sign-in for %r from %s", (username or "")[:64], addr)
        left = config.LOGIN_MAX_FAILS - _attempts.get(addr, {}).get("fails", 0)
        err = "locked" if _locked_for(addr) else "bad"
        if 0 < left <= 3 and err == "bad":
            err = "bad%d" % left
        return RedirectResponse("/auth/login?next=%s&error=%s" % (dest, err),
                                status_code=303)

    _clear_failures(addr)
    # Session fixation: drop everything that was in the pre-auth session,
    # including the CSRF token that was just spent.
    request.session.clear()
    request.session["user"] = {"user": config.AUTH_USER,
                              "name": config.AUTH_USER,
                              "at": int(time.time())}
    log.info("signed in: %s from %s", config.AUTH_USER, addr)
    return RedirectResponse(dest, status_code=303)


@router.post("/logout")
async def logout_post(request: Request):
    request.session.clear()
    return RedirectResponse("/auth/login", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/auth/login", status_code=303)


@router.get("/me")
async def me(request: Request):
    u = current_user(request)
    return {"authenticated": bool(u), "user": u,
            "configured": config.auth_configured(),
            "bypassed": config.auth_bypassed(),
            "hashed": looks_hashed(config.AUTH_PASSWORD_HASH)}


# ---------------------------------------------------------------------- views

ERRORS = {
    "bad": "That username and password did not match.",
    "bad3": "That did not match. 3 attempts left before a lockout.",
    "bad2": "That did not match. 2 attempts left before a lockout.",
    "bad1": "That did not match. 1 attempt left before a lockout.",
    "locked": "Too many attempts. Locked for %d minutes."
              % max(1, config.LOGIN_LOCKOUT_SECONDS // 60),
    "expired": "That form went stale. Try again.",
}


def _login_page(token: str, dest: str, error: str) -> str:
    msg = ERRORS.get(error, "")
    alert = ('<p class="alert" role="alert">%s</p>' % msg) if msg else ""
    return """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Sign in — AgentOS</title>
<link rel="stylesheet" href="/static/css/app.css">
<link rel="icon" href="/static/favicon.svg">
</head>
<body class="auth">
<main class="auth-card">
  <div class="auth-mark" aria-hidden="true"><span class="auth-core"></span></div>
  <h1>Your second brain</h1>
  <p class="auth-sub">One account. This instance holds private notes, so an
  unrecognised sign-in is refused rather than queued for approval.</p>
  %s
  <form method="post" action="/auth/login" class="auth-form">
    <input type="hidden" name="csrf" value="%s">
    <input type="hidden" name="next" value="%s">
    <label for="u">Username</label>
    <input id="u" name="username" autocomplete="username" required autofocus
           spellcheck="false" autocapitalize="none">
    <label for="p">Password</label>
    <input id="p" name="password" type="password" autocomplete="current-password"
           required>
    <button type="submit">Sign in</button>
  </form>
</main>
</body></html>
""" % (alert, token, dest)


def _page(title, body):
    """A dead-end page: misconfiguration or lockout. Same shell as the form so
    the app never drops you onto something that looks like a different product."""
    return """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>%s — AgentOS</title>
<link rel="stylesheet" href="/static/css/app.css">
<link rel="icon" href="/static/favicon.svg">
</head>
<body class="auth">
<main class="auth-card">
  <div class="auth-mark" aria-hidden="true"><span class="auth-core"></span></div>
  <h1>%s</h1>
  <div class="auth-sub">%s</div>
  <p><a href="/auth/login">Back to sign in</a></p>
</main>
</body></html>
""" % (title, title, body)
