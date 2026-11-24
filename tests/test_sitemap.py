from __future__ import annotations

from quiet_ai.config import FeedSource, load_sources
from quiet_ai.fetchers import sitemap
from tests.conftest import make_ctx

SITEMAP = """<?xml version="1.0"?><urlset>
<url><loc>https://ex.com/the-batch/new-thing</loc><lastmod>2026-11-23T08:00:00.000-08:00</lastmod></url>
<url><loc>https://ex.com/the-batch/tag/agents</loc><lastmod>2026-11-23T08:00:00.000-08:00</lastmod></url>
<url><loc>https://ex.com/the-batch/older-thing</loc><lastmod>2026-11-20T08:00:00Z</lastmod></url>
<url><loc>https://ex.com/the-batch/ancient</loc><lastmod>2025-01-01T00:00:00Z</lastmod></url>
<url><loc>https://ex.com/about</loc><lastmod>2026-11-23T00:00:00Z</lastmod></url>
</urlset>"""

SRC = FeedSource(id="b", name="B", kind="newsletter", role="digest", sitemap="https://ex.com/sitemap.xml",
                 sitemap_include=r"^https://ex\.com/the-batch/(?!tag/)[^/]+$")


def test_recent_urls_filters_and_orders(settings):
    ctx = make_ctx(settings, None)
    assert sitemap.recent_urls(SITEMAP, SRC, ctx) == ["https://ex.com/the-batch/new-thing", "https://ex.com/the-batch/older-thing"]
    one = SRC.model_copy(update={"sitemap_max_pages": 1})
    assert sitemap.recent_urls(SITEMAP, one, ctx) == ["https://ex.com/the-batch/new-thing"]


def test_page_meta_reads_og_tags():
    page = ('<html><head><title>Fallback</title><meta property="og:title" content="Real &amp; title"/>'
            '<meta content="Desc" property="og:description"><meta property="article:published_time" content="2026-11-20T08:15:00Z">')
    meta = sitemap.page_meta(page)
    assert meta["og:title"] == "Real & title" and meta["og:description"] == "Desc"
    assert sitemap.page_meta("<title>Only title</title>")["og:title"] == "Only title"


def test_known_urls_are_not_refetched(replay_ctx):
    src = next(f for f in load_sources().feeds if f.id == "thebatch")
    first = sitemap.fetch(replay_ctx, src)
    assert first and all(i.kind == "newsletter" and i.extra["role"] == "digest" for i in first)
    replay_ctx.known_urls = {i.url for i in first}
    assert sitemap.fetch(replay_ctx, src) == []
