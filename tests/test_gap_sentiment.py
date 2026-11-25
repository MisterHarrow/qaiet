from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from quiet_ai.pipeline import gap, sentiment
from quiet_ai.pipeline.momentum import StoryScore
from quiet_ai.site import build
from quiet_ai.store.db import Store, iso
from quiet_ai.store.models import Item
from tests.test_site import edition

NOW = datetime(2026, 11, 26, 8, tzinfo=timezone.utc)


def score(sid, **features):
    return StoryScore(story_id=sid, score=features.pop("score", 0.5), features=features, last_at=iso(NOW))


def test_gap_picks_both_sides(settings, monkeypatch):
    monkeypatch.setattr(gap, "story_entry", lambda store, sources, s, n: {
        "id": s.story_id, "headline": s.story_id, "track": "technical", "outlets": int(s.features.get("outlets", 0)), "countries": 1,
        "stance_summary": None, "builders_line": "", "builders": {"hn": [], "repos": [{"url": f"https://github.com/{s.story_id}"}], "models": [], "papers": []}})
    scores = [
        score("repo-hot", outlets=0, star_velocity=900),          # builders only, strong: left list
        score("repo-weak", outlets=0, star_velocity=20),          # builders only but tiny: neither
        score("social-only", outlets=0, social=500),              # Bluesky alone doesn't count as builders
        score("press-big", outlets=9),                            # press only: right list
        score("press-and-hn", outlets=8, hn_points=400),          # both: neither
        *[score(f"filler-{i}", outlets=2, hn_points=10 * i) for i in range(6)],
    ]
    out = gap.compute(None, settings, None, scores)
    assert [g["id"] for g in out["builders_not_press"]] == ["repo-hot"]
    assert out["builders_not_press"][0]["link"] == "https://github.com/repo-hot"
    assert [g["id"] for g in out["press_not_builders"]] == ["press-big"]


def labeled(st, i, source, track, stance, confidence="high", at=NOW):
    st.upsert_items([Item(id=f"n{i}", source=source, kind="news", url=f"https://e.com/{i}", title=f"AI {i}",
                          published_at=at, fetched_at=at)], at)
    with st.conn:
        st.conn.execute("UPDATE items SET relevant = 1 WHERE id = ?", (f"n{i}",))
        st.conn.execute("INSERT INTO item_labels (item_id, task, prompt_version, model, track, stance, confidence, data, created_at) "
                        "VALUES (?, 'news', 'v', 'm', ?, ?, ?, '{}', ?)", (f"n{i}", track, stance, confidence, iso(at)))


def test_sentiment_is_outlet_balanced_and_confidence_weighted(settings):
    st = Store(":memory:")
    labeled(st, 0, "early", "technical", 2, at=NOW - timedelta(days=1))  # collection starts the day before
    for i in range(10):  # one prolific outlet, all critical
        labeled(st, i + 1, "loud", "political", -2)
    labeled(st, 20, "a", "political", 1)
    labeled(st, 21, "b", "political", 1)
    labeled(st, 22, "b", "political", -2, confidence="low")   # unclear: left out
    labeled(st, 23, "c", "technical", 0, confidence="medium")
    settings.sentiment.min_outlets = 3
    sentiment.compute(st, settings, NOW)
    h = sentiment.history(st)
    today = NOW.date().isoformat()
    all_today = next(p for p in h["all"] if p["date"] == today)
    # loud -2, a +1, b +1, c 0: four voices, mean -0.0 -> loud doesn't dominate
    assert all_today["value"] == 0.0 and all_today["outlets"] == 4 and all_today["labels"] == 13
    pol = next(p for p in h["political"] if p["date"] == today)
    assert pol["value"] == 0.0 and pol["outlets"] == 3
    assert not h["technical"] or all(p["date"] != today for p in h["technical"])  # 1 outlet today: below min_outlets
    assert sentiment.describe(-0.6) == "critical" and sentiment.describe(0.05) == "neutral" and sentiment.describe(0.3) == "leaning positive"
    assert sentiment.period_value({"all": [{"value": 1.0}, {"value": 0.0}, {"value": -0.5}]}, 2) == {"all": -0.25}


def test_sentiment_page_and_front_page_line(tmp_path):
    hist = {"all": [{"date": "2026-11-24", "value": -0.3, "outlets": 20, "labels": 80},
                    {"date": "2026-11-25", "value": 0.1, "outlets": 22, "labels": 90}],
            "technical": [{"date": "2026-11-25", "value": 0.4, "outlets": 9, "labels": 30}], "political": [], "economic": []}
    html = build.render_sentiment(hist, tmp_path).read_text()
    assert "Wednesday 25 November 2026" in html and "+0.10" in html and "neutral" in html
    assert html.count('<svg class="spark"') == 2 and "No political values yet." in html
    assert "Regulation, policy, geopolitics, chips and export controls, elections and courts." in html  # what each track covers
    assert '<p class="chart-note">Every labeled article, whatever its angle.</p>' in html
    assert "<title>2026-11-24: −0.30 (20 outlets, 80 labels)</title>" in html
    assert "<table" in html and "://" not in html.replace("http://www.w3.org/2000/svg", "").split("<body>")[0].split("<link")[0]

    e = edition(sentiment={"values": {"all": -0.28, "technical": 0.1, "political": -0.6, "economic": None},
                           "words": "leaning critical", "days": 7, "latest": None, "outlets": 30},
                gap={"builders_not_press": [{"id": "s-2", "headline": "fast-anything", "track": "technical", "outlets": 0, "countries": 0,
                                             "stance_summary": None, "builders_line": "+900 stars/day", "link": "https://github.com/o/f"}],
                     "press_not_builders": []})
    page = build.render(e, tmp_path / "site").read_text()
    assert '<a class="sent-label step" href="sentiment/">The sentiment</a>' in page
    assert '<span class="sent-num step" data-value="-0.28">−0.28</span>' in page and "7-day average" in page
    assert "Political <b>−0.60</b>" in page and "Economic <b>–</b>" in page
    assert "The gap" in page and "fast-anything" in page and "no outlet coverage" in page
    assert "No big press story without builder interest." in page
    assert json.loads((tmp_path / "site" / "edition.json").read_text())["gap"]["builders_not_press"][0]["id"] == "s-2"
