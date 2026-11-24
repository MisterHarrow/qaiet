"""The normalized Item every fetcher produces."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ItemKind = Literal[
    "news",        # news outlet article (RSS or GDELT)
    "aggregator",  # Techmeme / Memeorandum lead story
    "newsletter",  # digest or commentary post
    "lab",         # official lab blog post
    "launch",      # Product Hunt launch
    "repo",        # GitHub repository
    "model",       # Hugging Face or OpenRouter model
    "dataset",
    "space",
    "paper",
    "hn",          # Hacker News story
    "social",      # Bluesky post or Hugging Face post
]


class Metrics(BaseModel):
    stars: int | None = None
    likes: int | None = None
    points: int | None = None
    comments: int | None = None
    reposts: int | None = None
    downloads: int | None = None
    trending_score: float | None = None

    def nonempty(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class Item(BaseModel):
    id: str
    source: str
    kind: ItemKind
    url: str
    title: str
    original_title: str | None = None  # set for non-English items; title becomes the translation (M2)
    lang: str | None = None
    published_at: datetime | None = None
    author: str | None = None
    summary: str | None = None
    metrics: Metrics = Field(default_factory=Metrics)
    extra: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime

    @property
    def content_hash(self) -> str:
        """Hash of the text an LLM would see; the classification cache key."""
        text = "\x1f".join([self.kind, self.original_title or self.title, self.summary or ""])
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
