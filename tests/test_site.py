from __future__ import annotations

import json
import re

from typer.testing import CliRunner

from quiet_ai.cli import app
from quiet_ai.pipeline.edition import stance_summary
from quiet_ai.site import build


def edition(**over):
    story = {
        "id": "s-1", "rank": 1, "momentum": 0.5, "features": {}, "headline": "Lab <script>alert(1)</script> ships model",
        "track": "technical", "summary": {"headline": "x", "coverage": "Coverage is uniform.", "builders": None},
        "outlets": 2, "countries": 1, "stance": {"-2": 0, "-1": 1, "0": 2, "1": 1, "2": 0, "unclear": 0, "unlabeled": 1},
        "stance_summary": "mostly neutral",
        "coverage": [{"stance": "0", "items": [{"outlet": "NYT", "country": "US", "kind": "news", "lang": "sv", "title": "Original rubrik",
                                                 "title_en": "Original headline", "url": "https://e.com/a", "frame": "grounded",
                                                 "evidence": ["ships model"], "rationale": "plain", "llm_opt_out": False}]},
                     {"stance": "unlabeled", "items": [{"outlet": "The Atlantic", "country": "US", "kind": "news", "lang": "en", "title": "T",
                                                         "title_en": None, "url": "https://e.com/b", "frame": None, "evidence": [],
                                                         "rationale": None, "llm_opt_out": True}]}],
        "builders": {"hn": [{"title": "HN", "url": "https://news.ycombinator.com/item?id=1", "points": 1200, "comments": 5}],
                     "repos": [], "models": [], "papers": [], "social": 0, "official": [], "digests": []},
        "builders_line": "HN 1,200 points, 5 comments", "items": 5, "entities": ["Nvidia"], "terms": ["nvidia"],
    }
    e = {"generated_at": "2026-11-24T09:00:00+00:00", "weather": "Quiet day.", "stories": [story], "terms_hours": 24,
         "terms": [{"key": "nvidia", "label": "Nvidia", "outlets": 12, "size": 4, "stories": 1}],
         "rising": [{"id": "r", "kind": "repo", "category": "agent", "title": "o/r", "url": "https://github.com/o/r", "signal": "+10 stars/day", "what": "w", "why": "y", "story_id": None}],
         "llm": {"month_spend_usd": 0.1, "budget_usd": 30, "budget_reached": False}}
    from quiet_ai.pipeline.edition import rising_groups
    e["rising_groups"] = rising_groups(e["rising"])
    e.update(over)
    return e


def test_render_is_escaped_local_and_complete(tmp_path):
    page = build.render(edition(), tmp_path)
    html = page.read_text()
    assert "<script>alert" not in html and "&lt;script&gt;" in html
    assert "Tuesday 24 November 2026" in html and "updated 10:00 Stockholm" in html  # UTC 09:00 -> CET 10:00
    # The page itself loads nothing from other hosts: only local CSS/JS, an inline favicon, no images.
    for tag in re.findall(r"<(?:link|script|img)[^>]*>", html):
        assert "://" not in tag.replace("http://www.w3.org/2000/svg", ""), tag
    assert "<img" not in html
    assert (tmp_path / "static" / "style.css").exists() and (tmp_path / "static" / "app.js").exists()
    assert json.loads((tmp_path / "edition.json").read_text())["weather"] == "Quiet day."
    # Translated headline shows English, keeps the original on hover; opted-out publisher is marked.
    assert 'title="Original rubrik" lang="sv">Original headline' in html and "translated from sv" in html
    assert "publisher opts out of AI processing" in html
    assert '<nav class="filters" aria-label="Filter stories by track" hidden>' in html  # shown only by JS
    assert 'class="card" id="s-1" data-track="technical" data-terms="nvidia"' in html
    assert 'data-term="nvidia"' in html and "mentioned by 12 outlets" in html and "Most mentioned" in html
    assert 'data-track="technical" aria-pressed="false">Technical <span class="n">1</span>' in html
    assert '<p class="empty" hidden>' in html
    assert "1,200 points" in html


def test_budget_notice(tmp_path):
    html = build.render(edition(llm={"month_spend_usd": 30, "budget_usd": 30, "budget_reached": True}), tmp_path).read_text()
    assert "budget for machine labeling is used up" in html


def test_stance_segments_and_summary():
    segs = build.stance_segments({"-2": 0, "-1": 1, "0": 2, "1": 1, "2": 0, "unclear": 0, "unlabeled": 4})
    assert [s["key"] for s in segs] == ["-1", "0", "1"] and abs(sum(s["pct"] for s in segs) - 100) < 0.1
    assert build.stance_segments({"unlabeled": 3}) == []
    assert stance_summary({"-2": 0, "-1": 3, "0": 4, "1": 3, "2": 0}) == "split"
    assert stance_summary({"-2": 2, "-1": 3, "0": 1, "1": 0, "2": 0}) == "leans critical"
    assert stance_summary({"0": 0}) is None


def test_cli_build_dry_run(tmp_path):
    res = CliRunner().invoke(app, ["build", "--dry-run", "--out", str(tmp_path)])
    assert res.exit_code == 0, res.output
    html = (tmp_path / "index.html").read_text()
    assert html.count("<article") >= 1 and "Rising" in html


def test_top_terms_merge_variants_and_count_outlets(settings):
    from datetime import datetime, timezone
    import json as _json
    from quiet_ai.config import FeedSource, SourcesConfig
    from quiet_ai.pipeline.edition import top_terms
    from quiet_ai.store.db import Store
    from quiet_ai.store.models import Item

    now = datetime(2026, 11, 24, 9, tzinfo=timezone.utc)
    st = Store(":memory:")
    labels = {"a": ("nyt", ["Donald Trump", "Nvidia Corp.", "AI", "CNBC"]), "b": ("nyt", ["Trump", "Nvidia"]),
              "c": ("ft", ["Trump administration", "Nvidia's"]), "d": ("bbc", ["Nvidia"])}
    st.upsert_items([Item(id=k, source=v[0], kind="news", url=f"https://e.com/{k}", title=k, fetched_at=now) for k, v in labels.items()], now)
    with st.conn:
        st.conn.execute("UPDATE items SET relevant = 1")
        for k, (_, ents) in labels.items():
            st.conn.execute("INSERT INTO item_labels(item_id, task, prompt_version, model, data, created_at) VALUES (?, 'news', 'v', 'm', ?, ?)",
                            (k, _json.dumps({"entities": ents}), now.isoformat()))
    srcs = SourcesConfig(feeds=[FeedSource(id=i, name=n, kind="news", feeds=["x"]) for i, n in (("nyt", "NYT"), ("ft", "FT"), ("bbc", "BBC"), ("cnbc", "CNBC"))])
    terms = {t["key"]: t for t in top_terms(st, srcs, settings, now)}
    assert terms["nvidia"]["outlets"] == 3 and terms["nvidia"]["label"] == "Nvidia"   # nyt twice counts once
    assert terms["trump"]["outlets"] == 2 and terms["trump"]["label"] == "Trump"       # aliases merged
    assert "ai" not in terms and "cnbc" not in terms                                     # stopword, outlet name
    assert terms["nvidia"]["size"] == 4


def test_rising_grouped_by_category(tmp_path):
    from quiet_ai.pipeline.edition import rising_groups
    entries = [{"category": c, "title": t} for c, t in [("research paper", "p1"), ("agent", "a1"), ("model", "m1"), ("agent", "a2")]]
    groups = rising_groups(entries)
    assert [(g["label"], [i["title"] for i in g["items"]]) for g in groups] == [("Models", ["m1"]), ("Agents", ["a1", "a2"]), ("Papers", ["p1"])]
    assert groups[2]["slug"] == "research-paper"
    html = build.render(edition(), tmp_path).read_text()
    assert '<div class="rgroup" data-category="agent">' in html and 'data-category="agent" aria-pressed="false">Agents <span class="n">1</span>' in html
    assert '<nav class="filters rising-filters" aria-label="Filter rising projects by category" hidden>' in html


def test_about_page_reads_config_and_health(tmp_path, settings):
    from datetime import datetime, timezone
    from quiet_ai.config import load_accounts, load_sources
    from quiet_ai.site.about import about_context
    from quiet_ai.store.db import Store

    now = datetime(2026, 11, 24, 9, tzinfo=timezone.utc)
    st = Store(":memory:")
    run = st.start_run("ingest", False, now)
    st.record_source_run(run, "nyt", "news_rss", "ok", 200, 10, 2, None, 0.1)
    st.record_source_run(run, "cbc", "news_rss", "robots_blocked", None, 0, 0, "robots.txt unreachable", 0.1)
    sources = load_sources()
    ctx = about_context(st, settings, sources, load_accounts(), now)
    assert ctx["counts"]["outlets"] == sum(1 for f in sources.feeds if f.kind == "news" and f.enabled)
    assert ctx["health"]["ok"] == 1 and ctx["health"]["failing"][0]["name"] == "CBC"
    assert sum(w["weight"] for w in ctx["weights"]) == 100
    html = build.render_about(ctx, tmp_path).read_text()
    assert 'href="../static/style.css"' in html and "How this site works" in html
    assert f"{ctx['counts']['outlets']} news outlets" in html and "1 of 2 sources answered normally" in html
    assert "CBC: robots blocked" in html and settings.analysis.news_prompt in html
    assert "<script" not in html and "<img" not in html


def test_brand_is_the_same_on_every_page(tmp_path):
    """The Qaiet Times wordmark, favicon and navigation come from one partial, so every page carries identical copies."""
    e = edition()
    front = build.render(e, tmp_path).read_text()
    e2 = edition()
    e2["frozen"] = {"date": "2026-11-24", "at": "2026-11-25T00:17:00+00:00"}
    archive = build.render_archive([e2], tmp_path).read_text()
    index = build.render_sentiment({"all": [{"date": "2026-11-25", "value": 0.1, "outlets": 22, "labels": 90}]}, tmp_path).read_text()
    pages = [front, archive, index]
    icons = {re.search(r'<link rel="icon" href="([^"]+)">', p).group(1) for p in pages}
    assert len(icons) == 1 and next(iter(icons)).startswith("data:image/svg+xml,")
    for p in pages:
        assert '<span class="wm">Qaiet Times</span>' in p and 'class="sitenav"' in p
        assert "Qaiet Times" in p.split("</title>")[0] and "quiet ai" not in p
    assert '<a href="./" aria-current="page">Today</a>' in front
    assert '<a href="../archive/" aria-current="page">Archive</a>' in archive
    # The masthead rule is the stance mix of every article in the view; each card's top edge is its own.
    assert '<p class="spectrum" role="img" aria-label="Stance of every article in this view: 1 critical, 2 neutral, 1 positive, 1 not labeled"' in front
    assert '<p class="stripe" role="img"' in front and '<span class="rank">01</span>' in front
