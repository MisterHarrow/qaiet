"""The M2 chain: relevance -> embed -> cluster."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from quiet_ai.config import ROOT, Settings, SourcesConfig
from quiet_ai.llm.client import LLM
from quiet_ai.pipeline import cluster, embed, relevance
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
