"""The M2 chain: relevance -> embed -> cluster."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from quiet_ai.config import ROOT, Settings, SourcesConfig
from quiet_ai.llm.client import LLM
from quiet_ai.pipeline import classify, cluster, edition, embed, gap, momentum, relevance, sentiment, summarize
from quiet_ai.store.db import Store, iso


@dataclass
class ClusterRun:
    relevance: relevance.RelevanceStats
    embedded: int
    cluster: cluster.ClusterStats
    embedder: str


def default_embedder(settings: Settings, offline: bool = False) -> embed.Embedder:
    """The configured model; in offline mode only if it is already downloaded."""
    cache = ROOT / settings.embed.cache_dir
    downloaded = cache.exists() and any(settings.embed.model.split("/")[-1].lower() in p.name.lower() for p in cache.iterdir())
    if offline and not downloaded:
        return embed.HashEmbedder()
    return embed.FastEmbedder(settings.embed)


def run_cluster(store: Store, settings: Settings, sources: SourcesConfig, now: datetime, llm: LLM | None, embedder: embed.Embedder) -> ClusterRun:
    since = iso(now - timedelta(hours=settings.cluster.window_hours))
    rstats = relevance.run(store, settings, sources, llm, since)
    n = embed.embed_pending(store, embedder, since, settings.embed.summary_chars, now)
    cstats = cluster.run(store, embedder.name, settings.cluster, now)
    embed.prune(store, now, settings.embed.keep_days)
    return ClusterRun(rstats, n, cstats, embedder.name)


@dataclass
class PeriodView:
    period: object
    scores: list[momentum.StoryScore]
    rising: list[momentum.RisingItem]


@dataclass
class AnalysisRun:
    views: dict[str, PeriodView]
    news: classify.LabelStats
    builders: classify.LabelStats
    summaries: summarize.SummaryStats
    weather: summarize.SummaryStats
    notes: list[str]

    @property
    def front(self) -> PeriodView:
        return next(iter(self.views.values()))

    @property
    def scores(self) -> list[momentum.StoryScore]:
        return self.front.scores

    @property
    def rising(self) -> list[momentum.RisingItem]:
        return self.front.rising


def period_views(store: Store, settings: Settings, sources: SourcesConfig, now: datetime) -> dict[str, PeriodView]:
    return {
        p.key: PeriodView(p, momentum.score_stories(store, settings, sources, now, p), momentum.rising(store, settings, now, p.hours))
        for p in settings.site.periods
    }


def run_analysis(store: Store, settings: Settings, sources: SourcesConfig, now: datetime, llm: LLM | None) -> AnalysisRun:
    """Labels (Haiku), then for every view (24 hours, 7 days, ...): ranking, Rising, summaries
    of its top stories and its weather line (Sonnet). Without an LLM, or once the budget is
    spent, the LLM steps are skipped and everything else still runs."""
    a = settings.analysis
    since = iso(now - timedelta(hours=settings.cluster.window_hours))
    use_llm = llm is not None and llm.available
    notes = [] if use_llm else ["no ANTHROPIC_API_KEY: no labels, summaries or weather this run"]
    news = classify.label_news(store, settings, sources, llm, since) if use_llm else classify.LabelStats()
    sentiment.compute(store, settings, now)
    views = period_views(store, settings, sources, now)  # after labels: merging uses their names
    builder_ids: list[str] = []
    for v in views.values():
        builder_ids += [r.item_id for r in v.rising]
        members = [sid for s in v.scores[: a.summarize_top] for sid in s.members]
        if members:
            builder_ids += [r["id"] for r in store.conn.execute(
                f"SELECT id FROM items WHERE story_id IN ({','.join('?' * len(members))}) AND kind IN ('repo','model','dataset','space','paper')",
                members,
            )]
    builders = classify.label_builders(store, settings, llm, list(dict.fromkeys(builder_ids))) if use_llm else classify.LabelStats()
    sums, wx = summarize.SummaryStats(), summarize.SummaryStats()
    if use_llm:
        for v in views.values():
            st = summarize.summarize_top(store, settings, sources, llm, v.scores, now)
            sums.summarized += st.summarized
            sums.unchanged += st.unchanged
            sums.notes += [n for n in st.notes if n not in sums.notes]
            w = summarize.weather(store, settings, sources, llm, v.scores, v.rising, a.top_stories, now, v.period)
            wx.weather = wx.weather or w.weather
            wx.notes += [n for n in w.notes if n not in wx.notes]
    for st in (news, builders, sums, wx):
        notes += [n for n in st.notes if n not in notes]
    return AnalysisRun(views, news, builders, sums, wx, notes)


def build_editions(store: Store, settings: Settings, sources: SourcesConfig, now: datetime, views: dict[str, PeriodView] | None = None) -> list[dict]:
    """One edition per view, with The gap and the sentiment index for that period."""
    import math

    views = views or period_views(store, settings, sources, now)
    hist = sentiment.history(store)
    out = []
    for v in views.values():
        ed = edition.build(store, settings, sources, v.scores, v.rising, now, settings.analysis.top_stories, v.period)
        ed["gap"] = gap.compute(store, settings, sources, v.scores)
        days = max(1, math.ceil(v.period.hours / 24))
        values = sentiment.period_value(hist, days)
        latest = hist["all"][-1]["date"] if hist.get("all") else None
        ed["sentiment"] = {"values": values, "words": sentiment.describe(values.get("all")), "days": days, "latest": latest,
                           "outlets": hist["all"][-1]["outlets"] if hist.get("all") else None}
        out.append(ed)
    return out
