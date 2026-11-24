from __future__ import annotations

from quiet_ai.config import FeedSource, IngestSettings
from quiet_ai.fetchers.news_rss import parse_feed
from tests.conftest import FIXTURES, NOW

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>T</title>
<item><title>OpenAI ships &lt;b&gt;thing&lt;/b&gt;</title><link>https://ex.com/a?utm_source=rss</link>
<description><![CDATA[<p>Short summary.</p>]]></description><pubDate>Mon, 23 Nov 2026 10:00:00 GMT</pubDate></item>
<item><title>[AINews] Daily recap</title><link>https://ex.com/b</link></item>
<item><title>No link</title></item>
</channel></rss>"""

RDF_NO_DATES = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/">
<channel rdf:about="x"><title>N</title><items><rdf:Seq><rdf:li resource="https://n.com/1"/></rdf:Seq></items></channel>
<item rdf:about="https://n.com/1"><title>Chips story</title><link>https://n.com/1</link></item>
</rdf:RDF>"""


def src(**kw) -> FeedSource:
    return FeedSource(**{"id": "t", "name": "T", "kind": "news", "feeds": ["x"], **kw})


def test_parse_rss_basic():
    items = parse_feed(RSS, src(), NOW, IngestSettings())
    assert [i.title for i in items] == ["OpenAI ships thing", "[AINews] Daily recap"]
    a = items[0]
    assert a.url == "https://ex.com/a"
    assert a.summary == "Short summary."
    assert a.published_at.isoformat() == "2026-11-23T10:00:00+00:00"
    assert a.original_title is None and a.lang == "en"


def test_include_title_filter():
    items = parse_feed(RSS, src(include_title=r"^\[AINews\]"), NOW, IngestSettings())
    assert [i.title for i in items] == ["[AINews] Daily recap"]


def test_non_english_keeps_original_title():
    items = parse_feed(RSS, src(language="sv"), NOW, IngestSettings())
    assert items[0].original_title == items[0].title and items[0].lang == "sv"


def test_rdf_without_dates():
    items = parse_feed(RDF_NO_DATES, src(), NOW, IngestSettings())
    assert len(items) == 1 and items[0].published_at is None


def test_newsletter_role_is_kept():
    items = parse_feed(RSS, src(kind="newsletter", role="digest"), NOW, IngestSettings())
    assert items[0].kind == "newsletter" and items[0].extra["role"] == "digest"


def test_techmeme_lead_outlet_and_url():
    body = (FIXTURES / "rss_techmeme_0.xml").read_bytes()
    items = parse_feed(body, src(id="techmeme", kind="aggregator"), NOW, IngestSettings())
    assert items
    with_lead = [i for i in items if i.extra.get("lead_outlet")]
    assert len(with_lead) >= len(items) - 1
    for i in with_lead:
        assert "techmeme.com" not in i.extra.get("lead_url", "")
    assert any(i.extra.get("lead_url", "").startswith("https://") for i in items)
