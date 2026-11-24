"""Hacker News via the Algolia search API: recent stories above a points threshold.

All topics are kept here; the relevance filter (M2) decides what is about AI.
"""

from __future__ import annotations

from datetime import timedelta

from quiet_ai.fetchers.base import Context, Task
from quiet_ai.store.models import Item, Metrics
from quiet_ai.text import canonical_url, clean_text, parse_iso

NAME = "hackernews"
API = "https://hn.algolia.com/api/v1/search_by_date"


def tasks(ctx: Context) -> list[Task]:
    return [Task("hackernews", NAME, lambda: fetch(ctx))]


def fetch(ctx: Context) -> list[Item]:
    hn = ctx.settings.hackernews
    since = int((ctx.now - timedelta(hours=hn.window_hours)).timestamp())
    r = ctx.http.get(
        API,
        key="hn:stories",
        params={
            "tags": "story",
            "numericFilters": f"created_at_i>{since},points>={hn.min_points}",
            "hitsPerPage": hn.max_hits,
        },
    )
    items = []
    for h in r.json().get("hits", []):
        title = clean_text(h.get("title"), ctx.settings.ingest.title_max_chars)
        if not title:
            continue
        hn_url = f"https://news.ycombinator.com/item?id={h['objectID']}"
        tags = h.get("_tags") or []
        items.append(
            Item(
                id=f"hn:{h['objectID']}",
                source="hackernews",
                kind="hn",
                url=canonical_url(h["url"]) if h.get("url") else hn_url,
                title=title,
                lang="en",
                published_at=parse_iso(h.get("created_at")),
                author=h.get("author"),
                summary=clean_text(h.get("story_text"), ctx.settings.ingest.summary_max_chars),
                metrics=Metrics(points=h.get("points"), comments=h.get("num_comments")),
                extra={"hn_url": hn_url, "show_hn": "show_hn" in tags, "ask_hn": "ask_hn" in tags},
                fetched_at=ctx.now,
            )
        )
    return items
