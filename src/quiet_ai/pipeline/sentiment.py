"""The sentiment index, one per desk (AI, energy, ...): per local day, the mean stance (-2..+2) of the coverage, overall and
per track. Outlet-balanced: each outlet's confident labels are averaged first (weighted by
confidence), then outlets are averaged, so one high-volume outlet counts as one voice. An outlet with
`index_from` (one in a language the site has just started reading) counts only from that day."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from quiet_ai.config import Settings, SourcesConfig
from quiet_ai.store.db import Store, iso

TRACKS = ("all", "technical", "political", "economic")


def waiting(sources: SourcesConfig) -> dict[str, str]:
    """Outlets whose labels don't count in the index yet: source id -> the first local date that counts."""
    return {f.id: f.index_from.isoformat() for f in sources.feeds if f.index_from}


def _rows(store: Store, since: datetime, desk: str = "ai") -> list:
    return store.conn.execute(
        "SELECT i.source, MIN(COALESCE(i.published_at, i.first_seen_at), i.first_seen_at) AS at, l.track, l.stance, l.confidence "
        "FROM item_labels l JOIN items i ON i.id = l.item_id "
        "WHERE l.task = 'news' AND l.stance IS NOT NULL AND i.relevant = 1 AND COALESCE(i.desk, 'ai') = ? AND i.dup_of IS NULL "
        "AND i.first_seen_at >= ?",
        (desk, iso(since)),
    ).fetchall()


def _daily(rows: list, settings: Settings, first_day: str, outlets: set[str] | None = None,
           wait: dict[str, str] | None = None) -> dict[tuple[str, str], tuple[float, int, int]]:
    """(local date, track) -> (value, outlets, labels) for the days from `first_day` with at least `min_outlets`
    outlets. `outlets` keeps only those sources (a region's or a country's); None keeps all. `wait` (from `waiting`)
    leaves out an outlet's labels before the day it starts to count."""
    wait = wait or {}
    s = settings.sentiment
    zone = ZoneInfo(settings.site.timezone)
    # (date, track) -> outlet -> [weighted sum, weight, n]
    acc: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0]))
    for r in rows:
        if outlets is not None and r["source"] not in outlets:
            continue
        w = s.confidence_weights.get(r["confidence"] or "", 0.0)
        if not w or not r["track"]:
            continue
        day = datetime.fromisoformat(r["at"]).astimezone(zone).date().isoformat()
        if day < first_day or day < wait.get(r["source"], ""):
            continue
        for track in ("all", r["track"]):
            a = acc[(day, track)][r["source"]]
            a[0] += w * r["stance"]
            a[1] += w
            a[2] += 1
    out = {}
    for key, voices in acc.items():
        if len(voices) < s.min_outlets:
            continue
        means = [ws / wt for ws, wt, _ in voices.values() if wt]
        out[key] = (round(sum(means) / len(means), 3), len(voices), sum(int(n) for *_, n in voices.values()))
    return out


def compute(store: Store, settings: Settings, now: datetime, wait: dict[str, str] | None = None, desk: str = "ai") -> int:
    """Recompute one desk's last `recompute_days` local dates. Returns rows written."""
    s = settings.sentiment
    zone = ZoneInfo(settings.site.timezone)
    rows = _rows(store, now - timedelta(days=s.recompute_days + 1), desk)
    first_day = (now.astimezone(zone) - timedelta(days=s.recompute_days - 1)).date().isoformat()
    # Days before collection started only hold the feeds' backlog: too partial to count.
    started = store.conn.execute("SELECT MIN(first_seen_at) FROM items").fetchone()[0]
    if started:
        first_day = max(first_day, datetime.fromisoformat(started).astimezone(zone).date().isoformat())
    out = [(desk, day, track, value, n, labels, iso(now)) for (day, track), (value, n, labels) in _daily(rows, settings, first_day, wait=wait).items()]
    with store.conn:
        store.conn.execute("DELETE FROM sentiment_daily WHERE desk = ? AND (date >= ? OR date < ?)", (desk, first_day, started[:10] if started else ""))
        store.conn.executemany("INSERT INTO sentiment_daily(desk, date, track, value, outlets, labels, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)", out)
    return len(out)


def by_place(store: Store, settings: Settings, outlet_country: dict[str, str | None], places: dict[str, list[str]],
             first_day: str, wait: dict[str, str] | None = None, desk: str = "ai") -> dict[str, dict[tuple[str, str], tuple[float, int, int]]]:
    """The daily index again, once per place (a region or a country, as country codes), from that place's outlets
    only: place -> (date, track) -> (value, outlets, labels). Same rules as the overall index, so a day counts
    only when at least `min_outlets` outlets there were labeled."""
    zone = ZoneInfo(settings.site.timezone)
    since = datetime.fromisoformat(first_day).replace(tzinfo=zone) - timedelta(days=1)
    rows = _rows(store, since, desk)
    return {key: _daily(rows, settings, first_day, {o for o, c in outlet_country.items() if c in codes}, wait)
            for key, codes in places.items()}


def labeled_outlets(store: Store, settings: Settings, day: str, wait: dict[str, str] | None = None) -> set[str]:
    """The outlets whose confident labels counted in the index on a local day (for the About page's share by country)."""
    zone = ZoneInfo(settings.site.timezone)
    since = datetime.fromisoformat(day).replace(tzinfo=zone) - timedelta(days=1)
    wait = wait or {}
    out = set()
    for r in _rows(store, since):
        if not settings.sentiment.confidence_weights.get(r["confidence"] or "", 0.0) or not r["track"]:
            continue
        d = datetime.fromisoformat(r["at"]).astimezone(zone).date().isoformat()
        if d == day and d >= wait.get(r["source"], ""):
            out.add(r["source"])
    return out


def place_value(daily: dict[tuple[str, str], tuple[float, int, int]], dates: list[str]) -> dict:
    """A place's index over a view: per track, the mean of its daily values on `dates` (the days the overall
    figure averages), skipping days with too few outlets there. `days` is how many days had a value."""
    values = {}
    for t in TRACKS:
        pts = [daily[(d, t)][0] for d in dates if (d, t) in daily]
        values[t] = round(sum(pts) / len(pts), 2) if pts else None
    return {"values": values, "words": describe(values["all"]), "days": sum((d, "all") in daily for d in dates)}


def history(store: Store, days: int | None = None, desk: str = "ai") -> dict[str, list[dict]]:
    """One desk's index: track -> [{date, value, outlets, labels}] oldest first."""
    q = "SELECT * FROM sentiment_daily WHERE desk = ?"
    args: tuple = (desk,)
    if days:
        q += " AND date >= date('now', ?)"
        args = (desk, f"-{days} days")
    out: dict[str, list[dict]] = {t: [] for t in TRACKS}
    for r in store.conn.execute(q + " ORDER BY date", args):
        out.setdefault(r["track"], []).append({"date": r["date"], "value": r["value"], "outlets": r["outlets"], "labels": r["labels"]})
    return out


def period_value(hist: dict[str, list[dict]], last_n_days: int) -> dict[str, float | None]:
    """Mean of the daily values over the last n days that have data, per track."""
    out = {}
    for t, pts in hist.items():
        recent = pts[-last_n_days:] if pts else []
        out[t] = round(sum(p["value"] for p in recent) / len(recent), 2) if recent else None
    return out


def describe(value: float | None) -> str | None:
    if value is None:
        return None
    if value <= -0.5:
        return "critical"
    if value <= -0.15:
        return "leaning critical"
    if value < 0.15:
        return "neutral"
    if value < 0.5:
        return "leaning positive"
    return "positive"
