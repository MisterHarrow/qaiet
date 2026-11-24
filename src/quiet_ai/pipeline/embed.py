"""Sentence embeddings for relevant items (local ONNX model via fastembed)."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from typing import Protocol

import numpy as np

from quiet_ai.config import ROOT, EmbedSettings
from quiet_ai.store.db import Store, iso


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


class FastEmbedder:
    def __init__(self, cfg: EmbedSettings):
        from fastembed import TextEmbedding

        self.name = cfg.model
        self._model = TextEmbedding(model_name=cfg.model, cache_dir=str(ROOT / cfg.cache_dir))

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        return normalize(np.array(list(self._model.embed(texts, batch_size=64)), dtype=np.float32))


class HashEmbedder:
    """Deterministic bag-of-words vectors. For tests and --dry-run without the model."""

    name = "hash-384"
    _TOKEN = re.compile(r"[a-z0-9]+")

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), 384), dtype=np.float32)
        for row, text in enumerate(texts):
            toks = self._TOKEN.findall(text.lower())
            for tok in toks + [a + "_" + b for a, b in zip(toks, toks[1:])]:
                h = int(hashlib.md5(tok.encode()).hexdigest()[:8], 16)
                out[row, h % 384] += 1.0 if h & 1 else -1.0
        return normalize(out)


def normalize(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


def to_blob(v: np.ndarray) -> bytes:
    return np.asarray(v, dtype=np.float32).tobytes()


def from_blob(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)


def item_text(title: str, title_en: str | None, summary: str | None, summary_chars: int) -> str:
    text = title_en or title
    if summary:
        text += ". " + summary[:summary_chars]
    return text


def embed_pending(store: Store, embedder: Embedder, since_iso: str, summary_chars: int, now: datetime) -> int:
    """Embed relevant, non-duplicate items in the window that have no vector from this model."""
    rows = store.conn.execute(
        "SELECT i.id, i.title, i.title_en, i.summary FROM items i LEFT JOIN embeddings e ON e.item_id = i.id AND e.model = ? "
        "WHERE i.relevant = 1 AND i.dup_of IS NULL AND e.item_id IS NULL AND i.first_seen_at >= ?",
        (embedder.name, since_iso),
    ).fetchall()
    if not rows:
        return 0
    vectors = embedder.embed([item_text(r["title"], r["title_en"], r["summary"], summary_chars) for r in rows])
    with store.conn:
        store.conn.executemany(
            "INSERT OR REPLACE INTO embeddings(item_id, model, vector, created_at) VALUES (?, ?, ?, ?)",
            [(r["id"], embedder.name, to_blob(v), iso(now)) for r, v in zip(rows, vectors)],
        )
    return len(rows)


def prune(store: Store, now: datetime, keep_days: int) -> int:
    cutoff = iso(now - timedelta(days=keep_days))
    with store.conn:
        cur = store.conn.execute("DELETE FROM embeddings WHERE created_at < ?", (cutoff,))
    return cur.rowcount
