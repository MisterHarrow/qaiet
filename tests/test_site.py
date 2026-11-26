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
    assert json.loads((tmp_path / "vercel.json").read_text()) == {"trailingSlash": True}  # relative links need /archive/
    # The host serves 404.html for any missing address, at any depth: its links are absolute.
    missing = (tmp_path / "404.html").read_text()
    assert "This page doesn't exist" in missing and 'href="/static/style.css"' in missing and 'href="/archive/"' in missing
    assert '<span class="wm">Qaiet Times</span>' in missing and 'name="robots" content="noindex"' in missing


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
    # Limits: outlets per region, and the two-week wait for outlets in a new language
    regions = dict((r["name"], r["n"]) for r in ctx["regions"])
    assert regions["Latin America"] == sum(1 for f in sources.feeds if f.kind == "news" and f.enabled and f.group == "latam")
    assert f"North America {regions['North America']}, Latin America {regions['Latin America']}, Europe" in html
    assert ctx["waiting"]["until"] == "10 December" and "join the index two weeks later (" in html
    assert ctx["us_share"] is None  # no labels in this store
    assert 'Daily Sabah <span class="country">TR, state-aligned</span>' in html  # state media are marked in the list
    assert "<h3>Canada</h3>" in html and "<h3>Middle East</h3>" in html and "<h3>Southeast Asia</h3>" in html and "Americas" not in html
    assert "<img" not in html and not re.search(r'<script[^>]*src="(?!\.\./static/app\.js")', html)  # only our own script


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
    for p in pages:  # light by default: a saved dark choice is applied before paint; the switch needs JS
        assert 'localStorage.getItem("theme")==="dark"' in p.split("</head>")[0]
        assert '<button type="button" class="theme-toggle" aria-pressed="false" hidden>' in p and "static/app.js" in p
    assert '<a href="./" aria-current="page">Today</a>' in front
    assert '<a href="../archive/" aria-current="page">Archive</a>' in archive
    # The masthead rule is the stance mix of every article in the view; each card's top edge is its own.
    assert '<p class="spectrum" role="img" aria-label="Stance of every article in this view: 1 critical, 2 neutral, 1 positive, 1 not labeled"' in front
    assert '<p class="stripe" role="img"' in front and '<span class="rank">01</span>' in front


def test_card_stripe_counts_each_outlet_once(tmp_path):
    """One outlet filing five critical articles on a story counts once in the stripe; the stance chart still counts articles."""
    from quiet_ai.pipeline.edition import outlet_stances

    def m(src, stance, confidence="high", label=True):
        return {"source": src, "stance": stance, "confidence": confidence, "label": {} if label else None}

    press = [*(m("loud", -2) for _ in range(5)), m("a", 0), m("b", 1), m("b", 0), m("c", 2, "low"), m("d", None, label=False)]
    got = outlet_stances(press)
    assert (got["-2"], got["0"], got["1"], got["unclear"], got["unlabeled"]) == (1, 2, 0, 1, 1)  # b: mean 0.5 rounds to 0
    e = edition()
    e["stories"][0]["stance_outlets"] = {"-2": 1, "-1": 0, "0": 2, "1": 0, "2": 0, "unclear": 1, "unlabeled": 1}
    card = re.search(r'<article class="card".*?</article>', build.render(e, tmp_path).read_text(), re.S).group(0)
    assert '<p class="stripe" role="img" aria-label="Stance by outlet: 1 strongly critical, 2 neutral, 1 unclear, 1 not labeled"' in card
    assert "Stance of the coverage: 1 critical, 2 neutral, 1 positive, 1 not labeled. Average" in card  # the chart: articles


def test_card_links_its_top_source(tmp_path, settings):
    """A small browser icon on each card opens the top source: an official post first, else an English original."""
    from datetime import timedelta

    from quiet_ai.config import FeedSource
    from quiet_ai.config import SourcesConfig as SC
    from quiet_ai.pipeline import cluster, edition as ed, momentum
    from quiet_ai.store.db import Store
    from quiet_ai.store.models import Item
    from tests.conftest import NOW
    from tests.test_cluster import CFG, EMB, add, news

    st = Store(":memory:")
    add(st, [news(1, "Acme releases tiny open model", source="dn", url="https://dn.se/a", lang="sv"),
             news(2, "Acme releases tiny open model today", source="nyt", url="https://nyt.com/a", lang="en")])
    cluster.run(st, EMB.name, CFG, NOW)
    srcs = SC(feeds=[FeedSource(id="dn", name="DN", kind="news", feeds=["x"], language="sv"), FeedSource(id="nyt", name="NYT", kind="news", feeds=["x"]),
                     FeedSource(id="acme", name="Acme blog", kind="lab", feeds=["x"])])
    [score] = momentum.score_stories(st, settings, srcs, NOW + timedelta(minutes=1))
    assert ed.story_entry(st, srcs, score, 1)["source"]["outlet"] == "NYT"  # the English original over the Swedish one
    lab = Item(id="lab:1", source="acme", kind="lab", url="https://acme.ai/blog/tiny", title="Introducing tiny", fetched_at=NOW,
               extra={"links": ["https://nyt.com/a"]})
    add(st, [lab], now=NOW + timedelta(minutes=2))
    cluster.run(st, EMB.name, CFG, NOW + timedelta(minutes=2))
    [score] = momentum.score_stories(st, settings, srcs, NOW + timedelta(minutes=3))
    entry = ed.story_entry(st, srcs, score, 1)
    assert entry["source"] == {"outlet": "Acme blog", "url": "https://acme.ai/blog/tiny", "title": "Introducing tiny", "official": True}

    e = edition()
    e["stories"][0]["source"] = entry["source"]
    html = build.render(e, tmp_path).read_text()
    assert '<a class="open-source" href="https://acme.ai/blog/tiny" rel="noopener" aria-label="Open the top source, Acme blog (official)">' in html
    assert '<span class="open-source-label" aria-hidden="true">Top source</span>' in html and '<g class="globe">' in html
    assert ">Expand Sources</summary>" in html


def test_card_footer_has_stance_chart_and_builders_line_moves_to_panel(tmp_path):
    html = build.render(edition(), tmp_path).read_text()
    card = re.search(r'<article class="card".*?</article>', html, re.S).group(0)
    panel = re.search(r'<div class="panel".*?<div class="panel-groups">', html, re.S).group(0)
    assert 'class="builders"' not in card and "HN 1,200 points, 5 comments" in panel
    # stance {-1: 1, 0: 2, 1: 1}: average 0, bars scaled to the largest bucket
    assert 'aria-label="Stance of the coverage: 1 critical, 2 neutral, 1 positive, 1 not labeled. Average +0.00 on a scale from −2 to +2."' in card
    assert '<rect class="sb3" x="25" y="1.0" width="8" height="22.0" rx="0.8"/>' in card and '<rect class="sb1" x="1" y="23" width="8" height="0" rx="0.8"/>' in card
    assert card.count('<g class="sface">') == 5 and 'tabindex="0"' in card
    # the hover tooltip: counts per stance and the average
    assert "Stance of 4 articles" in card  # labeled ones; unclear would count too and '<span class="tip-row"><i class="tip-dot st0"></i>Neutral<b>2</b></span>' in card
    assert '<span class="tip-avg">Average<b>+0.00</b></span>' in card


def test_panel_shows_countries_per_stance_and_a_plain_url_list(tmp_path):
    e = edition()
    e["stories"][0]["coverage"][0]["countries"] = [["US", 3], ["SE", 1]]
    e["stories"][0]["coverage"][0]["items"][0]["track"] = "technical"
    html = build.render(e, tmp_path).read_text()
    panel = re.search(r'<div class="panel".*?</div>\n</div>', html, re.S).group(0)
    assert '<p class="group-countries" aria-label="Countries: United States 3, Sweden 1">' in panel
    assert '<span title="United States: 3 outlets">US <b>3</b></span><span title="Sweden: 1 outlet">SE</span>' in panel
    # the corner toggle and the plain list: every URL with stance, angle, frame, outlet and country
    assert '<details class="raw-toggle">' in panel and "Every source, as labeled" in panel
    assert 'Neutral<span class="sep">·</span>technical<span class="sep">·</span>grounded<span class="sep">·</span>NYT (US)' in panel
    assert '<a class="raw-url" href="https://e.com/a" rel="noopener">https://e.com/a</a>' in panel


def test_countries_per_stance_group():
    from quiet_ai.pipeline.edition import _countries
    items = [{"country": "US"}, {"country": "SE"}, {"country": "US"}, {"country": None}, {"country": "GB"}]
    assert _countries(items) == [["US", 2], ["GB", 1], ["SE", 1]]


def test_builders_line_and_summary_link_their_sources():
    b = {"hn": [{"title": "t", "url": "https://news.ycombinator.com/item?id=1", "points": 1200, "comments": 5}],
         "repos": [], "models": [], "papers": [], "social": 2, "official": [],
         "posts": [{"url": "https://bsky.app/profile/a/post/1", "title": "p", "source": "Bluesky"}],
         "digests": ["The Rundown AI"], "digest_links": {"The Rundown AI": "https://therundown.ai/a"},
         "x": [{"url": "https://x.com/alice/status/1", "account": "alice"}], "reddit": [],
         "via": ["AINews"], "via_links": {"AINews": "https://latent.space/p/ainews-a"}}
    html = str(build.builders_html(b))
    assert html == ('<a href="https://news.ycombinator.com/item?id=1" rel="noopener">HN 1,200 points, 5 comments</a> · '
                    '<a href="https://bsky.app/profile/a/post/1" rel="noopener">2 posts</a> · '
                    'in <a href="https://therundown.ai/a" rel="noopener">The Rundown AI</a> · '
                    '<a href="https://x.com/alice/status/1" rel="noopener">1 X post</a> via '
                    '<a href="https://latent.space/p/ainews-a" rel="noopener">AINews</a>')
    # Older editions without the links keep plain text.
    assert str(build.builders_html({"hn": [], "social": 3, "digests": ["TLDR AI"]})) == "3 posts · in TLDR AI"
    text = "Hacker News & Bluesky users argued; Hacker News again, and on X <b>too</b>."
    linked = str(build.link_platforms(text, b))
    assert linked.startswith('<a href="https://news.ycombinator.com/item?id=1" rel="noopener">Hacker News</a> &amp; '
                             '<a href="https://bsky.app/profile/a/post/1" rel="noopener">Bluesky</a> users argued; Hacker News again')
    assert 'on <a href="https://x.com/alice/status/1" rel="noopener">X</a> &lt;b&gt;too&lt;/b&gt;.' in linked  # text stays escaped


def test_coverage_map_lights_up_the_outlets_countries(tmp_path):
    stories = [{"coverage": [{"items": [{"outlet": "NYT", "country": "US"}, {"outlet": "DN", "country": "SE"},
                                       {"outlet": "NYT", "country": "US"}, {"outlet": "?", "country": None}]}]},
               {"coverage": [{"items": [{"outlet": "WSJ", "country": "US"}]}]}]
    geo = build.coverage_map(stories)
    assert geo["outlets"] == 3 and geo["countries"] == [["US", 2], ["SE", 1]]  # one per outlet
    assert [(r["name"], r["n"]) for r in geo["regions"]] == [("North America", 2), ("Latin America", 0), ("Europe", 1), ("Middle East", 0), ("Africa", 0),
                                                              ("East Asia", 0), ("South Asia", 0), ("Southeast Asia", 0), ("Oceania", 0)]
    svg = str(geo["svg"])
    assert svg.startswith('<svg class="geo-map" viewBox="0 0 170 70" width="170" height="70"') and 'class="geo-land"' in svg
    assert svg.count('<circle class="lit') > 4 and "--d:" in svg
    assert build.coverage_map([{"coverage": []}]) is None
    html = build.render(edition(), tmp_path).read_text()
    assert '<p class="geo-head">Outlet coverage</p>\n  <div class="geo" tabindex="0" role="img" aria-label="Where the coverage in this view comes from. 2 outlets in 1 country: United States 2.">' in html


def test_stories_filter_by_region_and_country(tmp_path):
    us_se = {"coverage": [{"items": [{"outlet": "NYT", "country": "SE"}, {"outlet": "WSJ", "country": "US"}, {"outlet": "?", "country": None}]}]}
    gb_ca = {"coverage": [{"items": [{"outlet": "BBC", "country": "GB"}, {"outlet": "CBC", "country": "CA"}, {"outlet": "G", "country": "GB"}]}]}
    builders_only = {"coverage": []}
    assert build.story_countries(us_se) == ["US", "SE"] and build.story_countries(builders_only) == []  # legend order
    places = build.place_filters([us_se, gb_ca, builders_only])
    assert [(r["name"], r["n"]) for r in places] == [("North America", 2), ("Latin America", 0), ("Europe", 2), ("Middle East", 0),
                                                     ("Africa", 0), ("East Asia", 0), ("South Asia", 0), ("Southeast Asia", 0),
                                                     ("Oceania", 0)]
    assert [(c["code"], c["n"]) for c in places[2]["countries"]] == [("GB", 1), ("SE", 1)]  # stories per country, only those with any
    assert places[2]["codes"] == ["GB", "SE", "DE", "FR", "BE", "ES"]
    assert build.place_filters([builders_only]) == []

    html = build.render(edition(), tmp_path).read_text()
    assert 'data-countries="US"' in html  # each card says where its outlets are
    assert '<nav class="filters places" aria-label="Filter stories by where their outlets are" hidden>' in html  # app.js shows it
    assert '<button type="button" data-region="North America" data-codes="US CA" aria-pressed="false">North America <span class="n">1</span></button>' in html
    assert 'data-region="Latin America" data-codes="MX CO PE BR CL AR" aria-pressed="false" disabled>' in html
    assert 'data-region="Europe" data-codes="GB SE DE FR BE ES" aria-pressed="false" disabled>' in html
    assert '<span class="place-row"' not in html  # one country in the view: no country line to pick from


def test_card_lists_framings_with_their_outlets(tmp_path):
    story = {"summary": {"coverage": "Prose.", "frames": [
        {"frame": "frame the return as a governance failure.", "outlets": ["Breitbart", "the guardian", "Nobody Times"]},
        {"frame": "Report it plainly", "outlets": ["NYT"]}, {"frame": " ", "outlets": ["NYT"]}]},
        "coverage": [{"stance": "-2", "items": [{"outlet": "Breitbart", "country": "US", "url": "https://b/1", "title": "B1"},
                                                {"outlet": "The Guardian", "country": "GB", "url": "https://g/1", "title": "G1"},
                                                {"outlet": "Breitbart", "country": "US", "url": "https://b/2", "title": "B2"}]},
                     {"stance": "0", "items": [{"outlet": "NYT", "country": "US", "url": "https://n/1", "title": "N1"}]}]}
    rows = build.frame_rows(story)
    assert [r["frame"] for r in rows] == ["Frame the return as a governance failure", "Report it plainly"]  # tidied, blank dropped
    assert rows[0]["outlets"] == 2 and rows[0]["countries"] == ["US", "GB"]  # names matched without case; unknown names dropped
    assert [(c["title"], c["stance"]) for c in rows[0]["items"]] == [("B1", "-2"), ("B2", "-2"), ("G1", "-2")]  # every article of those outlets
    assert build.frame_rows({"summary": {"coverage": "Prose."}, "coverage": []}) == []  # before story_summary_v4: prose

    e = edition()
    e["stories"][0]["summary"]["frames"] = [{"frame": "Report the return plainly", "outlets": ["NYT"]}]
    html = build.render(e, tmp_path).read_text()
    assert '<ul class="frames" aria-label="How the outlets frame it">' in html and '<p class="coverage">' not in html
    assert '<li class="fr-row"><span class="fr-text">Report the return plainly</span> <span class="fr-who" tabindex="0" aria-label="1 outlet in United States: show their headlines">' in html
    assert '<span class="fr-cc">US</span>' in html and '<span class="fr-tip">' in html
