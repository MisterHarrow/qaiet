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
    # Scripts without spaces: Latin names and acronyms inside them, and native terms
    for t in ["生成AIが変える仕事", "OpenAI发布新模型", "Nvidia顶住压力", "인공지능 규제법", "엔비디아 실적 발표", "英伟达股价下跌",
              "الذكاء الاصطناعي في مصر", "एआई से नौकरियां", "Yapay zekâ ve eğitim", "Kecerdasan buatan di sekolah",
              "Trí tuệ nhân tạo thay đổi việc làm", "삼성, AI 반도체 투자"]:
        assert v(title=t) == (True, "keyword"), t
    for t in ["L’intelligenza artificiale cambia il lavoro", "Kabinet wil regels voor kunstmatige intelligentie",
              "Regjeringen satser på kunstig intelligens", "Tekoäly mullistaa koulut", "Sztuczna inteligencja w szkołach",
              "Umělá inteligence a práce", "A mesterséges intelligencia hatása", "Штучний інтелект у школах", "Як ШІ змінює роботу"]:
        assert v(title=t) == (True, "keyword"), t
    assert v(title="ШІСТЬ новин") == (False, "keyword")  # the Ukrainian acronym only as a word of its own
    assert v(title="半导体出口管制") == (None, "ambiguous")
    assert v(title="KIA launches a new EV") == (False, "keyword")  # KI (German for AI) only as a word of its own
    assert v(title="東京で大雨") == (False, "keyword")
    assert relevance.norm_title("英伟达股价下跌，市场担忧") == "英伟达股价下跌 市场担忧"  # duplicates are caught in any script
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
            low = text.lower()
            desk = "ai" if ("algorithm" in low or "ki" in low) else "energy" if "power plant" in low else None
            out.append({"i": n, "desk": desk, "title_en": None if lang == "en" else "EN: " + text.split(" | ")[0]})
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
        Item(id="f", source="nyt", kind="news", url="https://e.com/f", title="Utility opens a new power plant", fetched_at=NOW),
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
    rows = {r["id"]: r for r in store.conn.execute("SELECT id, relevant, relevance_by, desk, title_en, dup_of FROM items")}
    assert (rows["a"]["relevant"], rows["a"]["relevance_by"], rows["a"]["desk"]) == (1, "llm", "ai")
    assert (rows["b"]["relevant"], rows["b"]["relevance_by"], rows["b"]["desk"]) == (0, "llm", None)
    assert (rows["c"]["relevant"], rows["c"]["title_en"], rows["c"]["desk"]) == (1, "EN: Regeringen satsar på AI", "ai")
    # No AI word: with more desks than AI, the model sorts it (onto Energy here, or nowhere).
    assert (rows["d"]["relevant"], rows["d"]["relevance_by"]) == (0, "llm") and rows["e"]["dup_of"] == "d"
    assert (rows["f"]["relevant"], rows["f"]["relevance_by"], rows["f"]["desk"]) == (1, "llm", "energy")
    assert stats.duplicates == 1 and stats.pending == 0 and len(msgs.calls) == 1
    call = msgs.calls[0]
    assert call["model"] == "claude-haiku-5-5" and call["system"][0]["cache_control"] == {"type": "ephemeral"}
    cost = store.conn.execute("SELECT SUM(cost_usd) FROM llm_calls").fetchone()[0]
    assert abs(cost - (1000 * 0.1 + 200 * 0.5) / 1e6) < 1e-12

    # Nothing left to decide: a second run makes no call.
    relevance.run(store, settings, srcs, llm, since)
    assert len(msgs.calls) == 1


class LazyTranslator(FakeMessages):
    """The relevance call leaves every English title empty (as Haiku sometimes does); the translation call fills them,
    except for headlines containing "skip", which come back blank."""

    def parse(self, **kw):
        self.calls.append(kw)
        out = []
        for line in kw["messages"][0]["content"].splitlines():
            n, lang, text = re.match(r"\[(\d+)\] \((\w+)\) (.*)", line).groups()
            if kw["output_format"] is relevance._Translations:
                out.append({"i": int(n), "title_en": "" if "skip" in text else f"EN: {text}"})
            else:
                out.append({"i": int(n), "desk": "ai", "title_en": None})
        usage = SimpleNamespace(input_tokens=100, output_tokens=20, cache_read_input_tokens=0, cache_creation_input_tokens=0)
        return SimpleNamespace(parsed_output=kw["output_format"].model_validate({"items": out}), usage=usage, stop_reason="end_turn")


def test_titles_the_relevance_call_left_untranslated_get_a_translation_call(settings):
    store = Store(":memory:")
    store.upsert_items([
        Item(id="j", source="itm", kind="news", url="https://e.com/j", title="生成AIが変える仕事", lang="ja", fetched_at=NOW),
        Item(id="k", source="lupa", kind="news", url="https://e.com/k", title="Umělá inteligence skip", lang="cs", fetched_at=NOW),
        Item(id="m", source="nyt", kind="news", url="https://e.com/m", title="OpenAI raises prices", fetched_at=NOW),
    ], NOW)
    msgs = LazyTranslator()
    llm = fake_llm(store, msgs)
    since = iso(NOW - timedelta(hours=72))
    stats = relevance.run(store, settings, SourcesConfig(feeds=[]), llm, since)
    titles = dict(store.conn.execute("SELECT id, title_en FROM items").fetchall())
    assert titles == {"j": "EN: 生成AIが変える仕事", "k": None, "m": None}  # English needs none; a blank answer isn't kept
    assert stats.translated == 1 and [c["output_format"] for c in msgs.calls] == [relevance._Batch, relevance._Translations]
    assert store.conn.execute("SELECT task FROM llm_calls ORDER BY id").fetchall()[-1][0] == "translate"
    # Next run: the translated one is done; the blank one is asked again, the relevance answers come from the cache.
    relevance.run(store, settings, SourcesConfig(feeds=[]), llm, since)
    assert [c["output_format"] for c in msgs.calls[2:]] == [relevance._Translations]
    assert msgs.calls[2]["messages"][0]["content"] == "[0] (cs) Umělá inteligence skip"


def test_run_without_llm_leaves_ambiguous_pending(settings):
    store = Store(":memory:")
    seed(store)
    stats = relevance.run(store, settings, SourcesConfig(feeds=[]), None, iso(NOW - timedelta(hours=72)))
    assert stats.pending == 4 and "ANTHROPIC_API_KEY" in stats.note  # a, b, d, f (e is d's duplicate)
    assert store.conn.execute("SELECT relevant FROM items WHERE id='a'").fetchone()[0] is None


def test_budget_cap_stops_llm_calls(settings):
    store = Store(":memory:")
    seed(store)
    msgs = FakeMessages()
    llm = fake_llm(store, msgs, budget=0.0)
    stats = relevance.run(store, settings, SourcesConfig(feeds=[]), llm, iso(NOW - timedelta(hours=72)))
    assert msgs.calls == [] and "budget" in stats.note and stats.pending == 4


def test_refusal_is_not_applied(settings):
    store = Store(":memory:")
    seed(store)
    stats = relevance.run(store, settings, SourcesConfig(feeds=[]), fake_llm(store, FakeMessages(refuse=True)), iso(NOW - timedelta(hours=72)))
    assert stats.pending == 4 and "declined" in stats.note


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


def test_with_only_the_ai_desk_items_without_ai_words_are_dropped_without_a_call(settings):
    settings = settings.model_copy(update={"desks": [d for d in settings.desks if d.key == "ai"]})
    store = Store(":memory:")
    seed(store)
    msgs = FakeMessages()
    relevance.run(store, settings, SourcesConfig(feeds=[]), fake_llm(store, msgs), iso(NOW - timedelta(hours=72)))
    rows = dict(store.conn.execute("SELECT id, relevance_by FROM items").fetchall())
    assert rows["d"] == "keyword" and rows["f"] == "keyword"
    assert "power plant" not in msgs.calls[0]["messages"][0]["content"]


def test_desk_sources_and_llm_false_sources_by_keyword(settings):
    store = Store(":memory:")
    store.upsert_items([
        Item(id="s", source="spacenews", kind="news", url="https://e.com/s", title="Launch delayed again", fetched_at=NOW),
        Item(id="g", source="atlantic", kind="news", url="https://e.com/g", title="Why electricity bills keep rising", fetched_at=NOW),
        Item(id="h", source="atlantic", kind="news", url="https://e.com/h", title="A new novel", fetched_at=NOW),
    ], NOW)
    msgs = FakeMessages()
    srcs = SourcesConfig(feeds=[FeedSource(id="spacenews", name="SpaceNews", kind="news", feeds=["x"], desk="space"),
                                FeedSource(id="atlantic", name="The Atlantic", kind="news", feeds=["x"], llm=False)])
    relevance.run(store, settings, srcs, fake_llm(store, msgs), iso(NOW - timedelta(hours=72)))
    assert msgs.calls == []
    rows = {r["id"]: (r["relevant"], r["desk"]) for r in store.conn.execute("SELECT id, relevant, desk FROM items")}
    assert rows == {"s": (1, "space"), "g": (1, "energy"), "h": (0, None)}
