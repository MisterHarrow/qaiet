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
        content = (e.get("content") or [{}])[0].get("value", "") if src.mentions else ""
        if src.mentions:  # only links and counts are kept on the issue, never the recap's text
            found = mentions.extract(content)
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
                # dict.get: feedparser warns (deprecated fallback) when an undated entry is asked for updated_parsed
                published_at=from_struct(e.get("published_parsed") or dict.get(e, "updated_parsed")),
                author=clean_text(e.get("author"), 120),
                summary=summary,
                extra=extra,
                fetched_at=now,
            )
        )
        if src.mentions:
            items += _recap_items(content, src, url, items[-1].published_at, now, cfg)
    return items


def _recap_items(content: str, src: FeedSource, issue_url: str, published: datetime | None, now: datetime, cfg: IngestSettings) -> list[Item]:
    """One small item per X bullet of a recap: its bold lead and a short summary, the posts it links, its other URLs."""
    out = []
    for b in mentions.x_bullets(content):
        text = clean_text(b["text"], cfg.summary_max_chars)
        title = clean_text((b["lead"] or "").strip().rstrip(":"), cfg.title_max_chars) or clean_text(b["text"], 120)
        if not title:
            continue
        out.append(Item(
            id=url_id(b["x"][0]), source=src.id, kind="recap", url=b["x"][0], title=title, lang=src.language,
            published_at=published, summary=text if text != title else None, metrics={"posts": len(b["x"])},
            extra={"x": b["x"], "links": b["urls"], "issue": issue_url}, fetched_at=now,
        ))
    return out


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
