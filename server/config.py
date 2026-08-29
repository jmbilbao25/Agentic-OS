"""Configuration. Everything that could differ between machines lives here.

The provider is deliberately three variables (base URL, key, model) so that
switching between an aggregator, a lab's own API, or a local server is an edit to
.env and nothing else. See brain/wiki/Model Access Is Not Transferable.md
"""
import os
from pathlib import Path

try:  # optional: .env is a convenience, not a requirement
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass


def _bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _list(name, default=""):
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


ROOT = Path(__file__).resolve().parent.parent
VAULT = Path(os.getenv("AGENTOS_VAULT", ROOT / "brain"))
DB = Path(os.getenv("AGENTOS_DB", Path(__file__).resolve().parent / "index.db"))
STATIC = Path(__file__).resolve().parent / "static"

HOST = os.getenv("AGENTOS_HOST", "127.0.0.1")
PORT = int(os.getenv("AGENTOS_PORT", "8000"))
BASE_URL = os.getenv("AGENTOS_BASE_URL", "").rstrip("/")

# --- inference provider (OpenAI-compatible shape) ---
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
LLM_API_KEY = os.getenv("OPENROUTER_API_KEY") or os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "90"))

# --- embeddings (local, CPU, quantised) ---
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBED_DIM = int(os.getenv("EMBED_DIM", "384"))
EMBED_ENABLED = _bool("EMBED_ENABLED", True)

# Retrieval-tuned embedding models are asymmetric: the query side wants an
# instruction prefix that the passage side must NOT have. This is the documented
# prefix for the BGE v1.5 family. Measured on this vault it is worth ~30% of
# top-1 accuracy on paraphrased queries, so it is on by default.
# E5 models want "query: " / "passage: " instead. Set to empty to disable.
EMBED_QUERY_PREFIX = os.getenv(
    "EMBED_QUERY_PREFIX",
    "Represent this sentence for searching relevant passages: ")
EMBED_PASSAGE_PREFIX = os.getenv("EMBED_PASSAGE_PREFIX", "")

# --- auth ---
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "")
ALLOWED_EMAILS = [e.lower() for e in _list("ALLOWED_EMAILS")]
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "30"))

# Escape hatch for local development. Refuses to engage unless the bind address
# is loopback, so it cannot accidentally ship an open instance.
DEV_NO_AUTH = _bool("DEV_NO_AUTH", False)

# --- retrieval tuning ---
CHUNK_CHARS = int(os.getenv("CHUNK_CHARS", "1100"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))
TOP_K = int(os.getenv("TOP_K", "8"))

# Reciprocal Rank Fusion. RRF_K damps how much any single list's top hit counts;
# the classic default is 60, but that was tuned on web-scale corpora. On a
# personal vault (hundreds of chunks, not millions) a smaller k lets a confident
# top hit actually win, and unweighted fusion measurably *underperformed*
# semantic-alone because keyword search returns much of a small corpus at
# near-random rank. Weighting semantic higher fixes that while keeping keyword's
# exact-match wins (a filename, a rare token, an error string).
#
# Tuned on a 9-probe / 14-document benchmark — small enough that these are
# sensible defaults, not universal truths. Re-run tools/eval_retrieval.py after
# the vault grows substantially.
RRF_K = int(os.getenv("RRF_K", "20"))
W_KEYWORD = float(os.getenv("W_KEYWORD", "1.0"))
W_SEMANTIC = float(os.getenv("W_SEMANTIC", "2.0"))
POOL_MULT = int(os.getenv("POOL_MULT", "6"))

LAYERS = ["raw", "wiki", "output", "decisions", "journal", "loops"]


def auth_configured():
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and ALLOWED_EMAILS)


def auth_bypassed():
    """True only when explicitly asked for AND bound to loopback."""
    return DEV_NO_AUTH and HOST in ("127.0.0.1", "localhost", "::1")


def problems():
    """Config issues worth surfacing in the UI rather than failing silently."""
    out = []
    if not VAULT.exists():
        out.append("vault not found at %s" % VAULT)
    if not auth_configured() and not auth_bypassed():
        out.append("Google OAuth not configured — set GOOGLE_CLIENT_ID, "
                   "GOOGLE_CLIENT_SECRET and ALLOWED_EMAILS in server/.env")
    if auth_configured() and not SESSION_SECRET:
        out.append("SESSION_SECRET is empty — sessions will not survive a restart")
    if not LLM_API_KEY:
        out.append("no inference key — search works, Ask will not")
    if DEV_NO_AUTH and not auth_bypassed():
        out.append("DEV_NO_AUTH ignored: only honoured on a loopback bind")
    return out
