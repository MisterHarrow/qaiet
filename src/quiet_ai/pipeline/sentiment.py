"""The AI sentiment index: per local day, the mean stance (-2..+2) of the coverage, overall and
per track. Outlet-balanced: each outlet's confident labels are averaged first (weighted by
confidence), then outlets are averaged, so one high-volume outlet counts as one voice."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from quiet_ai.config import Settings
from quiet_ai.store.db import Store, iso

TRACKS = ("all", "technical", "political", "economic")


def compute(store: Store, settings: Settings, now: datetime) -> int:
    """Recompute the last `recompute_days` local dates. Returns rows written."""
    s = settings.sentiment
    zone = ZoneInfo(settings.site.timezone)
    since = now - timedelta(days=s.recompute_days + 1)
    rows = store.conn.execute(
        "SELECT i.source, MIN(COALESCE(i.published_at, i.first_seen_at), i.first_seen_at) AS at, l.track, l.stance, l.confidence "
        "FROM item_labels l JOIN items i ON i.id = l.item_id "
        "WHERE l.task = 'news' AND l.stance IS NOT NULL AND i.relevant = 1 AND i.dup_of IS NULL AND i.first_seen_at >= ?",
        (iso(since),),
    ).fetchall()
    first_day = (now.astimezone(zone) - timedelta(days=s.recompute_days - 1)).date().isoformat()
    # Days before collection started only hold the feeds' backlog: too partial to count.
    started = store.conn.execute("SELECT MIN(first_seen_at) FROM items").fetchone()[0]
    if started:
        first_day = max(first_day, datetime.fromisoformat(started).astimezone(zone).date().isoformat())
    # (date, track) -> outlet -> [weighted sum, weight, n]
    acc: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0]))
    for r in rows:
        w = s.confidence_weights.get(r["confidence"] or "", 0.0)
        if not w or not r["track"]:
            continue
        day = datetime.fromisoformat(r["at"]).astimezone(zone).date().isoformat()
        if day < first_day:
            continue
        for track in ("all", r["track"]):
            a = acc[(day, track)][r["source"]]
            a[0] += w * r["stance"]
            a[1] += w
            a[2] += 1
    out = []
    for (day, track), outlets in acc.items():
        if len(outlets) < s.min_outlets:
            continue
        means = [ws / wt for ws, wt, _ in outlets.values() if wt]
        out.append((day, track, round(sum(means) / len(means), 3), len(outlets), sum(int(n) for *_, n in outlets.values()), iso(now)))
    with store.conn:
        store.conn.execute("DELETE FROM sentiment_daily WHERE date >= ? OR date < ?", (first_day, started[:10] if started else ""))
        store.conn.executemany("INSERT INTO sentiment_daily VALUES (?, ?, ?, ?, ?, ?)", out)
    return len(out)


def history(store: Store, days: int | None = None) -> dict[str, list[dict]]:
    """track -> [{date, value, outlets, labels}] oldest first."""
    q = "SELECT * FROM sentiment_daily"
    args: tuple = ()
    if days:
        q += " WHERE date >= date('now', ?)"
        args = (f"-{days} days",)
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
