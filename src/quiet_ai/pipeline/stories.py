"""Read stories back out for display."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from quiet_ai.config import SourcesConfig
from quiet_ai.pipeline.cluster import EVENT_AT
from quiet_ai.pipeline.embed import from_blob, normalize
from quiet_ai.store.db import Store, iso

BUILDER_SOURCES = {
    "github": "GitHub", "hackernews": "Hacker News", "bluesky": "Bluesky", "openrouter": "OpenRouter",
    "hf_models": "Hugging Face", "hf_datasets": "Hugging Face", "hf_spaces": "Hugging Face",
    "hf_papers": "HF Papers", "hf_posts": "HF Posts",
}
# Which member's headline represents the story: press first, then the rest.
_KIND_RANK = {"news": 0, "aggregator": 1, "newsletter": 2, "lab": 3, "hn": 4, "paper": 5, "social": 6, "launch": 7, "recap": 8}


@dataclass
class StoryView:
    id: str
    title: str
    items: int
    outlets: list[str]          # distinct news outlets
    sources: list[str]          # every distinct source name
    kinds: Counter = field(default_factory=Counter)
    countries: set[str] = field(default_factory=set)
    first_at: str = ""
    last_at: str = ""


def _rep_key(r, centroid):
    sim = float(from_blob(r["vector"]) @ centroid) if centroid is not None and r["vector"] else 0.0
    english = bool(r["title_en"]) or (r["lang"] or "en") == "en"
    return (_KIND_RANK.get(r["kind"], 9), not english, -sim)


def representative_title(store: Store, story_id: str) -> str | None:
    """Headline of the press item closest to the story's centroid, English preferred."""
    rows = store.conn.execute(
        "SELECT i.kind, i.lang, i.title, i.title_en, e.vector, s.centroid FROM items i JOIN stories s ON s.id = i.story_id "
        "LEFT JOIN embeddings e ON e.item_id = i.id WHERE i.story_id = ?",
        (story_id,),
    ).fetchall()
    if not rows:
        return None
    centroid = normalize(from_blob(rows[0]["centroid"])[None, :])[0] if rows[0]["centroid"] else None
    rep = min(rows, key=lambda r: _rep_key(r, centroid))
    return rep["title_en"] or rep["title"]


def representative_url(store: Store, story_id: str, kinds: tuple[str, ...] = ("news",)) -> str | None:
    """URL of the item of these kinds closest to the story's centroid, an English original first: the card's source link."""
    rows = store.conn.execute(
        f"SELECT i.kind, i.lang, i.url, i.title_en, e.vector, s.centroid FROM items i JOIN stories s ON s.id = i.story_id "
        f"LEFT JOIN embeddings e ON e.item_id = i.id WHERE i.story_id = ? AND i.relevant = 1 AND i.dup_of IS NULL "
        f"AND i.kind IN ({','.join('?' * len(kinds))})",
        (story_id, *kinds),
    ).fetchall()
    if not rows:
        return None
    centroid = normalize(from_blob(rows[0]["centroid"])[None, :])[0] if rows[0]["centroid"] else None
    return min(rows, key=lambda r: ((r["lang"] or "en") != "en", _rep_key(r, centroid)))["url"]


def source_names(sources: SourcesConfig) -> dict[str, str]:
    names = dict(BUILDER_SOURCES)
    names.update({f.id: f.name for f in sources.feeds})
    names.update({g.id: g.name for g in sources.gdelt_outlets})
    return names


def active(store: Store, sources: SourcesConfig, now: datetime, window_hours: int) -> list[StoryView]:
    since = iso(now - timedelta(hours=window_hours))
    names = source_names(sources)
    countries = {f.id: f.country for f in sources.feeds} | {g.id: g.country for g in sources.gdelt_outlets}
    rows = store.conn.execute(
        f"SELECT i.story_id, i.source, i.kind, i.lang, i.title, i.title_en, {EVENT_AT} AS event_at, e.vector, s.centroid "
        "FROM items i JOIN stories s ON s.id = i.story_id LEFT JOIN embeddings e ON e.item_id = i.id "
        "WHERE s.merged_into IS NULL AND s.last_item_at >= ?",
        (since,),
    ).fetchall()
    grouped: dict[str, list] = {}
    for r in rows:
        grouped.setdefault(r["story_id"], []).append(r)
    views = []
    for sid, members in grouped.items():
        centroid = normalize(from_blob(members[0]["centroid"])[None, :])[0] if members[0]["centroid"] else None

        rep = min(members, key=lambda r: _rep_key(r, centroid))
        news = [r for r in members if r["kind"] == "news"]
        views.append(StoryView(
            id=sid,
            title=rep["title_en"] or rep["title"],
            items=len(members),
            outlets=sorted({names.get(r["source"], r["source"]) for r in news}),
            sources=sorted({names.get(r["source"], r["source"]) for r in members}),
            kinds=Counter(r["kind"] for r in members),
            countries={countries[r["source"]] for r in news if countries.get(r["source"])},
            first_at=min(r["event_at"] for r in members),
            last_at=max(r["event_at"] for r in members),
        ))
    # M2 ordering; M3 replaces this with the momentum score.
    views.sort(key=lambda v: (len(v.outlets), len(v.sources), v.items, v.last_at), reverse=True)
    return views

