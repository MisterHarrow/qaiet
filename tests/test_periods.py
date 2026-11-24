from __future__ import annotations

import json
from datetime import timedelta

from quiet_ai.config import FeedSource, PeriodSettings, SourcesConfig
from quiet_ai.pipeline import cluster, edition, embed, momentum
from quiet_ai.site import build
from quiet_ai.store.db import Store, iso
from quiet_ai.store.models import Item
from tests.conftest import NOW

EMB = embed.HashEmbedder()
SOURCES = SourcesConfig(feeds=[FeedSource(id=s, name=s.upper(), kind="news", feeds=["x"], country="US") for s in ("nyt", "ft", "bbc")])
DAY = PeriodSettings(key="day", label="24 hours", hours=24, half_life_hours=36)
WEEK = PeriodSettings(key="week", label="7 days", hours=168, half_life_hours=96, merge=True)


def add(st, items, at):
    st.upsert_items(items, at)
    with st.conn:
        st.conn.execute("UPDATE items SET relevant = 1, relevance_by = 'test' WHERE relevant IS NULL")
        for it in items:
            st.conn.execute(
                "INSERT INTO item_labels(item_id, task, prompt_version, model, stance, confidence, data, created_at) "
                "VALUES (?, 'news', 'v', 'm', 0, 'high', ?, ?)",
                (it.id, json.dumps({"entities": ["Nvidia", "Jensen Huang"]}), iso(at)),
            )
    embed.embed_pending(st, EMB, iso(at - timedelta(days=30)), 300, at)


def news(i, source, title, at):
    return Item(id=f"n{i}", source=source, kind="news", url=f"https://e.com/{i}", title=title, published_at=at, fetched_at=at)


def recurring_story(settings):
    """The same topic five days apart: two separate stories, since the first went quiet for >72h."""
    st = Store(":memory:")
    settings.cluster.join_threshold = settings.cluster.confident_threshold = 0.5
    early = NOW - timedelta(days=5)
    add(st, [news(1, "nyt", "Nvidia board reinstates Jensen Huang as chief executive", early),
             news(2, "ft", "Nvidia board reinstates Jensen Huang as chief executive again", early)], early)
    cluster.run(st, EMB.name, settings.cluster, early)
    add(st, [news(3, "bbc", "Nvidia board reinstates Jensen Huang as chief executive officer", NOW)], NOW)
    cluster.run(st, EMB.name, settings.cluster, NOW)
    return st


def test_two_stories_are_one_in_the_week_view_only(settings):
    st = recurring_story(settings)
    ids = {r[0] for r in st.conn.execute("SELECT DISTINCT story_id FROM items")}
    assert len(ids) == 2

    day = momentum.score_stories(st, settings, SOURCES, NOW, DAY)
    assert len(day) == 1 and day[0].features["outlets"] == 1  # only today's item counts

    week = momentum.score_stories(st, settings, SOURCES, NOW, WEEK)
    assert len(week) == 1 and week[0].story_id.endswith("@week") and sorted(week[0].members) == sorted(ids)
    assert week[0].features["outlets"] == 3

    entry = edition.story_entry(st, SOURCES, week[0], 1)
    assert entry["items"] == 3 and entry["outlets"] == 3


def test_partial_coverage_note_and_period_meta(settings):
    st = recurring_story(settings)  # first item seen 5 days ago
    # Collection started 5 days ago; with a day of feed backlog that covers 6 days.
    assert edition.build(st, settings, SOURCES, [], [], NOW, 12, DAY)["data_since"] is None
    ed_week = edition.build(st, settings, SOURCES, [], [], NOW, 12, WEEK)
    assert ed_week["period"] == {"key": "week", "label": "7 days", "hours": 168}
    assert ed_week["data_since"] == iso(NOW - timedelta(days=5))


def test_render_all_writes_one_page_per_view_with_relative_paths(tmp_path, settings):
    st = recurring_story(settings)
    eds = [edition.build(st, settings, SOURCES, momentum.score_stories(st, settings, SOURCES, NOW, p), [], NOW, 12, p) for p in (DAY, WEEK)]
    pages = build.render_all(eds, tmp_path)
    assert [p.relative_to(tmp_path).as_posix() for p in pages] == ["index.html", "week/index.html"]
    week_html = (tmp_path / "week" / "index.html").read_text()
    assert 'href="../static/style.css"' in week_html and '<a href="../">24 hours</a>' in week_html
    assert '<a href="../week/" aria-current="page">7 days</a>' in week_html
    front = (tmp_path / "index.html").read_text()
    assert '<a href="./" aria-current="page">24 hours</a>' in front and '<a href="week/">7 days</a>' in front
    assert (tmp_path / "week" / "edition.json").exists() and (tmp_path / "static" / "style.css").exists()
