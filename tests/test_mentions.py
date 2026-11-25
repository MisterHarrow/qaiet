"""X posts and Reddit threads taken second-hand from a recap newsletter's links (AINews)."""

from __future__ import annotations

from datetime import datetime, timezone

from quiet_ai.config import FeedSource, load_settings
from quiet_ai.fetchers.news_rss import parse_feed
from quiet_ai.pipeline import mentions
from quiet_ai.pipeline.edition import builders_line
from quiet_ai.site import build

RECAP = """
<h1>AI Twitter Recap</h1>
<ul>
 <li><p><b>Small model release</b>: a 9B model with open weights
   (<a href="https://x.com/alice/status/111">@alice</a>, <a href="https://twitter.com/bob/status/222?s=20">@bob</a>,
   <a href="https://github.com/acme/tiny-model/tree/main">code</a>).</p>
   <ul><li><p>Benchmarks (<a href="https://x.com/carol/status/333">@carol</a>).</p></li></ul></li>
 <li><p><b>Opinion only</b> (<a href="https://x.com/dave/status/444">@dave</a>).</p></li>
</ul>
<h1>AI Reddit Recap</h1>
<ul>
 <li><p><a href="https://www.reddit.com/r/LocalLLaMA/comments/1AbC2d/tiny_model_is_out/"><b>Tiny model is out</b></a>
   (Activity: 1,838): <a href="https://huggingface.co/acme/tiny-model">acme/tiny-model</a> on
   <a href="https://latent.space/p/older-issue">an older issue</a>, <img src="x.png">
   <a href="https://acme.ai/">Acme</a>.</p></li>
 <li><p><a href="https://www.reddit.com/r/singularity/comments/9zz/self_post/"><b>A self post</b></a> (Activity: 50): no links.</p></li>
</ul>
"""


def test_extract_keeps_links_next_to_targets_only():
    blocks = mentions.extract(RECAP)
    assert len(blocks) == 2  # "Opinion only" and the self post have nothing to match on
    tw, rd = blocks
    assert tw["targets"] == ["github.com/acme/tiny-model"]  # nested bullets count with their parent
    assert tw["x"] == ["https://x.com/alice/status/111", "https://x.com/bob/status/222", "https://x.com/carol/status/333"]
    assert rd["targets"] == ["huggingface.co/acme/tiny-model"]  # the newsletter's own pages and bare domains are not targets
    assert rd["reddit"] == [{"url": "https://www.reddit.com/r/LocalLLaMA/comments/1abc2d", "sub": "LocalLLaMA",
                             "title": "Tiny model is out", "activity": 1838}]


def test_index_lookup_and_line():
    idx = mentions.Index([("ainews", b) for b in mentions.extract(RECAP)])
    found = idx.lookup({"github.com/acme/tiny-model", "huggingface.co/acme/tiny-model"}, {"ainews": "AINews"})
    assert [p["account"] for p in found["x"]] == ["alice", "bob", "carol"]
    assert found["reddit"][0]["activity"] == 1838 and found["via"] == ["AINews"]
    assert mentions.line(found) == "3 X posts, 1 Reddit thread via AINews"
    assert idx.lookup({"github.com/other/repo"}) == {"x": [], "reddit": [], "via": []}
    b = {"hn": [], "repos": [], "models": [], "papers": [], "social": 0, "digests": [], **found}
    assert builders_line(b) == "3 X posts, 1 Reddit thread via AINews"


def test_parse_feed_stores_only_links_for_mention_sources():
    feed = f"""<?xml version="1.0"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
      <item><title>[AINews] A day</title><link>https://latent.space/p/ainews-a-day</link>
      <description>Short teaser.</description><content:encoded><![CDATA[{RECAP}]]></content:encoded></item></channel></rss>"""
    now = datetime(2026, 11, 25, tzinfo=timezone.utc)
    on = FeedSource(id="ainews", name="AINews", kind="newsletter", feeds=["x"], role="digest", mentions=True)
    off = on.model_copy(update={"mentions": False})
    [item] = parse_feed(feed.encode(), on, now, load_settings().ingest)
    assert len(item.extra["mentions"]) == 2 and item.summary == "Short teaser."  # the recap's text is not stored
    assert "Opinion only" not in str(item.extra)
    [plain] = parse_feed(feed.encode(), off, now, load_settings().ingest)
    assert "mentions" not in plain.extra


def test_rising_and_panel_render_the_links(tmp_path):
    from tests.test_site import edition

    talk = {"x": [{"url": "https://x.com/alice/status/111", "account": "alice"}],
            "reddit": [{"url": "https://www.reddit.com/r/LocalLLaMA/comments/1abc2d", "sub": "LocalLLaMA", "title": "Tiny model is out", "activity": 1838}],
            "via": ["AINews"]}
    e = edition()
    e["rising"][0]["talk"] = talk
    from quiet_ai.pipeline.edition import rising_groups
    e["rising_groups"] = rising_groups(e["rising"])
    e["stories"][0]["builders"] |= talk
    html = build.render(e, tmp_path).read_text()
    assert 'Discussed on <a href="https://www.reddit.com/r/LocalLLaMA/comments/1abc2d" rel="noopener">r/LocalLLaMA</a> (1,838)' in html
    assert 'on X by <a href="https://x.com/alice/status/111" rel="noopener">@alice</a>, via AINews' in html
    assert '<span class="outlet">r/LocalLLaMA <span class="num">1,838 activity</span> <span class="country">via AINews</span></span>' in html
    assert ">Tiny model is out</a>" in html
