from __future__ import annotations

import json
import re

import pytest
from datetime import timedelta
from types import SimpleNamespace

from typer.testing import CliRunner

from quiet_ai.cli import app
from quiet_ai.config import FeedSource, LLMSettings, ModelPrice, SourcesConfig
from quiet_ai.llm.client import LLM
from quiet_ai.pipeline import classify, cluster, edition, embed, momentum, summarize
from quiet_ai.pipeline.process import run_analysis
from quiet_ai.store.db import Store, iso
from quiet_ai.store.models import Item, Metrics
from tests.conftest import NOW

EMB = embed.HashEmbedder()
SOURCES = SourcesConfig(feeds=[
    FeedSource(id="nyt", name="NYT", kind="news", feeds=["x"], country="US"),
    FeedSource(id="ft", name="FT", kind="news", feeds=["x"], country="GB"),
    FeedSource(id="atlantic", name="The Atlantic", kind="news", feeds=["x"], country="US", llm=False),
    FeedSource(id="tldr", name="TLDR AI", kind="newsletter", feeds=["x"], role="digest"),
])


class FakeAnthropic:
    """Answers each structured-output type with something plausible; records every call."""

    def __init__(self):
        self.calls = []
        self.messages = SimpleNamespace(parse=self._parse)
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def _parse(self, **kw):
        self.calls.append(kw)
        fmt = kw["output_format"]
        user = kw["messages"][0]["content"]
        nums = [int(n) for n in re.findall(r"^\[(\d+)\]", user, re.M)]
        name = fmt.__name__
        if name == "NewsBatch":
            items = []
            for n in nums:
                line = next(l for l in user.splitlines() if l.startswith(f"[{n}]"))
                headline = re.search(r"headline: (.*?)( \(English|\s\|\s|$)", line).group(1)
                items.append({"i": n, "track": "economic", "track2": "economic", "frame": "bubble" if "bubble" in line else "boom",
                              "stance": -1 if "bubble" in line else 0, "evidence": [" ".join(headline.split()[:4]), "words that are not there"],
                              "rationale": "r", "confidence": "high", "entities": ["Nvidia", "Nvidia", " "]})
            data = {"items": items}
        elif name == "BuilderBatch":
            data = {"items": [{"i": n, "what": f"thing {n}", "why": "because", "kind": "tool/library"} for n in nums]}
        elif name == "StorySummary":
            data = {"headline": "Nvidia reinstates its chief executive", "track": "economic", "coverage": "Mostly neutral.", "builders": None}
        else:
            data = {"sentence": "Market-heavy day; builders shipped agent tools."}
        usage = SimpleNamespace(input_tokens=500, output_tokens=100, cache_read_input_tokens=0, cache_creation_input_tokens=0)
        return SimpleNamespace(parsed_output=fmt.model_validate(data), usage=usage, stop_reason="end_turn", model=kw["model"])


def make_llm(store, client):
    prices = {"claude-haiku-5-5": ModelPrice(input=0.1, output=0.5), "claude-sonnet-5-5": ModelPrice(input=2, output=10)}
    return LLM(LLMSettings(prices=prices), store, "run", client=client)


def news(i, source, title, **kw):
    return Item(id=f"n{i}", source=source, kind="news", url=f"https://e.com/{i}", title=title, published_at=NOW, fetched_at=NOW, **kw)


def seeded_store(settings):
    st = Store(":memory:")
    items = [
        news(1, "nyt", "Nvidia board reinstates Jensen Huang as chief executive"),
        news(2, "ft", "Nvidia board reinstates Jensen Huang as chief executive amid bubble fears"),
        news(3, "atlantic", "Nvidia board reinstates Jensen Huang as chief executive, again"),
        Item(id="t1", source="tldr", kind="newsletter", url="https://e.com/t1", title="Nvidia board reinstates Jensen Huang as chief executive (TLDR)",
             published_at=NOW, fetched_at=NOW),
        Item(id="hn:1", source="hackernews", kind="hn", url="https://e.com/1", title="Nvidia reinstates Huang",
             metrics=Metrics(points=300, comments=120), extra={"hn_url": "https://news.ycombinator.com/item?id=1"}, published_at=NOW, fetched_at=NOW),
        Item(id="github:o/r", source="github", kind="repo", url="https://github.com/o/r", title="o/r", summary="an agent tool",
             metrics=Metrics(stars=100), published_at=NOW - timedelta(days=2), fetched_at=NOW),
    ]
    st.upsert_items(items, NOW - timedelta(hours=8))
    repo = items[-1].model_copy(update={"metrics": Metrics(stars=160)})
    st.upsert_items([repo], NOW)  # +60 stars in 8 hours: 180 stars/day
    with st.conn:
        st.conn.execute("UPDATE items SET relevant = 1, relevance_by = 'test'")
    embed.embed_pending(st, EMB, iso(NOW - timedelta(days=3)), 300, NOW)
    settings.cluster.join_threshold = settings.cluster.confident_threshold = 0.5
    cluster.run(st, EMB.name, settings.cluster, NOW)
    return st


def test_evidence_must_come_from_the_item():
    raw = {"track": "technical", "frame": "bubble", "evidence": ["Nvidia board reinstates", "not in the text", "x y"],
           "confidence": "high", "entities": ["Nvidia", "Nvidia"], "track2": "technical"}
    out = classify.check_news_label(raw, ["Nvidia board reinstates Huang", None, "summary"])
    assert out["evidence"] == ["Nvidia board reinstates"] and out["evidence_dropped"] == 2
    assert out["frame"] is None and out["confidence"] == "low"  # "bubble" isn't a technical frame
    assert out["track2"] is None and out["entities"] == ["Nvidia"]
    curly = classify.check_news_label({"track": "economic", "frame": "boom", "evidence": ["Nvidia's 'comeback'"], "confidence": "high"},
                                      ["Nvidia’s ‘comeback’ lifts markets"])
    assert curly["evidence"] == ["Nvidia's 'comeback'"] and curly["confidence"] == "high"


def test_percentiles_and_log_share():
    ranks = momentum.percentile_ranks({"a": 0, "b": 5, "c": 10, "d": 10})
    assert ranks["a"] == 0 and ranks["b"] == pytest.approx(1 / 3) and ranks["c"] == ranks["d"] == pytest.approx(2.5 / 3)
    share = momentum.log_share({"a": 0, "b": 2, "c": 14})
    assert share["a"] == 0 and share["c"] == 1 and 0.3 < share["b"] < 0.5


def test_full_analysis_with_fake_llm(settings):
    st = seeded_store(settings)
    fake = FakeAnthropic()
    llm = make_llm(st, fake)
    res = run_analysis(st, settings, SOURCES, NOW, llm)

    # News labels: the Atlantic (llm: false) and the digest are never sent.
    sent = "\n".join(c["messages"][0]["content"] for c in fake.calls if c["output_format"].__name__ == "NewsBatch")
    assert "again" not in sent and "(TLDR)" not in sent
    assert res.news.labeled == 2 and res.news.skipped_llm_false == 1 and res.news.evidence_dropped == 2
    lab = json.loads(st.conn.execute("SELECT data FROM item_labels WHERE item_id = 'n2'").fetchone()[0])
    assert lab["frame"] == "bubble" and lab["prompt_version"] == "news_label_v3" and lab["evidence"]

    # Haiku calls have thinking off; Sonnet calls use the server-side refusal fallback.
    haiku = [c for c in fake.calls if c["model"] == "claude-haiku-5-5"]
    sonnet = [c for c in fake.calls if c["model"] == "claude-sonnet-5-5"]
    assert all(c["thinking"] == {"type": "disabled"} for c in haiku)
    assert sonnet and all(c.get("fallbacks") == "default" and "server-side-fallback-2026-07-01" in c["betas"] for c in sonnet)

    # One story; momentum sees outlets, HN, the digest and the repo's star velocity.
    top = res.scores[0]
    assert top.features["outlets"] == 3 and top.features["hn_points"] == 300 and top.features["digests"] == 1
    assert res.rising and res.rising[0].kind == "repo" and res.rising[0].signal.startswith("+180 stars/day")

    ed = edition.build(st, settings, SOURCES, res.scores, res.rising, NOW, 7)
    s = ed["stories"][0]
    assert s["headline"] == "Nvidia reinstates its chief executive" and s["track"] == "economic"
    assert s["stance"]["-1"] == 1 and s["stance"]["0"] == 1 and s["stance"]["unlabeled"] == 1
    opted_out = [c for g in s["coverage"] for c in g["items"] if c["llm_opt_out"]]
    assert [c["outlet"] for c in opted_out] == ["The Atlantic"]
    assert "HN 300 points" in s["builders_line"] and "TLDR AI" in s["builders_line"]
    assert ed["weather"].startswith("Market-heavy") and ed["rising"][0]["what"] == "thing 0"
    assert ed["llm"]["month_spend_usd"] > 0

    # Second run: nothing new, so no new LLM calls at all.
    n = len(fake.calls)
    run_analysis(st, settings, SOURCES, NOW, llm)
    assert len(fake.calls) == n


def test_summary_material_withholds_opted_out_text(settings):
    st = seeded_store(settings)
    scores = momentum.score_stories(st, settings, SOURCES, NOW)
    text = summarize.material(edition.story_entry(st, SOURCES, scores[0], 1))
    assert "again" not in text and "text withheld at the publisher's request): The Atlantic" in text
    assert "Hacker News: Nvidia reinstates Huang (300 points" in text


def test_budget_reached_skips_llm_but_still_ranks(settings):
    st = seeded_store(settings)
    fake = FakeAnthropic()
    settings.llm.monthly_budget_usd = 0
    llm = LLM(settings.llm, st, "run", client=fake)
    res = run_analysis(st, settings, SOURCES, NOW, llm)
    assert fake.calls == [] and res.scores and any("budget" in n for n in res.notes)
    assert edition.build(st, settings, SOURCES, res.scores, res.rising, NOW, 7)["llm"]["budget_reached"]


def test_cli_classify_and_stories_dry_run():
    runner = CliRunner()
    res = runner.invoke(app, ["classify", "--dry-run"])
    assert res.exit_code == 0, res.output
    assert "momentum" in res.output and "Rising" in res.output
    res = runner.invoke(app, ["stories", "--dry-run"])
    assert res.exit_code == 0, res.output


def test_evidence_match_ignores_punctuation_and_keeps_rejected():
    out = classify.check_news_label(
        {"track": "technical", "frame": "neutral", "evidence": ["Huang's return resuscitates AI trade...", "a made-up phrase"], "confidence": "medium"},
        ["Japan Stocks Rebound as Huang’s Return Resuscitates AI Trade"],
    )
    assert out["evidence"] == ["Huang's return resuscitates AI trade..."] and out["evidence_rejected"] == ["a made-up phrase"]
    assert out["frame"] == "grounded" and out["frame_repaired"] == "neutral" and out["confidence"] == "medium"
    # Whole words only: "AI" must not match inside "said"
    assert classify.check_news_label({"track": "economic", "frame": "boom", "evidence": ["ai"], "confidence": "high"}, ["He said so"])["evidence"] == []


def test_long_real_quotes_are_cut_to_twelve_words():
    text = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen"
    out = classify.check_news_label({"track": "economic", "frame": "boom", "evidence": [text], "confidence": "high"}, [text])
    assert out["evidence"] == ["one two three four five six seven eight nine ten eleven twelve…"]
    assert out["evidence_truncated"] == 1 and out["confidence"] == "high"


def test_summary_refreshes_when_labels_change(settings):
    a = settings.analysis
    entry = {"items": 10, "outlets": 4, "stance": {"-1": 2, "0": 5, "unclear": 3}}
    prev = {"prompt_version": a.summary_prompt, "item_count": 10, "outlet_count": 4,
            "data": json.dumps({"basis": {"news_prompt": a.news_prompt, "stance": {"-1": 2, "0": 5, "unclear": 3}}})}
    assert not summarize.needs_refresh(prev, entry, a)
    assert summarize.needs_refresh(prev, {**entry, "stance": {"-1": 2, "0": 8, "unclear": 0}}, a)  # unclear became neutral
    assert summarize.needs_refresh({**prev, "data": json.dumps({"basis": {"news_prompt": "old", "stance": entry["stance"]}})}, entry, a)
    assert summarize.needs_refresh({**prev, "data": "{}"}, entry, a)  # summaries from before this check


def test_big_stories_refresh_only_on_real_growth(settings):
    a = settings.analysis
    basis = {"news_prompt": a.news_prompt, "stance": {"0": 100}}
    prev = {"prompt_version": a.summary_prompt, "item_count": 100, "outlet_count": 40, "data": json.dumps({"basis": basis})}
    entry = lambda items, outlets, stance=None: {"items": items, "outlets": outlets, "stance": stance or {"0": 100}}  # noqa: E731
    assert not summarize.needs_refresh(prev, entry(103, 41), a)      # +3 items, +1 outlet on a 100-item story: no
    assert summarize.needs_refresh(prev, entry(130, 41), a)          # +30%
    assert summarize.needs_refresh(prev, entry(103, 48), a)          # +8 outlets (20%)
    assert not summarize.needs_refresh(prev, entry(103, 41, {"0": 90, "-1": 4, "unclear": 6}), a)  # stance moved 10 of 100
    assert summarize.needs_refresh(prev, entry(103, 41, {"0": 80, "-1": 20}), a)  # moved 40 of 100


def test_weather_is_throttled(settings):
    from datetime import timedelta as td
    from quiet_ai.pipeline.momentum import StoryScore
    st = seeded_store(settings)
    fake = FakeAnthropic()
    llm = make_llm(st, fake)
    period = settings.site.periods[0]
    scores = lambda ids: [StoryScore(i, 1.0, {"outlets": 1}, iso(NOW)) for i in ids]  # noqa: E731
    with st.conn:
        st.conn.execute("INSERT INTO reports(kind, prompt_version, model, data, created_at) VALUES (?, ?, 'm', ?, ?)",
                        (f"weather:{period.key}", settings.analysis.weather_prompt, json.dumps({"sentence": "s", "story_ids": ["a", "b", "c", "d"]}), iso(NOW - td(hours=1))))
    summarize.weather(st, settings, SOURCES, llm, scores(["a", "b", "c", "e"]), [], 4, NOW, period)
    assert fake.calls == []                                          # top 3 unchanged, line is fresh
    summarize.weather(st, settings, SOURCES, llm, scores(["a", "b", "x", "d"]), [], 4, NOW, period)
    assert len(fake.calls) == 1                                      # top 3 changed
