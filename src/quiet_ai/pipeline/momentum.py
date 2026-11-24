"""Momentum: rank stories by cross-source signals, and pick the fastest-rising builder items.

Two kinds of features, each scaled to 0..1 across the active stories:
- Counts (outlets, countries, aggregators, digests) are log-scaled against the window's
  maximum, so 14 outlets stays clearly ahead of 2.
- Volumes from one platform (HN points, star velocity, HF trending, social engagement) are
  percentile ranks, so no single source can dominate: 3,000 HN points count no more than
  being the top HN story of the window.
The weighted sum is decayed by the age of the story's latest item.

Every view (24 hours, 7 days, ...) scores only the items inside its period, and longer views
merge stories that went quiet and came back.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from quiet_ai.config import PeriodSettings, Settings, SourcesConfig
from quiet_ai.pipeline.cluster import EVENT_AT
from quiet_ai.pipeline.embed import from_blob, normalize
from quiet_ai.store.db import Store, iso
from quiet_ai.terms import term_key
from quiet_ai.text import parse_iso

FEATURES = ("outlets", "countries", "hn_points", "star_velocity", "hf_trending", "social", "aggregators", "digests")
COUNT_FEATURES = ("outlets", "countries", "aggregators", "digests")
RISING_KINDS = ("repo", "model", "dataset", "space", "paper")


@dataclass
class StoryScore:
    story_id: str  # a story ID, or "<id>@<period>" for stories merged in a longer view
    score: float
    features: dict[str, float]
    last_at: str
    members: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.members:
            self.members = [self.story_id]


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


def star_velocities(store: Store, item_ids: list[str], now: datetime, hours: float = 48) -> dict[str, float]:
    """Stars gained per day, measured across runs once there are 6+ hours of snapshots inside
    the window (at least 48h); before that, the lifetime average (stars per day since creation)."""
    if not item_ids:
        return {}
    snaps: dict[str, list[tuple[str, int]]] = defaultdict(list)
    created: dict[str, str] = {}
    for i in range(0, len(item_ids), 500):
        chunk = item_ids[i : i + 500]
        marks = ",".join("?" * len(chunk))
        for r in store.conn.execute(f"SELECT item_id, observed_at, metrics FROM metric_snapshots WHERE item_id IN ({marks}) ORDER BY observed_at", chunk):
            stars = json.loads(r["metrics"]).get("stars")
            if stars is not None:
                snaps[r["item_id"]].append((r["observed_at"], stars))
        created.update({r["id"]: r["published_at"] for r in store.conn.execute(f"SELECT id, published_at FROM items WHERE id IN ({marks})", chunk)})
    out = {}
    since = iso(now - timedelta(hours=max(48, hours)))
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


def _story_entities(store: Store, story_ids: list[str], aliases: dict[str, str], top: int = 5) -> dict[str, set[str]]:
    """Each story's most frequent names, from its items' labels."""
    counts: dict[str, Counter] = defaultdict(Counter)
    for i in range(0, len(story_ids), 500):
        chunk = story_ids[i : i + 500]
        rows = store.conn.execute(
            f"SELECT i.story_id, l.data FROM items i JOIN item_labels l ON l.item_id = i.id WHERE i.story_id IN ({','.join('?' * len(chunk))})",
            chunk,
        )
        for r in rows:
            for e in json.loads(r["data"]).get("entities", []):
                counts[r["story_id"]][term_key(e, aliases)] += 1
    return {sid: {k for k, _ in c.most_common(top)} for sid, c in counts.items()}


def merge_groups(store: Store, settings: Settings, activity: dict[str, tuple], period: PeriodSettings) -> dict[str, list[str]]:
    """For longer views: stories about the same thing that went quiet and came back (and so
    got separate IDs) are shown as one. A story joins a group when its centroid is within
    `period_merge_threshold` of the group's and they share one of their top names.
    Returns display key -> member story IDs (most active first)."""
    site = settings.site
    order = sorted(activity, key=lambda sid: activity[sid], reverse=True)
    candidates, rest = order[: site.period_merge_candidates], order[site.period_merge_candidates :]
    vecs = {
        r["id"]: from_blob(r["centroid"]) for r in store.conn.execute(
            f"SELECT id, centroid FROM stories WHERE id IN ({','.join('?' * len(candidates))}) AND centroid IS NOT NULL", candidates
        )
    } if candidates else {}
    ents = _story_entities(store, candidates, {k.lower(): v for k, v in site.term_aliases.items()})
    groups: list[dict] = []
    for sid in candidates:
        v = vecs.get(sid)
        best, best_sim = None, site.period_merge_threshold
        if v is not None and ents.get(sid):
            unit = normalize(v[None, :])[0]
            for g in groups:
                sim = float(normalize(g["mean"][None, :])[0] @ unit)
                if sim >= best_sim and g["ents"] & ents[sid]:
                    best, best_sim = g, sim
        weight = activity[sid][-1] or 1
        if best:
            best["mean"] = (best["mean"] * best["weight"] + v * weight) / (best["weight"] + weight)
            best["weight"] += weight
            best["ents"] |= ents[sid]
            best["members"].append(sid)
        else:
            groups.append({"mean": v if v is not None else None, "weight": weight, "ents": set(ents.get(sid, ())), "members": [sid]})
            if v is None:
                groups[-1]["mean"] = None
    out: dict[str, list[str]] = {}
    for g in groups:
        key = g["members"][0] if len(g["members"]) == 1 else f"{g['members'][0]}@{period.key}"
        out[key] = g["members"]
    for sid in rest:
        out[sid] = [sid]
    return out


def score_stories(store: Store, settings: Settings, sources: SourcesConfig, now: datetime, period: PeriodSettings | None = None) -> list[StoryScore]:
    """Rank stories by activity inside a period (the front-page period by default)."""
    m = settings.momentum
    first = settings.site.periods[0]
    period = period or first
    since = iso(now - timedelta(hours=period.hours))
    countries = {f.id: f.country for f in sources.feeds} | {g.id: g.country for g in sources.gdelt_outlets}
    digests = {f.id for f in sources.feeds if f.role == "digest"}
    rows = store.conn.execute(
        f"SELECT i.id, i.story_id, i.kind, i.source, i.metrics, {EVENT_AT} AS event_at FROM items i "
        f"JOIN stories s ON s.id = i.story_id WHERE s.merged_into IS NULL AND i.relevant = 1 AND i.dup_of IS NULL AND {EVENT_AT} >= ?",
        (since,),
    ).fetchall()
    if not rows:
        return []
    activity: dict[str, tuple] = {}
    per_story: dict[str, list] = defaultdict(list)
    for r in rows:
        per_story[r["story_id"]].append(r)
    for sid, rs in per_story.items():
        activity[sid] = (len({r["source"] for r in rs if r["kind"] == "news"}), len(rs))
    groups = merge_groups(store, settings, activity, period) if period.merge else {sid: [sid] for sid in per_story}
    key_of = {sid: key for key, members in groups.items() for sid in members}
    velocity = star_velocities(store, [r["id"] for r in rows if r["kind"] == "repo"], now, period.hours)

    raw: dict[str, dict[str, float]] = defaultdict(lambda: dict.fromkeys(FEATURES, 0.0))
    outlets: dict[str, set] = defaultdict(set)
    ctry: dict[str, set] = defaultdict(set)
    aggs: dict[str, set] = defaultdict(set)
    digs: dict[str, set] = defaultdict(set)
    last_at: dict[str, str] = {}
    for r in rows:
        key, met = key_of[r["story_id"]], json.loads(r["metrics"] or "{}")
        f = raw[key]
        last_at[key] = max(last_at.get(key, ""), r["event_at"])
        if r["kind"] == "news":
            outlets[key].add(r["source"])
            if countries.get(r["source"]):
                ctry[key].add(countries[r["source"]])
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
            aggs[key].add(r["source"])
        elif r["kind"] == "newsletter" and r["source"] in digests:
            digs[key].add(r["source"])
    for key, f in raw.items():
        f["outlets"], f["countries"] = len(outlets[key]), len(ctry[key])
        f["aggregators"], f["digests"] = len(aggs[key]), len(digs[key])

    ranks = {
        feat: (log_share if feat in COUNT_FEATURES else percentile_ranks)({k: f[feat] for k, f in raw.items()})
        for feat in FEATURES
    }
    scores = []
    for key, f in raw.items():
        base = sum(m.weights.get(feat, 0.0) * ranks[feat][key] for feat in FEATURES)
        age_h = max(0.0, (now - parse_iso(last_at[key])).total_seconds() / 3600)
        decay = 0.5 ** (age_h / period.half_life_hours)
        scores.append(StoryScore(key, round(base * decay, 4), {k: round(v, 2) for k, v in f.items()}, last_at[key], groups[key]))
    scores.sort(key=lambda s: (s.score, s.features["outlets"], s.story_id), reverse=True)
    if period.key == first.key:
        with store.conn:
            store.conn.executemany(
                "UPDATE stories SET momentum = ?, features = ?, scored_at = ? WHERE id = ?",
                [(s.score, json.dumps(s.features, sort_keys=True), iso(now), s.story_id) for s in scores if len(s.members) == 1],
            )
    return scores


def rising(store: Store, settings: Settings, now: datetime, hours: float | None = None) -> list[RisingItem]:
    """Fastest-rising builder items seen in a listing within the period, with a quota per kind."""
    hours = hours or settings.rising.window_hours
    since = iso(now - timedelta(hours=max(hours, 24)))
    rows = store.conn.execute(
        "SELECT id, kind, source, title, url, metrics, extra, story_id FROM items "
        f"WHERE kind IN ({','.join('?' * len(RISING_KINDS))}) AND relevant = 1 AND last_seen_at >= ? AND source != 'openrouter'",
        (*RISING_KINDS, since),
    ).fetchall()
    velocity = star_velocities(store, [r["id"] for r in rows if r["kind"] == "repo"], now, hours)
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
        out += sorted(by_kind.get(kind, []), key=lambda x: (x.score, x.item_id), reverse=True)[:quota]
    return out
