"""Assemble the day's edition as plain data: the terminal view, the site (M4) and the
frozen daily archive (M5) all read this one structure."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import Any

from quiet_ai.config import Settings, SourcesConfig
from quiet_ai.pipeline.momentum import RisingItem, StoryScore
from quiet_ai.pipeline.stories import representative_title, source_names
from quiet_ai.store.db import Store, iso

STANCES = (-2, -1, 0, 1, 2)
_PRESS_KINDS = ("news", "newsletter")


def story_members(store: Store, story_id: str) -> list[dict]:
    rows = store.conn.execute(
        "SELECT i.id, i.kind, i.source, i.url, i.title, i.title_en, i.lang, i.published_at, i.metrics, i.extra, "
        "l.task, l.track, l.frame, l.stance, l.confidence, l.data AS label "
        "FROM items i LEFT JOIN item_labels l ON l.item_id = i.id WHERE i.story_id = ? AND i.relevant = 1 AND i.dup_of IS NULL "
        "ORDER BY i.published_at",
        (story_id,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["metrics"] = json.loads(r["metrics"] or "{}")
        d["extra"] = json.loads(r["extra"] or "{}")
        d["label"] = json.loads(r["label"]) if r["label"] else None
        out.append(d)
    return out


def _stance_key(m: dict) -> str:
    if m["label"] is None:
        return "unlabeled"
    if m["confidence"] == "low":
        return "unclear"
    return str(m["stance"])


def story_entry(store: Store, sources: SourcesConfig, score: StoryScore, rank: int) -> dict[str, Any]:
    names = source_names(sources)
    feeds = {f.id: f for f in sources.feeds}
    countries = {f.id: f.country for f in sources.feeds} | {g.id: g.country for g in sources.gdelt_outlets}
    members = story_members(store, score.story_id)
    summary = store.conn.execute("SELECT data, prompt_version, model FROM story_summaries WHERE story_id = ?", (score.story_id,)).fetchone()
    summary_data = json.loads(summary["data"]) if summary else None

    press = [m for m in members if m["kind"] in _PRESS_KINDS and not (m["kind"] == "newsletter" and (feeds.get(m["source"]) and feeds[m["source"]].role == "digest"))]
    stance = Counter(_stance_key(m) for m in press)
    groups: dict[str, list[dict]] = {}
    seen_outlets: set[str] = set()
    for m in sorted(press, key=lambda m: (m["source"], m["published_at"] or "")):
        if m["source"] in seen_outlets:  # one headline per outlet in the coverage list
            continue
        seen_outlets.add(m["source"])
        feed = feeds.get(m["source"])
        groups.setdefault(_stance_key(m), []).append({
            "outlet": names.get(m["source"], m["source"]),
            "country": countries.get(m["source"]),
            "kind": m["kind"],
            "title": m["title"],
            "title_en": m["title_en"],
            "url": m["url"],
            "frame": m["frame"],
            "evidence": (m["label"] or {}).get("evidence", []),
            "rationale": (m["label"] or {}).get("rationale"),
            "llm_opt_out": bool(feed and not feed.llm),
        })

    tracks = Counter(m["track"] for m in press if m["track"] and m["confidence"] != "low")
    hn = [m for m in members if m["kind"] == "hn"]
    builders = {
        "hn": [{"title": m["title"], "url": m["extra"].get("hn_url", m["url"]), "points": m["metrics"].get("points", 0),
                "comments": m["metrics"].get("comments", 0)} for m in sorted(hn, key=lambda m: -m["metrics"].get("points", 0))],
        "repos": [{"title": m["title"], "url": m["url"], "stars": m["metrics"].get("stars", 0)} for m in members if m["kind"] == "repo"],
        "models": [{"title": m["title"], "url": m["url"], "source": names.get(m["source"], m["source"])}
                   for m in members if m["kind"] in ("model", "dataset", "space")],
        "papers": [{"title": m["title"], "url": m["url"], "upvotes": m["metrics"].get("likes", 0)} for m in members if m["kind"] == "paper"],
        "social": sum(1 for m in members if m["kind"] == "social"),
        "official": [{"title": m["title"], "url": m["url"], "source": names.get(m["source"], m["source"])} for m in members if m["kind"] == "lab"],
        "digests": sorted({names.get(m["source"], m["source"]) for m in members if m["kind"] == "newsletter" and feeds.get(m["source"]) and feeds[m["source"]].role == "digest"}),
    }
    headline = (summary_data or {}).get("headline") or representative_title(store, score.story_id) or score.story_id
    return {
        "id": score.story_id,
        "rank": rank,
        "momentum": score.score,
        "features": score.features,
        "headline": headline,
        "track": (summary_data or {}).get("track") or (tracks.most_common(1)[0][0] if tracks else None),
        "summary": summary_data,
        "outlets": int(score.features.get("outlets", 0)),
        "countries": int(score.features.get("countries", 0)),
        "stance": {k: stance.get(k, 0) for k in [*map(str, STANCES), "unclear", "unlabeled"]},
        "coverage": [{"stance": k, "items": groups[k]} for k in [*map(str, STANCES), "unclear", "unlabeled"] if k in groups],
        "builders": builders,
        "builders_line": builders_line(builders),
        "items": len(members),
    }


def builders_line(b: dict) -> str:
    parts = []
    if b["hn"]:
        parts.append(f"HN {sum(h['points'] for h in b['hn']):,} points, {sum(h['comments'] for h in b['hn']):,} comments")
    for key, word in (("repos", "repo"), ("models", "model"), ("papers", "paper")):
        if b[key]:
            parts.append(f"{len(b[key])} {word}{'s' if len(b[key]) > 1 else ''}")
    if b["social"]:
        parts.append(f"{b['social']} post{'s' if b['social'] > 1 else ''}")
    if b["digests"]:
        parts.append("in " + ", ".join(b["digests"][:3]))
    return " · ".join(parts)


def rising_entries(store: Store, rising: list[RisingItem]) -> list[dict]:
    out = []
    for r in rising:
        lab = store.conn.execute("SELECT data FROM item_labels WHERE item_id = ?", (r.item_id,)).fetchone()
        data = json.loads(lab["data"]) if lab else {}
        out.append({"id": r.item_id, "kind": data.get("kind") or r.kind, "title": r.title, "url": r.url, "signal": r.signal,
                    "what": data.get("what"), "why": data.get("why"), "story_id": r.story_id})
    return out


def build(store: Store, settings: Settings, sources: SourcesConfig, scores: list[StoryScore], rising: list[RisingItem], now: datetime, top: int) -> dict[str, Any]:
    weather = store.conn.execute("SELECT data FROM reports WHERE kind = 'weather' ORDER BY id DESC LIMIT 1").fetchone()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    spend = store.conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls WHERE created_at >= ?", (iso(month_start),)).fetchone()[0]
    return {
        "generated_at": iso(now),
        "weather": json.loads(weather["data"])["sentence"] if weather else None,
        "stories": [story_entry(store, sources, s, n) for n, s in enumerate(scores[:top], 1)],
        "rising": rising_entries(store, rising),
        "llm": {"month_spend_usd": round(spend, 4), "budget_usd": settings.llm.monthly_budget_usd,
                "budget_reached": spend >= settings.llm.monthly_budget_usd},
    }
