"""Boot configuration — the things that genuinely cannot change at runtime.

Paths, the bind address, the session secret, the credentials. Everything a person
might want to tune *while looking at the result* lives in settings.py instead and
is editable from the UI.

For backwards compatibility, the runtime keys are still readable as
`config.LLM_MODEL`, `config.TOP_K` and so on: a module-level __getattr__ (PEP
562) forwards them to settings. That keeps every existing caller — including
tools/eval_retrieval.py — working while the values became live-editable
underneath them.
"""
import os
from pathlib import Path

try:  # optional: .env is a convenience, not a requirement
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass

from . import settings as _settings


def _bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _list(name, default=""):
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


# ------------------------------------------------------------------- paths

ROOT = Path(__file__).resolve().parent.parent
VAULT = Path(os.getenv("AGENTOS_VAULT", ROOT / "brain"))
DB = Path(os.getenv("AGENTOS_DB", Path(__file__).resolve().parent / "index.db"))
STATIC = Path(__file__).resolve().parent / "static"

# ------------------------------------------------------------------ server

HOST = os.getenv("AGENTOS_HOST", "127.0.0.1")
PORT = int(os.getenv("AGENTOS_PORT", "8000"))
BASE_URL = os.getenv("AGENTOS_BASE_URL", "").rstrip("/")

# Only turn this on when something in front of the app actually sets
# X-Forwarded-For. Trusting it unconditionally would let any client forge a
# fresh address per request and walk straight through the login lockout.
TRUST_PROXY = _bool("AGENTOS_TRUST_PROXY", False)

# -------------------------------------------------------------------- auth
#
# One person, one password. There is no registration, no reset, and no second
# user — see server/auth.py for the threat model.

AUTH_USER = os.getenv("AGENTOS_USER", "").strip()

# Preferred: a PBKDF2 hash minted by `python -m server.passwd`. The plaintext
# variable exists because a hash is a bad first experience, but it is reported as
# a problem in the UI until you replace it.
AUTH_PASSWORD_HASH = os.getenv("AGENTOS_PASSWORD_HASH", "").strip()
AUTH_PASSWORD = os.getenv("AGENTOS_PASSWORD", "")

SESSION_SECRET = os.getenv("SESSION_SECRET", "")
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "30"))

# Brute-force ceiling. Counted per client address, in memory — a restart clears
# it, which is an acceptable ceiling for a single-user instance.
LOGIN_MAX_FAILS = int(os.getenv("LOGIN_MAX_FAILS", "8"))
LOGIN_LOCKOUT_SECONDS = int(os.getenv("LOGIN_LOCKOUT_SECONDS", "900"))

# Escape hatch for local development. Refuses to engage unless the bind address
# is loopback, so it cannot accidentally ship an open instance.
DEV_NO_AUTH = _bool("DEV_NO_AUTH", False)

# ------------------------------------------------------------------- vault

LAYERS = ["raw", "wiki", "output", "decisions", "journal", "loops"]


# ------------------------------------------------- runtime settings proxy

# Read as config.X, resolved live from settings.py. Deliberately NOT assigned at
# module level: __getattr__ only fires for names that are missing.
_RUNTIME_KEYS = frozenset(_settings.BY_KEY)


def __getattr__(name):
    if name in _RUNTIME_KEYS:
        return _settings.get(name)
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


def __dir__():
    return sorted(list(globals()) + list(_RUNTIME_KEYS))


# -------------------------------------------------------------- diagnostics

def auth_configured():
    return bool(AUTH_USER and (AUTH_PASSWORD_HASH or AUTH_PASSWORD))


def auth_bypassed():
    """True only when explicitly asked for AND bound to loopback."""
    return DEV_NO_AUTH and HOST in ("127.0.0.1", "localhost", "::1")


def problems():
    """Config issues worth surfacing in the UI rather than failing silently."""
    out = []
    if not VAULT.exists():
        out.append("Vault not found at %s" % VAULT)
    if not auth_configured() and not auth_bypassed():
        out.append("No credentials set — nobody can sign in. Run "
                   "`python -m server.passwd` and put the result in server/.env "
                   "as AGENTOS_USER and AGENTOS_PASSWORD_HASH.")
    if AUTH_PASSWORD and not AUTH_PASSWORD_HASH:
        out.append("AGENTOS_PASSWORD is a plaintext password in .env. Replace it "
                   "with AGENTOS_PASSWORD_HASH from `python -m server.passwd`.")
    if auth_configured() and not SESSION_SECRET:
        out.append("SESSION_SECRET is empty — everyone gets signed out on restart. "
                   "Generate one with `openssl rand -hex 32`.")
    if DEV_NO_AUTH and not auth_bypassed():
        out.append("DEV_NO_AUTH ignored: only honoured on a loopback bind.")
    if auth_bypassed():
        out.append("DEV_NO_AUTH is on — this instance is unauthenticated. "
                   "Loopback only.")
    return out + _settings.problems()
