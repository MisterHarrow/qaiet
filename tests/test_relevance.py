from __future__ import annotations

import re
from datetime import timedelta
from types import SimpleNamespace

from quiet_ai.config import FeedSource, LLMSettings, ModelPrice, SourcesConfig
from quiet_ai.llm.client import LLM
from quiet_ai.pipeline import relevance
from quiet_ai.store.db import Store, iso
from quiet_ai.store.models import Item
from tests.conftest import NOW

ALWAYS_KINDS = {"repo", "paper"}


def v(kind="news", source="x", title="", summary=None, ai_sources=frozenset()):
    return relevance.keyword_verdict(kind, source, title, summary, set(ai_sources), ALWAYS_KINDS, {"hf_posts"})


def test_keyword_verdicts():
    assert v(kind="repo", title="whatever") == (True, "kind")
    assert v(source="verge", title="Phone review", ai_sources={"verge"}) == (True, "source")
    assert v(source="hf_posts", title="hello") == (True, "source")
    assert v(title="OpenAI raises prices") == (True, "keyword")
    assert v(title="Nvidia board brings back Huang") == (True, "keyword")
    assert v(title="KI-Verordnung tritt in Kraft") == (True, "keyword")
    assert v(title="Regeringen vill reglera AI i skolan") == (True, "keyword")
    assert v(title="Nvidias jakt på ny vd") == (True, "keyword")
    assert v(title="OpenAI’s new model") == (True, "keyword")
    # Latin America: Spanish and Portuguese, spelled out or abbreviated
    assert v(title="O avanço da inteligência artificial no Brasil") == (True, "keyword")
    assert v(title="Governo lança plano nacional de IA") == (True, "keyword")
    assert v(title="México atrae inversiones en centros de datos") == (True, "keyword")
    assert v(title="Novos modelos de linguagem em português") == (True, "keyword")
    assert v(title="Big techs e semicondutores", summary=None) == (None, "ambiguous")
    assert v(title="Flamengo vence o clássico") == (False, "keyword")
    assert v(title="Microsoft reports earnings") == (None, "ambiguous")
    assert v(title="Markets fall", summary="Investors worry about artificial intelligence spending") == (None, "ambiguous")
    assert v(title="Local team wins final") == (False, "keyword")
    # case-sensitive acronyms don't fire on ordinary words
    assert v(title="Said the chair at the fair") == (False, "keyword")


class FakeMessages:
    def __init__(self, refuse=False):
        self.calls = []
        self.refuse = refuse

    def parse(self, **kw):
        self.calls.append(kw)
        lines = kw["messages"][0]["content"].splitlines()
        out = []
        for line in lines:
            m = re.match(r"\[(\d+)\] \((\w+)\) (.*)", line)
            n, lang, text = int(m.group(1)), m.group(2), m.group(3)
            out.append({"i": n, "about_ai": "algorithm" in text.lower() or "ki" in text.lower(),
                        "title_en": None if lang == "en" else "EN: " + text.split(" | ")[0]})
        parsed = kw["output_format"].model_validate({"items": out})
        usage = SimpleNamespace(input_tokens=1000, output_tokens=200, cache_read_input_tokens=0, cache_creation_input_tokens=0)
        return SimpleNamespace(parsed_output=parsed, usage=usage, stop_reason="refusal" if self.refuse else "end_turn")


def fake_llm(store, messages, budget=30.0):
    settings = LLMSettings(monthly_budget_usd=budget, prices={"claude-haiku-5-5": ModelPrice(input=0.1, output=0.5)})
    return LLM(settings, store, run_id="r", client=SimpleNamespace(messages=messages))


def seed(store):
    items = [
        Item(id="a", source="nyt", kind="news", url="https://e.com/a", title="Google tweaks its search algorithm", fetched_at=NOW),
        Item(id="b", source="nyt", kind="news", url="https://e.com/b", title="Microsoft opens an office", fetched_at=NOW),
        Item(id="c", source="dn", kind="news", url="https://e.com/c", title="Regeringen satsar på AI", lang="sv", fetched_at=NOW),
        Item(id="d", source="nyt", kind="news", url="https://e.com/d", title="Weather is nice", fetched_at=NOW),
        Item(id="e", source="nyt", kind="news", url="https://e.com/e2", title="Weather is nice", fetched_at=NOW),
    ]
    store.upsert_items(items, NOW)


def test_run_with_llm_decides_ambiguous_translates_and_caches(settings):
    store = Store(":memory:")
    seed(store)
    msgs = FakeMessages()
    llm = fake_llm(store, msgs)
    srcs = SourcesConfig(feeds=[FeedSource(id="nyt", name="NYT", kind="news", feeds=["x"])])
    since = iso(NOW - timedelta(hours=72))
    stats = relevance.run(store, settings, srcs, llm, since)
    rows = {r["id"]: r for r in store.conn.execute("SELECT id, relevant, relevance_by, title_en, dup_of FROM items")}
    assert (rows["a"]["relevant"], rows["a"]["relevance_by"]) == (1, "llm")
    assert (rows["b"]["relevant"], rows["b"]["relevance_by"]) == (0, "llm")
    assert (rows["c"]["relevant"], rows["c"]["title_en"]) == (1, "EN: Regeringen satsar på AI")
    assert rows["d"]["relevant"] == 0 and rows["e"]["dup_of"] == "d"
    assert stats.duplicates == 1 and stats.pending == 0 and len(msgs.calls) == 1
    call = msgs.calls[0]
    assert call["model"] == "claude-haiku-5-5" and call["system"][0]["cache_control"] == {"type": "ephemeral"}
    cost = store.conn.execute("SELECT SUM(cost_usd) FROM llm_calls").fetchone()[0]
    assert abs(cost - (1000 * 0.1 + 200 * 0.5) / 1e6) < 1e-12

    # Nothing left to decide: a second run makes no call.
    relevance.run(store, settings, srcs, llm, since)
    assert len(msgs.calls) == 1


def test_run_without_llm_leaves_ambiguous_pending(settings):
    store = Store(":memory:")
    seed(store)
    stats = relevance.run(store, settings, SourcesConfig(feeds=[]), None, iso(NOW - timedelta(hours=72)))
    assert stats.pending == 2 and "ANTHROPIC_API_KEY" in stats.note
    assert store.conn.execute("SELECT relevant FROM items WHERE id='a'").fetchone()[0] is None


def test_budget_cap_stops_llm_calls(settings):
    store = Store(":memory:")
    seed(store)
    msgs = FakeMessages()
    llm = fake_llm(store, msgs, budget=0.0)
    stats = relevance.run(store, settings, SourcesConfig(feeds=[]), llm, iso(NOW - timedelta(hours=72)))
    assert msgs.calls == [] and "budget" in stats.note and stats.pending == 2


def test_refusal_is_not_applied(settings):
    store = Store(":memory:")
    seed(store)
    stats = relevance.run(store, settings, SourcesConfig(feeds=[]), fake_llm(store, FakeMessages(refuse=True)), iso(NOW - timedelta(hours=72)))
    assert stats.pending == 2 and "declined" in stats.note


def test_llm_false_sources_never_reach_the_llm(settings):
    store = Store(":memory:")
    store.upsert_items([
        Item(id="x", source="atlantic", kind="news", url="https://e.com/x", title="Microsoft's new office", summary="About artificial intelligence", fetched_at=NOW),
        Item(id="y", source="atlantic", kind="news", url="https://e.com/y", title="Apple's new office", summary="Nothing else", fetched_at=NOW),
    ], NOW)
    msgs = FakeMessages()
    srcs = SourcesConfig(feeds=[FeedSource(id="atlantic", name="The Atlantic", kind="news", feeds=["x"], llm=False)])
    relevance.run(store, settings, srcs, fake_llm(store, msgs), iso(NOW - timedelta(hours=72)))
    assert msgs.calls == []
    rows = dict(store.conn.execute("SELECT id, relevant FROM items").fetchall())
    assert rows == {"x": 1, "y": 0}
