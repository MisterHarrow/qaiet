"""Sites with no feed but a sitemap (e.g. The Batch): new URLs from the sitemap, then
title/description/date from each page's metadata (og: tags). Page bodies are not stored."""

from __future__ import annotations

import hashlib
import html
import re
from datetime import timedelta

from quiet_ai.config import FeedSource
from quiet_ai.fetchers.base import Context, Task
from quiet_ai.store.models import Item
from quiet_ai.text import canonical_url, clean_text, parse_iso, url_id

NAME = "sitemap"
_URL = re.compile(r"<url>\s*<loc>\s*([^<\s]+)\s*</loc>(?:\s*<lastmod>\s*([^<\s]+)\s*</lastmod>)?", re.S)
_META = re.compile(r"<meta\s+[^>]*>", re.I)
_ATTR = re.compile(r"""(\w[\w:-]*)\s*=\s*["']([^"']*)["']""")


def tasks(ctx: Context) -> list[Task]:
    return [Task(src.id, NAME, lambda src=src: fetch(ctx, src)) for src in ctx.sources.feeds if src.enabled and src.sitemap]


def recent_urls(body: str, src: FeedSource, ctx: Context) -> list[str]:
    include = re.compile(src.sitemap_include) if src.sitemap_include else None
    cutoff = ctx.now - timedelta(days=ctx.settings.ingest.max_age_days)
    found = []
    for loc, lastmod in _URL.findall(body):
        when = parse_iso(lastmod)
        if (include and not include.search(loc)) or not when or when < cutoff:
            continue
        found.append((when, loc))
    found.sort(reverse=True)
    return [loc for _, loc in found[: src.sitemap_max_pages]]


def page_meta(page: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for tag in _META.findall(page):
        attrs = {k.lower(): html.unescape(v) for k, v in _ATTR.findall(tag)}
        key = attrs.get("property") or attrs.get("name")
        if key and "content" in attrs:
            out.setdefault(key.lower(), attrs["content"])
    if "og:title" not in out and (m := re.search(r"<title>(.*?)</title>", page, re.S | re.I)):
        out["og:title"] = html.unescape(m.group(1))
    return out


def fetch(ctx: Context, src: FeedSource) -> list[Item]:
    sm = ctx.http.get(src.sitemap, key=f"sitemap:{src.id}")
    items = []
    for loc in recent_urls(sm.content.decode("utf-8", "replace"), src, ctx):
        url = canonical_url(loc)
        if url in ctx.known_urls:
            continue
        key = f"sitemap:{src.id}:page:{hashlib.sha1(url.encode()).hexdigest()[:12]}"
        meta = page_meta(ctx.http.get(loc, key=key).content.decode("utf-8", "replace"))
        title = clean_text(meta.get("og:title"), ctx.settings.ingest.title_max_chars)
        if not title:
            continue
        extra = {"role": src.role} if src.role else {}
        items.append(
            Item(
                id=url_id(url),
                source=src.id,
                kind=src.kind,
                url=url,
                title=title,
                lang=src.language,
                published_at=parse_iso(meta.get("article:published_time")),
                summary=clean_text(meta.get("og:description") or meta.get("description"), ctx.settings.ingest.summary_max_chars),
                extra=extra,
                fetched_at=ctx.now,
            )
        )
    return items
