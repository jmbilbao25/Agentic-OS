"""Runtime settings — everything you can change without a restart.

Three layers, highest wins:

    settings.local.json   what you changed in the UI      (gitignored)
    environment / .env    what the machine was deployed with
    SCHEMA default        what ships

`config.py` keeps only the things that genuinely cannot move at runtime — paths,
bind address, session secret. Everything a person might want to tune while
looking at the result lives here instead, because a model swap that needs a
restart is a model swap nobody makes. See brain/wiki/Model Access Is Not
Transferable.md

The SCHEMA is also the UI: /api/settings ships it to the browser, which renders
the form from it. Adding a knob is one entry here and nothing else.

This module deliberately imports nothing from the rest of the package — config
proxies *into* it, so any import back out would be a cycle.
"""
import json
import logging
import os
import tempfile
import threading
from pathlib import Path

log = logging.getLogger("agentos.settings")

HERE = Path(__file__).resolve().parent
STORE = Path(os.getenv("AGENTOS_SETTINGS", HERE / "settings.local.json"))

# Reserved keys inside the store that are state, not settings.
_PENDING = "__reindex_pending__"

DEFAULT_SYSTEM_PROMPT = """You are the assistant inside a personal second brain. \
You answer strictly from the supplied excerpts of the user's own vault.

Rules:
- Ground every claim in the excerpts. Cite as [n] using the excerpt numbers.
- If the excerpts do not answer the question, say so plainly and name what is \
missing. Never fill the gap from general knowledge without flagging it.
- The user wrote these notes. Do not explain their own ideas back to them at \
length — be direct and add the connection they asked for.
- Prefer the user's own vocabulary from the excerpts over synonyms.
- Brief and specific. No preamble."""


class Field:
    """One tunable value, plus the metadata the UI needs to render it."""

    def __init__(self, key, kind, default, *, group, label, help="",
                 lo=None, hi=None, choices=None, secret=False,
                 reindex=False, restart=False, placeholder="", step=None,
                 env_aliases=()):
        self.key = key
        self.kind = kind          # str text url secret int float bool csv model choice
        self.default = default
        self.group = group
        self.label = label
        self.help = help
        self.lo = lo
        self.hi = hi
        self.choices = choices
        self.secret = secret
        self.reindex = reindex    # changing this invalidates the index
        self.restart = restart    # changing this needs a process restart
        self.placeholder = placeholder
        self.step = step
        self.env_aliases = env_aliases

    def as_json(self):
        return {
            "key": self.key, "kind": self.kind, "group": self.group,
            "label": self.label, "help": self.help, "lo": self.lo, "hi": self.hi,
            "choices": self.choices, "secret": self.secret,
            "reindex": self.reindex, "restart": self.restart,
            "placeholder": self.placeholder, "step": self.step,
            "default": None if self.secret else self.default,
        }


F = Field

SCHEMA = [
    # ------------------------------------------------------------- inference
    F("LLM_BASE_URL", "url", "https://openrouter.ai/api/v1",
      group="inference", label="Base URL",
      help="Any OpenAI-compatible endpoint. OpenRouter, OpenAI, Together, "
           "an Ollama at /v1, or your own proxy.",
      placeholder="https://openrouter.ai/api/v1"),
    F("LLM_API_KEY", "secret", "", secret=True,
      group="inference", label="API key",
      env_aliases=("OPENROUTER_API_KEY",),
      help="Stored in settings.local.json, which is gitignored. Never sent back "
           "to the browser — you get a masked hint instead.",
      placeholder="sk-or-v1-…"),
    # Verified present in OpenRouter's catalogue on 2026-08-30. The previous
    # default, meta-llama/llama-3.3-70b-instruct:free, had been retired upstream
    # and no longer appears in /api/v1/models at all — so a fresh install's very
    # first Ask failed with a model-not-found, which reads as "the app is broken"
    # rather than "that default expired". Free routes get withdrawn regularly;
    # re-check this one against the live catalogue rather than trusting it.
    F("LLM_MODEL", "model", "nvidia/nemotron-3.5-lightning:free",
      group="inference", label="Model",
      help="The model that answers Ask. Swap it live; no restart."),
    F("LLM_FALLBACK_MODELS", "csv", "",
      group="inference", label="Fallback models",
      help="Tried in order if the primary is rate-limited or down. OpenRouter "
           "routes these server-side (3 per request, see llm.py:_batches); "
           "other providers get a client-side retry. Note that every :free "
           "model draws on ONE account-wide quota, so a chain of free models "
           "does not survive the daily cap — only a per-minute spike.",
      placeholder="nvidia/nemotron-3-ultra-550b-a55b:free, minimax/minimax-m2.7:free"),
    F("LLM_TEMPERATURE", "float", 0.2, lo=0.0, hi=2.0, step=0.05,
      group="inference", label="Temperature",
      help="Low for grounded recall. Raise it only if answers feel mechanical."),
    F("LLM_MAX_TOKENS", "int", 0, lo=0, hi=200000,
      group="inference", label="Max output tokens",
      help="0 leaves it to the provider."),
    F("LLM_TIMEOUT", "float", 90.0, lo=5.0, hi=600.0,
      group="inference", label="Timeout (seconds)"),
    F("LLM_REASONING_EFFORT", "choice", "off",
      choices=["off", "low", "medium", "high"],
      group="inference", label="Reasoning effort",
      help="Only reasoning models honour this. Ignored elsewhere."),
    F("LLM_SYSTEM_PROMPT", "text", DEFAULT_SYSTEM_PROMPT,
      group="inference", label="System prompt",
      help="The instruction wrapped around every retrieval answer."),

    # -------------------------------------------------------------- gauntlet
    F("GAUNTLET_BUILDER_MODEL", "model", "",
      group="gauntlet", label="Builder model",
      help="Blank uses the main model. A strong model earns its cost here."),
    F("GAUNTLET_CRITIC_MODEL", "model", "",
      group="gauntlet", label="Critic model",
      help="Blank uses the main model. A *different* model from the builder is "
           "the point — a model grading its own output grades generously."),
    F("GAUNTLET_MAX_ROUNDS", "int", 4, lo=1, hi=12,
      group="gauntlet", label="Round ceiling",
      help="A safety stop, not the exit. The real exit is the critic picking "
           "ours blind."),
    F("GAUNTLET_TEMPERATURE", "float", 0.7, lo=0.0, hi=2.0, step=0.05,
      group="gauntlet", label="Builder temperature",
      help="Higher than Ask on purpose: the builder is generating, not reciting."),

    # ------------------------------------------------------------- retrieval
    #
    # The fusion weights below are the values tools/eval_retrieval.py measured as
    # best on this vault; the sweep found no configuration that beats them, so
    # they are left exactly as tuned. The one addition is W_TITLE, which fixed a
    # failure none of the existing knobs could reach. Re-run the sweep after the
    # vault grows substantially.
    F("TOP_K", "int", 8, lo=1, hi=40,
      group="retrieval", label="Excerpts per answer"),
    F("MAX_PER_DOC", "int", 2, lo=1, hi=10,
      group="retrieval", label="Max excerpts per note",
      help="Stops one long note monopolising the citation list."),
    F("RRF_K", "int", 20, lo=1, hi=200,
      group="retrieval", label="RRF k",
      help="Damps how much any single ranking's top hit counts. 60 is the "
           "web-scale default; a personal vault wants less."),
    F("W_KEYWORD", "float", 1.0, lo=0.0, hi=10.0, step=0.1,
      group="retrieval", label="Keyword weight"),
    F("W_SEMANTIC", "float", 2.0, lo=0.0, hi=10.0, step=0.1,
      group="retrieval", label="Semantic weight"),
    F("W_TITLE", "float", 0.08, lo=0.0, hi=1.0, step=0.01,
      group="retrieval", label="Name-match nudge",
      help="Neither BM25 nor the vectors can see a note's title, so typing a "
           "note's name was the search this was worst at. Adds a bounded bonus "
           "when the query looks like it is naming a note. On the 16-probe "
           "benchmark: 0 scores top-1 7/16, and 0.08 scores 12/16 — the smallest "
           "value that reaches the plateau. 0 disables it."),
    F("W_TITLE_EXACT", "float", 0.45, lo=0.0, hi=2.0, step=0.05,
      group="retrieval", label="Exact-name boost",
      help="Applied instead of the nudge when the query matches a note's whole "
           "name. Typing a full name is navigation, not search: you know which "
           "document you want. Kept separate because raising the nudge enough to "
           "win a navigational case over-boosts every fuzzy match too."),
    F("POOL_MULT", "int", 6, lo=1, hi=30,
      group="retrieval", label="Candidate pool multiplier",
      help="How deep each ranking goes before fusion."),

    # ------------------------------------------------------------ embeddings
    F("EMBED_ENABLED", "bool", True, reindex=True,
      group="embeddings", label="Semantic search",
      help="Off falls back to keyword-only, which is a supported mode."),
    F("EMBED_MODEL", "str", "BAAI/bge-small-en-v1.5",
      reindex=True, restart=True,
      group="embeddings", label="Embedding model",
      help="A fastembed model name. Changing it needs a full reindex and a "
           "restart, and the dimension must match."),
    F("EMBED_DIM", "int", 384, lo=32, hi=4096, reindex=True, restart=True,
      group="embeddings", label="Embedding dimension",
      help="Must match the model. bge-small is 384, bge-base is 768."),
    F("EMBED_QUERY_PREFIX", "text",
      "Represent this sentence for searching relevant passages: ",
      group="embeddings", label="Query prefix",
      help="Retrieval models are asymmetric: BGE wants this on queries only. "
           "E5 wants 'query: ' / 'passage: '. Empty disables it."),
    F("EMBED_PASSAGE_PREFIX", "text", "", reindex=True,
      group="embeddings", label="Passage prefix"),
    F("CHUNK_CHARS", "int", 1100, lo=200, hi=8000, reindex=True,
      group="embeddings", label="Chunk size (characters)"),
    F("CHUNK_OVERLAP", "int", 150, lo=0, hi=2000, reindex=True,
      group="embeddings", label="Chunk overlap"),

    # ------------------------------------------------------------- interface
    F("UI_REDUCED_MOTION", "bool", False,
      group="interface", label="Reduce motion",
      help="Stops the ambient orbit drift. Your OS preference already does this; "
           "this forces it on regardless."),
    F("UI_ORBIT_SPIN", "float", 1.0, lo=0.0, hi=3.0, step=0.1,
      group="interface", label="Orbit drift speed"),
    F("UI_LABEL_DENSITY", "choice", "balanced",
      choices=["sparse", "balanced", "dense"],
      group="interface", label="Map labels",
      help="How many note titles the map draws before it starts dropping the "
           "ones that would overlap."),
    F("REPO_URL", "url", "",
      group="interface", label="Repository URL",
      help="Set this and every note gets an 'open on GitHub' link.",
      placeholder="https://github.com/you/your-brain"),
]

BY_KEY = {f.key: f for f in SCHEMA}
GROUPS = [
    ("inference", "Inference",
     "Where answers come from, and which model writes them."),
    ("gauntlet", "Gauntlet loop",
     "Builder and critic. Keep them different models."),
    ("retrieval", "Retrieval",
     "How the two rankings get fused. Re-run the eval after changing these."),
    ("embeddings", "Embeddings",
     "Changing anything here means rebuilding the index."),
    ("interface", "Interface", "How the map behaves."),
]

_lock = threading.RLock()
_cache = None            # dict | None — the parsed store file


# ------------------------------------------------------------------ coercion

class Invalid(ValueError):
    pass


def _to_bool(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _to_csv(v):
    if isinstance(v, (list, tuple)):
        items = v
    else:
        items = str(v).split(",")
    return [str(x).strip() for x in items if str(x).strip()]


def coerce(field, raw):
    """Turn whatever arrived (env string, JSON value, form value) into the right
    type, or raise Invalid with a message a human can act on."""
    k = field.kind
    try:
        if k == "bool":
            return _to_bool(raw)
        if k == "csv":
            return _to_csv(raw)
        if k == "int":
            v = int(float(str(raw).strip()))
        elif k == "float":
            v = float(str(raw).strip())
        else:
            v = "" if raw is None else str(raw)
    except (TypeError, ValueError):
        raise Invalid("%s must be a %s" % (field.label, k))

    if k in ("int", "float"):
        if field.lo is not None and v < field.lo:
            raise Invalid("%s must be at least %s" % (field.label, field.lo))
        if field.hi is not None and v > field.hi:
            raise Invalid("%s must be at most %s" % (field.label, field.hi))
        return v

    v = v.strip() if k in ("str", "url", "secret", "model", "choice") else v
    if k == "choice" and v not in (field.choices or []):
        raise Invalid("%s must be one of: %s"
                      % (field.label, ", ".join(field.choices or [])))
    if k == "url" and v and not v.startswith(("http://", "https://")):
        raise Invalid("%s must start with http:// or https://" % field.label)
    if k == "url":
        v = v.rstrip("/")
    return v


# --------------------------------------------------------------------- store

def _load():
    global _cache
    with _lock:
        if _cache is None:
            try:
                _cache = json.loads(STORE.read_text("utf-8")) if STORE.is_file() else {}
            except (OSError, json.JSONDecodeError) as e:
                log.warning("settings store unreadable (%s) — using env defaults", e)
                _cache = {}
        return _cache


def _save(data):
    """Atomic replace. A half-written settings file would take the app down on
    the next boot, and the whole point of this file is to be editable while the
    app is running."""
    global _cache
    with _lock:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(STORE.parent), prefix=".settings-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, sort_keys=True)
                fh.write("\n")
            os.replace(tmp, STORE)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        try:
            os.chmod(STORE, 0o600)      # it holds an API key
        except OSError:
            pass
        _cache = data


def reload():
    """Drop the cache so the next read picks up an edit made on disk."""
    global _cache
    with _lock:
        _cache = None


# ---------------------------------------------------------------- public API

def _from_env(field):
    for name in (field.key,) + tuple(field.env_aliases):
        raw = os.getenv(name)
        if raw is not None and raw != "":
            try:
                return coerce(field, raw)
            except Invalid as e:
                log.warning("ignoring %s from environment: %s", name, e)
    return None


def get(key):
    field = BY_KEY.get(key)
    if field is None:
        raise KeyError(key)
    store = _load()
    if key in store:
        try:
            return coerce(field, store[key])
        except Invalid as e:
            log.warning("ignoring stored %s: %s", key, e)
    env = _from_env(field)
    return field.default if env is None else env


def source(key):
    """Where the live value came from. The UI shows this so you can tell a
    default from a deliberate choice."""
    if key in _load():
        return "saved"
    return "env" if _from_env(BY_KEY[key]) is not None else "default"


def mask(value):
    if not value:
        return ""
    s = str(value)
    return "…" + s[-4:] if len(s) > 8 else "…" + s[-2:]


def public():
    """Everything the browser needs to render the settings form. Secrets are
    reported as set/unset plus a 4-character tail, never in full."""
    values, sources, secrets = {}, {}, {}
    for f in SCHEMA:
        sources[f.key] = source(f.key)
        if f.secret:
            v = get(f.key)
            secrets[f.key] = {"set": bool(v), "hint": mask(v)}
            values[f.key] = ""
        else:
            values[f.key] = get(f.key)
    return {
        "schema": [f.as_json() for f in SCHEMA],
        "groups": [{"id": g, "label": l, "help": h} for g, l, h in GROUPS],
        "values": values,
        "sources": sources,
        "secrets": secrets,
        "store": str(STORE),
        "reindex_pending": reindex_pending(),
    }


def update(patch):
    """Validate and persist. Returns (changed_keys, errors).

    Nothing is written unless every field validates — a settings form that
    half-applies leaves you guessing which half.

    A secret sent as "" means "leave it alone", because that is what the browser
    sends back for a field it was never given the value of. Sending null clears
    it.
    """
    errors, staged = {}, {}
    for key, raw in (patch or {}).items():
        f = BY_KEY.get(key)
        if f is None:
            errors[key] = "unknown setting"
            continue
        if f.secret and raw == "":
            continue                       # untouched masked field
        if raw is None:                    # explicit clear
            staged[key] = None
            continue
        try:
            staged[key] = coerce(f, raw)
        except Invalid as e:
            errors[key] = str(e)

    if errors:
        return [], errors

    store = dict(_load())
    changed, needs_reindex = [], False
    for key, val in staged.items():
        f = BY_KEY[key]
        before = get(key)
        if val is None:
            store.pop(key, None)
        else:
            store[key] = val
        after = coerce(f, val) if val is not None else None
        if after is None:
            after = _from_env(f)
            after = f.default if after is None else after
        if after != before:
            changed.append(key)
            needs_reindex = needs_reindex or f.reindex

    if not changed:
        return [], {}

    if needs_reindex:
        store[_PENDING] = True
    _save(store)
    log.info("settings changed: %s", ", ".join(sorted(changed)))
    return changed, {}


def reset(keys=None):
    """Forget saved values and fall back to env/defaults."""
    store = dict(_load())
    targets = [k for k in (keys or list(BY_KEY)) if k in store]
    for k in targets:
        store.pop(k, None)
    if any(BY_KEY[k].reindex for k in targets if k in BY_KEY):
        store[_PENDING] = True
    _save(store)
    return targets


def reindex_pending():
    return bool(_load().get(_PENDING))


def clear_reindex_pending():
    store = dict(_load())
    if store.pop(_PENDING, None) is not None:
        _save(store)


def restart_required(changed):
    return sorted(k for k in changed if BY_KEY[k].restart)


def problems():
    """Config issues worth showing in the UI rather than failing silently."""
    out = []
    if not get("LLM_API_KEY"):
        out.append("No inference key — search works, Ask and Gauntlet will not. "
                   "Add one in Settings.")
    if get("EMBED_ENABLED") and get("EMBED_DIM") not in (384, 512, 768, 1024):
        out.append("EMBED_DIM %s is unusual — confirm it matches %s"
                   % (get("EMBED_DIM"), get("EMBED_MODEL")))
    if get("W_KEYWORD") == 0 and get("W_SEMANTIC") == 0:
        out.append("Both retrieval weights are 0 — search will return nothing.")
    if reindex_pending():
        out.append("Index is stale: an embedding setting changed. Reindex to "
                   "apply it.")
    return out


# ponytail: one runnable check, no framework. `python -m server.settings`
def _selfcheck():
    import copy
    global STORE, _cache
    original, orig_cache = STORE, copy.deepcopy(_load())
    tmpdir = tempfile.mkdtemp(prefix="agentos-settings-")
    STORE = Path(tmpdir) / "s.json"
    reload()
    try:
        assert get("TOP_K") == 8, "default not returned"
        assert source("TOP_K") == "default"

        changed, errs = update({"TOP_K": "12"})
        assert not errs and changed == ["TOP_K"], (changed, errs)
        assert get("TOP_K") == 12, "string coerced to int and persisted"
        assert source("TOP_K") == "saved"

        _, errs = update({"TOP_K": 999})
        assert "TOP_K" in errs, "range ceiling not enforced"
        assert get("TOP_K") == 12, "rejected write must not apply"

        _, errs = update({"W_KEYWORD": "nope"})
        assert "W_KEYWORD" in errs, "non-numeric accepted"

        # all-or-nothing: one bad field blocks its good sibling
        _, errs = update({"RRF_K": 30, "TOP_K": -5})
        assert "TOP_K" in errs and get("RRF_K") == 20, "partial write leaked"

        assert not reindex_pending()
        update({"CHUNK_CHARS": 900})
        assert reindex_pending(), "reindex-affecting change not flagged"
        clear_reindex_pending()
        assert not reindex_pending()

        update({"LLM_API_KEY": "sk-or-v1-abcdefghijkl"})
        assert get("LLM_API_KEY") == "sk-or-v1-abcdefghijkl"
        pub = public()
        assert pub["values"]["LLM_API_KEY"] == "", "secret leaked in values"
        assert pub["secrets"]["LLM_API_KEY"] == {"set": True, "hint": "…ijkl"}
        update({"LLM_API_KEY": ""})          # untouched field
        assert get("LLM_API_KEY") == "sk-or-v1-abcdefghijkl", "blank cleared secret"
        update({"LLM_API_KEY": None})        # explicit clear
        assert get("LLM_API_KEY") == ""

        update({"LLM_BASE_URL": "http://x.test/v1/"})
        assert get("LLM_BASE_URL") == "http://x.test/v1", "url not normalised"
        _, errs = update({"LLM_BASE_URL": "x.test"})
        assert "LLM_BASE_URL" in errs, "scheme-less url accepted"

        update({"LLM_FALLBACK_MODELS": "a/b , c/d ,"})
        assert get("LLM_FALLBACK_MODELS") == ["a/b", "c/d"], "csv not parsed"

        _, errs = update({"LLM_REASONING_EFFORT": "extreme"})
        assert "LLM_REASONING_EFFORT" in errs, "choice not constrained"

        assert reset(["TOP_K"]) == ["TOP_K"]
        assert get("TOP_K") == 8, "reset did not fall back to default"

        os.environ["TOP_K"] = "15"
        reload()
        assert get("TOP_K") == 15 and source("TOP_K") == "env", "env layer ignored"
        update({"TOP_K": 3})
        assert get("TOP_K") == 3, "saved value must beat env"
        del os.environ["TOP_K"]

        assert restart_required(["EMBED_MODEL", "TOP_K"]) == ["EMBED_MODEL"]
        print("settings selfcheck OK")
    finally:
        STORE = original
        _cache = orig_cache
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    _selfcheck()
