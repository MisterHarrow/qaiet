from __future__ import annotations

from datetime import timedelta

from quiet_ai.config import ClusterSettings, SourcesConfig
from quiet_ai.pipeline import cluster, embed, stories
from quiet_ai.pipeline.cluster import norm_key
from quiet_ai.store.db import Store, iso
from quiet_ai.store.models import Item, Metrics
from tests.conftest import NOW

EMB = embed.HashEmbedder()
CFG = ClusterSettings(join_threshold=0.5, strict_join_threshold=0.9, merge_threshold=0.9)


def add(store, items, now=NOW):
    for it in items:
        it.published_at = it.published_at or now
    store.upsert_items(items, now)
    with store.conn:
        store.conn.execute("UPDATE items SET relevant = 1, relevance_by = 'test' WHERE relevant IS NULL")
    embed.embed_pending(store, EMB, iso(now - timedelta(days=3)), 300, now)


def news(i, title, source="nyt", url=None, **kw):
    return Item(id=f"n{i}", source=source, kind="news", url=url or f"https://news.example/{i}", title=title, fetched_at=NOW, **kw)


def story_of(store, item_id):
    return store.conn.execute("SELECT story_id FROM items WHERE id = ?", (item_id,)).fetchone()[0]


def test_norm_key():
    assert norm_key("https://github.com/Org/Repo/tree/main/x") == "github.com/org/repo"
    assert norm_key("https://github.com/") is None
    assert norm_key("https://huggingface.co/papers/2611.01234") == "arxiv:2611.01234"
    assert norm_key("https://arxiv.org/abs/2611.01234v2") == "arxiv:2611.01234"
    assert norm_key("https://huggingface.co/Org/Model-7B") == "huggingface.co/org/model-7b"
    assert norm_key("https://www.ft.com/content/abc?utm_source=x") == "ft.com/content/abc"
    assert norm_key("https://example.com/") is None


def test_non_latin_headlines_wait_for_their_english_title():
    """Untranslated Japanese or Arabic headlines aren't embedded (so not clustered); once translated, the English title
    is embedded alone, without the untranslated summary."""
    st = Store(":memory:")
    add(st, [news(1, "エヌビディア、フアン氏をCEOに復帰", lang="ja", summary="長い日本語の要約"),
             news(2, "Nvidia brings back Huang", lang="en"), news(3, "Nvidia ger Huang jobbet igen", lang="sv")])
    embedded = {r[0] for r in st.conn.execute("SELECT item_id FROM embeddings")}
    assert embedded == {"n2", "n3"}  # Swedish is Latin script: close enough untranslated
    with st.conn:
        st.conn.execute("UPDATE items SET title_en = 'Nvidia returns Huang as CEO' WHERE id = 'n1'")
    assert embed.embed_pending(st, EMB, iso(NOW - timedelta(days=3)), 300, NOW) == 1
    assert embed.item_text("エヌビディア", "Nvidia returns Huang", "日本語の要約", 300, "ja") == "Nvidia returns Huang"
    assert embed.item_text("Nvidia ger", "Nvidia gives", "Svensk text", 300, "sv") == "Nvidia gives. Svensk text"


def test_similar_headlines_form_one_story_with_stable_id():
    st = Store(":memory:")
    add(st, [news(1, "Nvidia board reinstates Jensen Huang as chief executive"),
             news(2, "Nvidia board reinstates Jensen Huang as chief executive officer", source="ft"),
             news(3, "Local bakery wins national bread award", source="bbc")])
    cluster.run(st, EMB.name, CFG, NOW)
    s1 = story_of(st, "n1")
    assert s1 == cluster.story_id_for("n1") and story_of(st, "n2") == s1 and story_of(st, "n3") != s1

    # A later run adds a new item to the same story; existing assignments don't move.
    later = NOW + timedelta(hours=2)
    add(st, [news(4, "Nvidia board reinstates Jensen Huang as chief executive, shares jump", source="wsj")], now=later)
    stats = cluster.run(st, EMB.name, CFG, later)
    assert stats.placed == 1 and story_of(st, "n4") == s1 and story_of(st, "n1") == s1
    assert st.conn.execute("SELECT item_count FROM stories WHERE id = ?", (s1,)).fetchone()[0] == 3


def test_links_join_across_kinds():
    st = Store(":memory:")
    add(st, [news(1, "Lab releases open model", url="https://ex.com/story")])
    hn = Item(id="hn:1", source="hackernews", kind="hn", url="https://ex.com/story", title="Totally different words here",
              extra={"hn_url": "https://news.ycombinator.com/item?id=1"}, fetched_at=NOW)
    post = Item(id="bsky:1", source="bluesky", kind="social", url="https://bsky.app/profile/a/post/1", title="look",
                extra={"links": ["https://github.com/org/model"]}, fetched_at=NOW)
    repo = Item(id="github:org/model", source="github", kind="repo", url="https://github.com/org/model", title="org/model",
                metrics=Metrics(stars=10), fetched_at=NOW)
    add(st, [hn, post, repo], now=NOW + timedelta(minutes=5))
    stats = cluster.run(st, EMB.name, CFG, NOW + timedelta(minutes=5))
    assert story_of(st, "hn:1") == story_of(st, "n1")
    assert story_of(st, "bsky:1") == story_of(st, "github:org/model")
    assert stats.by_link >= 2


def test_strict_kinds_need_high_similarity():
    st = Store(":memory:")
    add(st, [news(1, "Agent framework for building AI agents released")])
    repo = Item(id="github:a/b", source="github", kind="repo", url="https://github.com/a/b", title="a/b",
                summary="framework for building AI agents", fetched_at=NOW)
    add(st, [repo])
    cluster.run(st, EMB.name, CFG, NOW)
    assert story_of(st, "github:a/b") != story_of(st, "n1")


def test_active_view_counts_outlets():
    st = Store(":memory:")
    add(st, [news(1, "Nvidia board reinstates Jensen Huang as chief executive"),
             news(2, "Nvidia board reinstates Jensen Huang as chief executive officer", source="ft")])
    cluster.run(st, EMB.name, CFG, NOW)
    views = stories.active(st, SourcesConfig(feeds=[]), NOW, 72)
    assert len(views) == 1 and views[0].outlets == ["ft", "nyt"] and views[0].items == 2
