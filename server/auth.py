"""Google OAuth with a single-account allowlist.

Threat model: this is one person's private notes on the public internet. So the
allowlist is checked server-side against the *verified* email Google returns, and
an empty allowlist denies everyone rather than admitting anyone. There is no
registration path, no password reset, and no second user.
"""
import logging
import secrets
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from . import config

log = logging.getLogger("agentos.auth")
router = APIRouter()

_oauth = None


def oauth():
    """Lazily build the OAuth client so the app still boots unconfigured."""
    global _oauth
    if _oauth is not None:
        return _oauth
    if not config.auth_configured():
        return None
    from authlib.integrations.starlette_client import OAuth
    o = OAuth()
    o.register(
        name="google",
        client_id=config.GOOGLE_CLIENT_ID,
        client_secret=config.GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    _oauth = o
    return _oauth


def current_user(request: Request) -> Optional[dict]:
    if config.auth_bypassed():
        return {"email": "dev@localhost", "name": "Local Dev", "dev": True}
    u = request.session.get("user")
    if not u:
        return None
    # Re-check the allowlist on every request: revoking access should take effect
    # immediately, not whenever the cookie happens to expire.
    if u.get("email", "").lower() not in config.ALLOWED_EMAILS:
        request.session.pop("user", None)
        return None
    return u


def require(request: Request) -> dict:
    u = current_user(request)
    if not u:
        raise HTTPException(status_code=401, detail="not authenticated")
    return u


@router.get("/login")
async def login(request: Request):
    o = oauth()
    if not o:
        return HTMLResponse(_page(
            "Not configured",
            "Google OAuth is not set up yet. Add <code>GOOGLE_CLIENT_ID</code>, "
            "<code>GOOGLE_CLIENT_SECRET</code> and <code>ALLOWED_EMAILS</code> to "
            "<code>server/.env</code>, then restart.<br><br>Redirect URI to register: "
            "<code>%s/auth/callback</code>" % (config.BASE_URL or "https://YOUR-HOST")),
            status_code=503)
    redirect = config.OAUTH_REDIRECT_URI or str(request.url_for("callback"))
    request.session["nonce"] = secrets.token_urlsafe(16)
    return await o.google.authorize_redirect(request, redirect,
                                             nonce=request.session["nonce"])


@router.get("/callback", name="callback")
async def callback(request: Request):
    o = oauth()
    if not o:
        raise HTTPException(status_code=503, detail="oauth not configured")
    try:
        token = await o.google.authorize_access_token(request)
        info = token.get("userinfo") or await o.google.parse_id_token(
            request, token, nonce=request.session.get("nonce"))
    except Exception as e:                          # noqa: BLE001
        log.warning("oauth exchange failed: %s", e)
        return HTMLResponse(_page("Sign-in failed", "Could not complete Google "
                                  "sign-in. <a href='/auth/login'>Try again</a>."),
                            status_code=400)

    email = (info.get("email") or "").lower()
    verified = info.get("email_verified", False)

    if not verified:
        return HTMLResponse(_page("Unverified email",
                                  "Google reports this address as unverified."),
                            status_code=403)
    if email not in config.ALLOWED_EMAILS:
        log.warning("denied sign-in for %s", email)
        return HTMLResponse(_page(
            "Not your brain",
            "<code>%s</code> is not on the allowlist for this instance." % email),
            status_code=403)

    request.session.pop("nonce", None)
    request.session["user"] = {"email": email,
                              "name": info.get("name") or email.split("@")[0],
                              "picture": info.get("picture", "")}
    log.info("signed in: %s", email)
    return RedirectResponse("/")


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/auth/login")


@router.get("/me")
async def me(request: Request):
    u = current_user(request)
    return {"authenticated": bool(u), "user": u,
            "configured": config.auth_configured(),
            "bypassed": config.auth_bypassed()}


def _page(title, body, cta=None):
    return """<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AgentOS — %s</title>
<style>
:root{color-scheme:dark}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#05070d;
color:#c9d3df;font:15px/1.65 ui-sans-serif,-apple-system,Segoe UI,sans-serif}
.b{max-width:30rem;padding:2.5rem;border:1px solid #1d2532;border-radius:14px;
background:linear-gradient(180deg,#0c1017,#080b11);text-align:center}
h1{font-size:1.1rem;margin:0 0 .75rem;letter-spacing:.02em}
p{color:#8b97a6;margin:0}
code{background:#0b0e14;border:1px solid #1d2532;border-radius:4px;padding:1px 5px;
font-size:.85em;color:#e0b089}
a{color:#f0873f}
.dot{width:34px;height:34px;margin:0 auto 1.25rem;border-radius:50%%;
background:radial-gradient(circle at 30%% 30%%,#ffc65f,#f0873f 60%%,#7a3d18);
box-shadow:0 0 28px #f0873f66}
</style>
<div class="b"><div class="dot"></div><h1>%s</h1><p>%s</p>%s</div>
""" % (title, title, body, cta or "")
