"""The gap: what builders are busy with that the press hasn't covered, and what the press
is covering that builders aren't talking about."""

from __future__ import annotations

from quiet_ai.config import Settings, SourcesConfig
from quiet_ai.pipeline.edition import story_entry
from quiet_ai.pipeline.momentum import StoryScore, percentile_ranks
from quiet_ai.store.db import Store

BUILDER_FEATURES = ("hn_points", "star_velocity", "hf_trending", "social")


def builder_ranks(scores: list[StoryScore]) -> dict[str, float]:
    """Each story's strongest builder signal, as a percentile among the stories in view."""
    ranks = {f: percentile_ranks({s.story_id: s.features.get(f, 0) for s in scores}) for f in BUILDER_FEATURES}
    return {s.story_id: max(ranks[f][s.story_id] for f in BUILDER_FEATURES) for s in scores}


def compute(store: Store, settings: Settings, sources: SourcesConfig, scores: list[StoryScore]) -> dict:
    g = settings.gap
    builder = builder_ranks(scores)

    def strong(s: StoryScore) -> bool:  # a real builder signal, not just a top rank among weak ones
        return any(s.features.get(f, 0) >= floor for f, floor in g.builder_floors.items())

    quiet_press = [
        s for s in scores
        if s.features.get("outlets", 0) <= g.quiet_max_outlets and builder[s.story_id] >= g.builder_min_rank and strong(s)
    ]
    quiet_press.sort(key=lambda s: (builder[s.story_id], s.score), reverse=True)
    quiet_builders = [
        s for s in scores
        if s.features.get("outlets", 0) >= g.loud_min_outlets and builder[s.story_id] <= g.builder_max_rank_quiet
    ]
    quiet_builders.sort(key=lambda s: (s.features.get("outlets", 0), s.score), reverse=True)

    def entry(s: StoryScore, n: int) -> dict:
        e = story_entry(store, sources, s, n)
        b = e["builders"]
        link = (b["hn"][0]["url"] if b["hn"] else b["repos"][0]["url"] if b["repos"] else
                b["models"][0]["url"] if b["models"] else b["papers"][0]["url"] if b["papers"] else None)
        return {"id": e["id"], "headline": e["headline"], "track": e["track"], "outlets": e["outlets"], "countries": e["countries"],
                "stance_summary": e["stance_summary"], "builders_line": e["builders_line"], "link": link}

    return {
        "builders_not_press": [entry(s, n) for n, s in enumerate(quiet_press[: g.max_items], 1)],
        "press_not_builders": [entry(s, n) for n, s in enumerate(quiet_builders[: g.max_items], 1)],
    }
