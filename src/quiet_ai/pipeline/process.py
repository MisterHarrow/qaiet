"""The M2 chain: relevance -> embed -> cluster."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from quiet_ai.config import ROOT, Settings, SourcesConfig
from quiet_ai.llm.client import LLM
from quiet_ai.pipeline import classify, cluster, embed, momentum, relevance, summarize
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
class AnalysisRun:
    scores: list[momentum.StoryScore]
    rising: list[momentum.RisingItem]
    news: classify.LabelStats
    builders: classify.LabelStats
    summaries: summarize.SummaryStats
    weather: summarize.SummaryStats
    notes: list[str]


def run_analysis(store: Store, settings: Settings, sources: SourcesConfig, now: datetime, llm: LLM | None) -> AnalysisRun:
    """Momentum, item labels (Haiku), story summaries and weather (Sonnet). Without an LLM, or
    once the budget is spent, the LLM steps are skipped and everything else still runs."""
    a = settings.analysis
    since = iso(now - timedelta(hours=settings.cluster.window_hours))
    use_llm = llm is not None and llm.available
    notes = [] if use_llm else ["no ANTHROPIC_API_KEY: no labels, summaries or weather this run"]
    news = classify.label_news(store, settings, sources, llm, since) if use_llm else classify.LabelStats()
    scores = momentum.score_stories(store, settings, sources, now)
    rising = momentum.rising(store, settings, now)
    builder_ids = [r.item_id for r in rising]
    top_ids = [s.story_id for s in scores[: a.summarize_top]]
    if top_ids:
        builder_ids += [r["id"] for r in store.conn.execute(
            f"SELECT id FROM items WHERE story_id IN ({','.join('?' * len(top_ids))}) AND kind IN ('repo','model','dataset','space','paper')",
            top_ids,
        )]
    builders = classify.label_builders(store, settings, llm, list(dict.fromkeys(builder_ids))) if use_llm else classify.LabelStats()
    sums = summarize.summarize_top(store, settings, sources, llm, scores, now) if use_llm else summarize.SummaryStats()
    wx = summarize.weather(store, settings, sources, llm, scores, rising, a.top_stories, now) if use_llm else summarize.SummaryStats()
    for st in (news, builders, sums, wx):
        notes += [n for n in st.notes if n not in notes]
    return AnalysisRun(scores, rising, news, builders, sums, wx, notes)
