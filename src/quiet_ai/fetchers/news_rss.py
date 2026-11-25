"""RSS/Atom feeds: news outlets, aggregators, newsletters, lab blogs, Product Hunt."""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlsplit

import feedparser

from quiet_ai.config import FeedSource, IngestSettings
from quiet_ai.fetchers.base import Context, Task
from quiet_ai.pipeline import mentions
from quiet_ai.store.models import Item
from quiet_ai.text import canonical_url, clean_text, from_struct, url_id

NAME = "news_rss"
_AGGREGATOR_HOSTS = ("techmeme.com", "memeorandum.com", "mediagazer.com")
_HREF = re.compile(r"""href=["']([^"']+)["']""", re.I)
# "Author / Outlet: headline" or "Outlet: headline"
_BYLINE = re.compile(r"^(?:(?P<author>[^/:]{2,80}?)\s*/\s*)?(?P<outlet>[^:]{2,80}?):\s")


def tasks(ctx: Context) -> list[Task]:
    return [
        Task(src.id, NAME, lambda src=src: fetch_source(ctx, src))
        for src in ctx.sources.feeds
        if src.enabled and src.feeds
    ]


def fetch_source(ctx: Context, src: FeedSource) -> tuple[list[Item], str]:
    items: list[Item] = []
    not_modified = 0
    for i, url in enumerate(src.feeds):
        r = ctx.http.get(url, key=f"rss:{src.id}:{i}", conditional=True)
        if r.not_modified:
            not_modified += 1
            continue
        items += parse_feed(r.content, src, ctx.now, ctx.settings.ingest)
    status = "not_modified" if not_modified == len(src.feeds) else "ok"
    return items, status


def parse_feed(body: bytes, src: FeedSource, now: datetime, cfg: IngestSettings) -> list[Item]:
    parsed = feedparser.parse(body)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"unparseable feed: {parsed.get('bozo_exception')}")
    include = re.compile(src.include_title) if src.include_title else None
    items = []
    for e in parsed.entries:
        link = e.get("link") or (e.get("id") if str(e.get("id", "")).startswith("http") else None)
        title = clean_text(e.get("title"), cfg.title_max_chars)
        if not link or not title:
            continue
        if include and not include.search(title):
            continue
        summary = clean_text(e.get("summary") or e.get("description"), cfg.summary_max_chars)
        if summary == title:
            summary = None
        extra: dict = {}
        if src.kind == "aggregator":
            extra = _aggregator_extra(e)
        if src.role:
            extra["role"] = src.role
        if src.mentions:  # only links and counts are kept, never the recap's text
            found = mentions.extract((e.get("content") or [{}])[0].get("value", ""))
            if found:
                extra["mentions"] = found
        url = canonical_url(link)
        items.append(
            Item(
                id=url_id(url),
                source=src.id,
                kind=src.kind,
                url=url,
                title=title,
                original_title=title if src.language != "en" else None,
                lang=src.language,
                published_at=from_struct(e.get("published_parsed") or e.get("updated_parsed")),
                author=clean_text(e.get("author"), 120),
                summary=summary,
                extra=extra,
                fetched_at=now,
            )
        )
    return items


def _aggregator_extra(entry) -> dict:
    """Techmeme/Memeorandum: who broke the story, and the link to their article."""
    raw = entry.get("summary") or ""
    out: dict = {}
    m = _BYLINE.match(clean_text(raw) or "")
    if m:
        out["lead_outlet"] = m.group("outlet").strip()
        if m.group("author"):
            out["lead_author"] = m.group("author").strip()
    for href in _HREF.findall(raw):
        parts = urlsplit(href)
        if not parts.netloc or any(parts.netloc.endswith(h) for h in _AGGREGATOR_HOSTS):
            continue
        if parts.path in ("", "/") or re.search(r"\.(png|jpe?g|gif|webp)$", parts.path, re.I):
            continue
        out["lead_url"] = canonical_url(href)
        break
    return out
