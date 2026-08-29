"""Local CPU embeddings, loaded lazily and allowed to be absent.

Absence is a first-class case. If the model or its runtime is missing, search
degrades to keyword-only rather than the app failing to start — a vault you can
search by keyword beats a 500 page. `status()` reports which mode is live so the
UI can say so out loud instead of quietly returning worse results.
"""
import logging
import threading
from typing import List, Optional

from . import config

log = logging.getLogger("agentos.embed")

_model = None
_state = "cold"          # cold | ready | disabled | failed:<reason>
_lock = threading.Lock()


def _load():
    global _model, _state
    if not config.EMBED_ENABLED:
        _state = "disabled"
        return None
    try:
        from fastembed import TextEmbedding
    except ImportError:
        _state = "failed:fastembed not installed"
        log.warning("fastembed missing — keyword-only search")
        return None
    try:
        # fastembed ships quantised ONNX weights and runs on CPU. No torch.
        m = TextEmbedding(model_name=config.EMBED_MODEL)
        _state = "ready"
        log.info("embeddings ready: %s", config.EMBED_MODEL)
        return m
    except Exception as e:                      # noqa: BLE001 - report, don't crash
        _state = "failed:%s" % e
        log.warning("embedding model failed to load: %s", e)
        return None


def available() -> bool:
    global _model
    if _state == "cold":
        with _lock:
            if _state == "cold":
                _model = _load()
    return _model is not None


def status() -> dict:
    return {"model": config.EMBED_MODEL, "dim": config.EMBED_DIM,
            "state": _state, "available": _model is not None}


def encode(texts: List[str]) -> Optional[List[List[float]]]:
    """Embed passages (documents) for indexing, or None if unavailable."""
    if not texts or not available():
        return None
    pre = config.EMBED_PASSAGE_PREFIX
    try:
        batch = [pre + t for t in texts] if pre else texts
        return [list(map(float, v)) for v in _model.embed(batch)]
    except Exception as e:                      # noqa: BLE001
        log.warning("embed failed: %s", e)
        return None


def encode_query(text: str) -> Optional[List[float]]:
    """Embed a *query*, which is not the same operation as embedding a passage.

    Retrieval-tuned models (BGE, E5) are trained asymmetrically: the query side
    gets an instruction prefix the passage side must not have. Embedding a
    question as though it were a document degrades recall on exactly the
    paraphrased queries semantic search exists to win.

    Note: fastembed's own query_embed() was measured to be a no-op for this model
    (an identical vector to embed(), cosine 1.0000), so the prefix is applied here
    explicitly rather than trusted to the library.
    """
    if not text or not available():
        return None
    try:
        vecs = list(_model.embed([config.EMBED_QUERY_PREFIX + text]))
        return list(map(float, vecs[0])) if vecs else None
    except Exception as e:                      # noqa: BLE001
        log.warning("query embed failed: %s", e)
        return None


def encode_one(text: str) -> Optional[List[float]]:
    out = encode([text])
    return out[0] if out else None


def warm():
    """Touch the model at startup so the first user query isn't the one that
    pays the load cost."""
    if available():
        encode_query("warmup")
