"""GDELT DOC 2.0 API (keyless): AI headlines from outlets with no usable feed
(wires, CNN, Chinese state media). Headline, URL and date only."""

from __future__ import annotations

from datetime import datetime, timezone

from quiet_ai.config import GdeltOutlet
from quiet_ai.fetchers.base import Context, Task
from quiet_ai.store.models import Item
from quiet_ai.text import canonical_url, clean_text, url_id

NAME = "gdelt"
API = "https://api.gdeltproject.org/api/v2/doc/doc"
_LANG = {"english": "en", "chinese": "zh", "french": "fr", "german": "de", "spanish": "es", "swedish": "sv",
         "korean": "ko", "japanese": "ja", "russian": "ru", "arabic": "ar", "portuguese": "pt", "italian": "it"}


def tasks(ctx: Context) -> list[Task]:
    if not ctx.settings.gdelt.enabled or not ctx.sources.gdelt_outlets:
        return []
    return [Task("gdelt", NAME, lambda: fetch(ctx))]


def build_query(terms: list[str], domains: list[str], lang: str | None = None) -> str:
    dom = " OR ".join(f"domain:{d}" for d in domains)
    q = f"({' OR '.join(terms)}) ({dom})" if len(domains) > 1 else f"({' OR '.join(terms)}) {dom}"
    return f"{q} sourcelang:{lang}" if lang else q


def build_queries(terms: list[str], outlets: list[GdeltOutlet], max_chars: int, lang: str | None = None) -> list[str]:
    """GDELT rejects long queries ("too short or too long"), so pack domains into several."""
    queries, group = [], []
    for d in [d for o in outlets for d in o.domains]:
        if group and len(build_query(terms, group + [d], lang)) > max_chars:
            queries.append(build_query(terms, group, lang))
            group = []
        group.append(d)
    if group:
        queries.append(build_query(terms, group, lang))
    return queries


def outlet_for(domain: str, outlets: list[GdeltOutlet]) -> GdeltOutlet | None:
    domain = domain.lower()
    for o in outlets:
        if any(domain == d or domain.endswith("." + d) for d in o.domains):
            return o
    return None


def fetch(ctx: Context) -> list[Item]:
    g = ctx.settings.gdelt
    outlets = [o for o in ctx.sources.gdelt_outlets if o.enabled]
    articles = []
    for i, query in enumerate(build_queries(g.terms, outlets, g.max_query_chars, g.source_lang)):
        r = ctx.http.get(
            API,
            key=f"gdelt:artlist:{i}",
            params={
                "query": query,
                "mode": "artlist",
                "format": "json",
                "maxrecords": g.max_records,
                "timespan": g.timespan,
                "sort": "datedesc",
            },
        )
        if not r.content.strip().startswith(b"{"):
            # GDELT answers some errors (e.g. "query too long") with 200 and a plain-text message.
            raise ValueError(r.content[:200].decode("utf-8", "replace"))
        articles += r.json().get("articles", [])
    items = []
    for a in articles:
        outlet = outlet_for(a.get("domain", ""), outlets)
        title = clean_text(a.get("title"), ctx.settings.ingest.title_max_chars)
        if not outlet or not title or not a.get("url"):
            continue
        url = canonical_url(a["url"])
        lang = _LANG.get((a.get("language") or "").lower())
        items.append(
            Item(
                id=url_id(url),
                source=outlet.id,
                kind="news",
                url=url,
                title=title,
                original_title=title if lang != "en" else None,
                lang=lang,
                published_at=_seendate(a.get("seendate")),
                extra={"via": "gdelt", "domain": a.get("domain"), "source_country": a.get("sourcecountry")},
                fetched_at=ctx.now,
            )
        )
    return items


def _seendate(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
