"""Momentum: rank stories by cross-source signals, and pick the fastest-rising builder items.

Two kinds of features, each scaled to 0..1 across the active stories:
- Counts (outlets, countries, aggregators, digests) are log-scaled against the window's
  maximum, so 14 outlets stays clearly ahead of 2.
- Volumes from one platform (HN points, star velocity, HF trending, social engagement) are
  percentile ranks, so no single source can dominate: 3,000 HN points count no more than
  being the top HN story of the window.
The weighted sum is decayed by the age of the story's latest item.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from quiet_ai.config import Settings, SourcesConfig
from quiet_ai.store.db import Store, iso
from quiet_ai.text import parse_iso

FEATURES = ("outlets", "countries", "hn_points", "star_velocity", "hf_trending", "social", "aggregators", "digests")
COUNT_FEATURES = ("outlets", "countries", "aggregators", "digests")
RISING_KINDS = ("repo", "model", "dataset", "space", "paper")


@dataclass
class StoryScore:
    story_id: str
    score: float
    features: dict[str, float]
    last_at: str


@dataclass
class RisingItem:
    item_id: str
    kind: str
    title: str
    url: str
    signal: str  # human-readable, e.g. "+412 stars/day"
    score: float
    story_id: str | None = None
    extra: dict = field(default_factory=dict)


def percentile_ranks(values: dict[str, float]) -> dict[str, float]:
    """0 for zero/absent; otherwise rank among positive values scaled to (0, 1]."""
    positive = sorted((v, k) for k, v in values.items() if v > 0)
    out = {k: 0.0 for k in values}
    n = len(positive)
    i = 0
    while i < n:  # ties share the average rank
        j = i
        while j + 1 < n and positive[j + 1][0] == positive[i][0]:
            j += 1
        rank = ((i + j) / 2 + 1) / n
        for _, k in positive[i : j + 1]:
            out[k] = rank
        i = j + 1
    return out


def log_share(values: dict[str, float]) -> dict[str, float]:
    top = max(values.values(), default=0)
    if top <= 0:
        return {k: 0.0 for k in values}
    return {k: math.log1p(v) / math.log1p(top) for k, v in values.items()}


def star_velocities(store: Store, item_ids: list[str], now: datetime) -> dict[str, float]:
    """Stars gained per day, measured across runs once we have 6+ hours of snapshots in the
    last 48h; before that, the lifetime average (stars per day since the repo was created)."""
    if not item_ids:
        return {}
    snaps: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for i in range(0, len(item_ids), 500):
        chunk = item_ids[i : i + 500]
        rows = store.conn.execute(
            f"SELECT item_id, observed_at, metrics FROM metric_snapshots WHERE item_id IN ({','.join('?' * len(chunk))}) "
            "ORDER BY observed_at",
            chunk,
        )
        for r in rows:
            stars = json.loads(r["metrics"]).get("stars")
            if stars is not None:
                snaps[r["item_id"]].append((r["observed_at"], stars))
    created = {
        r["id"]: r["published_at"]
        for r in store.conn.execute(
            f"SELECT id, published_at FROM items WHERE id IN ({','.join('?' * len(item_ids))})", item_ids
        )
    }
    out = {}
    since = iso(now - timedelta(hours=48))
    for iid in item_ids:
        s = snaps.get(iid)
        if not s:
            continue
        recent = [x for x in s if x[0] >= since] or s[-1:]
        first, last = recent[0], s[-1]
        span_days = (parse_iso(last[0]) - parse_iso(first[0])).total_seconds() / 86400
        if span_days >= 6 / 24:  # shorter spans extrapolate noise
            out[iid] = max(0.0, (last[1] - first[1]) / span_days)
        else:
            born = parse_iso(created.get(iid))
            age_days = max(1.0, (now - born).total_seconds() / 86400) if born else 30.0
            out[iid] = last[1] / age_days
    return out


def score_stories(store: Store, settings: Settings, sources: SourcesConfig, now: datetime) -> list[StoryScore]:
    m = settings.momentum
    since = iso(now - timedelta(hours=settings.cluster.window_hours))
    countries = {f.id: f.country for f in sources.feeds} | {g.id: g.country for g in sources.gdelt_outlets}
    digests = {f.id for f in sources.feeds if f.role == "digest"}
    rows = store.conn.execute(
        f"SELECT i.id, i.story_id, i.kind, i.source, i.metrics, s.last_item_at FROM items i "
        "JOIN stories s ON s.id = i.story_id WHERE s.merged_into IS NULL AND s.last_item_at >= ? AND i.relevant = 1",
        (since,),
    ).fetchall()
    repo_ids = [r["id"] for r in rows if r["kind"] == "repo"]
    velocity = star_velocities(store, repo_ids, now)

    raw: dict[str, dict[str, float]] = defaultdict(lambda: dict.fromkeys(FEATURES, 0.0))
    outlets: dict[str, set] = defaultdict(set)
    ctry: dict[str, set] = defaultdict(set)
    aggs: dict[str, set] = defaultdict(set)
    digs: dict[str, set] = defaultdict(set)
    last_at: dict[str, str] = {}
    for r in rows:
        sid, met = r["story_id"], json.loads(r["metrics"] or "{}")
        f = raw[sid]
        last_at[sid] = r["last_item_at"]
        if r["kind"] == "news":
            outlets[sid].add(r["source"])
            if countries.get(r["source"]):
                ctry[sid].add(countries[r["source"]])
        elif r["kind"] == "hn":
            f["hn_points"] += met.get("points", 0)
        elif r["kind"] == "repo":
            f["star_velocity"] += velocity.get(r["id"], 0.0)
        elif r["kind"] in ("model", "dataset", "space"):
            f["hf_trending"] += met.get("trending_score", 0) or 0
        elif r["kind"] == "paper":
            f["hf_trending"] += met.get("likes", 0) or 0
        elif r["kind"] == "social":
            f["social"] += 1 + (met.get("likes") or 0) + (met.get("reposts") or 0)
        elif r["kind"] == "aggregator":
            aggs[sid].add(r["source"])
        elif r["kind"] == "newsletter" and r["source"] in digests:
            digs[sid].add(r["source"])
    for sid, f in raw.items():
        f["outlets"], f["countries"] = len(outlets[sid]), len(ctry[sid])
        f["aggregators"], f["digests"] = len(aggs[sid]), len(digs[sid])

    ranks = {
        feat: (log_share if feat in COUNT_FEATURES else percentile_ranks)({sid: f[feat] for sid, f in raw.items()})
        for feat in FEATURES
    }
    scores = []
    for sid, f in raw.items():
        base = sum(m.weights.get(feat, 0.0) * ranks[feat][sid] for feat in FEATURES)
        age_h = max(0.0, (now - parse_iso(last_at[sid])).total_seconds() / 3600)
        decay = 0.5 ** (age_h / m.half_life_hours)
        scores.append(StoryScore(sid, round(base * decay, 4), {k: round(v, 2) for k, v in f.items()}, last_at[sid]))
    scores.sort(key=lambda s: (s.score, s.features["outlets"], s.story_id), reverse=True)
    with store.conn:
        store.conn.executemany(
            "UPDATE stories SET momentum = ?, features = ?, scored_at = ? WHERE id = ?",
            [(s.score, json.dumps(s.features, sort_keys=True), iso(now), s.story_id) for s in scores],
        )
    return scores


def rising(store: Store, settings: Settings, now: datetime) -> list[RisingItem]:
    """Fastest-rising builder items, with a quota per kind so one kind can't fill the list."""
    since = iso(now - timedelta(hours=settings.rising.window_hours))
    rows = store.conn.execute(
        "SELECT id, kind, source, title, url, metrics, extra, story_id FROM items "
        f"WHERE kind IN ({','.join('?' * len(RISING_KINDS))}) AND relevant = 1 AND last_seen_at >= ? AND source != 'openrouter'",
        (*RISING_KINDS, since),
    ).fetchall()
    velocity = star_velocities(store, [r["id"] for r in rows if r["kind"] == "repo"], now)
    by_kind: dict[str, list[RisingItem]] = defaultdict(list)
    for r in rows:
        met = json.loads(r["metrics"] or "{}")
        if r["kind"] == "repo":
            val = velocity.get(r["id"], 0.0)
            signal = f"+{val:,.0f} stars/day ({met.get('stars', 0):,} total)"
        elif r["kind"] == "paper":
            val = met.get("likes") or 0
            signal = f"{val} upvotes on HF Papers"
        else:
            val = met.get("trending_score") or 0
            signal = f"trending {val:,.0f} on Hugging Face ({met.get('likes', 0):,} likes)"
        if val > 0:
            by_kind[r["kind"]].append(
                RisingItem(r["id"], r["kind"], r["title"], r["url"], signal, float(val), r["story_id"], json.loads(r["extra"] or "{}"))
            )
    out = []
    for kind, quota in settings.rising.quota.items():
        items = sorted(by_kind.get(kind, []), key=lambda x: (x.score, x.item_id), reverse=True)[:quota]
        out += items
    return out

