"""Narratives: stories the press has covered on several Stockholm days in a row, told day by day.

A story keeps its ID while coverage continues (the cluster's rolling window), so a narrative is one story
ID whose news and commentary items fall on `min_days` or more consecutive local days. Digests don't count:
they summarize, they don't cover. No model calls: each day's numbers come from the stored items and labels,
its headlines from the day's articles, and its front-page line from that morning's edition when the story
was on it.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date as Date, datetime, timedelta
from zoneinfo import ZoneInfo

from quiet_ai.config import Settings, SourcesConfig
from quiet_ai.pipeline.cluster import EVENT_AT
from quiet_ai.pipeline.edition import STANCES, data_since, stance_summary
from quiet_ai.pipeline.stories import representative_title, source_names
from quiet_ai.store.db import Store

STANCE_KEYS = [*map(str, STANCES), "unclear", "unlabeled"]


def _stance_key(stance: int | None, confidence: str | None, labeled: bool) -> str:
    if not labeled or stance is None:
        return "unlabeled"
    if confidence == "low":
        return "unclear"
    return str(stance)


def stance_mean(counts: dict[str, int]) -> float | None:
    """Mean of the confident labels on the -2..+2 scale, as on the card's stance chart."""
    n = sum(counts.get(str(k), 0) for k in STANCES)
    return round(sum(k * counts.get(str(k), 0) for k in STANCES) / n, 2) if n else None


def streak(dates: list[str]) -> int:
    """Longest run of consecutive dates (ISO strings, sorted)."""
    best = run = 0
    prev = None
    for d in dates:
        cur = Date.fromisoformat(d)
        run = run + 1 if prev is not None and cur - prev == timedelta(days=1) else 1
        best, prev = max(best, run), cur
    return best


def trend(first: float | None, last: float | None) -> str | None:
    """A few words for how the stance moved from the first covered day to the last."""
    if first is None or last is None:
        return None
    d = last - first
    if d <= -0.3:
        return "turned more critical"
    if d >= 0.3:
        return "turned more positive"
    return "held steady"


def _num(key: str) -> int | None:
    return int(key) if key.lstrip("-").isdigit() else None


_WORD = re.compile(r"[^\W\d_]{4,}")
_COMMON = {"that", "this", "with", "from", "after", "about", "into", "over", "will", "what", "says", "said", "have", "their",
           "more", "than", "they", "been", "when", "were", "could", "would", "amid", "news"}
TREND_MIN_LABELS = 3  # a day needs this many confident labels to anchor the trend


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "")} - _COMMON


def _pick_headlines(items: list[dict], n: int) -> list[dict]:
    """Up to n headlines from different outlets that represent the day: ranked by how many words they share
    with the day's other headlines (so stray items that joined the story sink), English originals first,
    taking a different stance where the top ones allow it. Shown from critical to positive."""
    by_outlet: dict[str, dict] = {}
    for it in sorted(items, key=lambda i: (not (i["lang"] in (None, "en") or i["title_en"]), i["at"])):
        by_outlet.setdefault(it["source"], it)
    cands = list(by_outlet.values())
    words = [_words(c["title_en"] or c["title"]) for c in cands]
    day_words = Counter(w for ws in (_words(i["title_en"] or i["title"]) for i in items) for w in ws)
    central = [sum(day_words[w] - 1 for w in ws) / (len(ws) ** 0.5 or 1) for ws in words]
    order = sorted(range(len(cands)), key=lambda i: (-central[i], i))
    ranked = [cands[i] for i in order]
    on_topic = [cands[i] for i in order[: n * 2] if central[i] > 0]  # shares words with the day's other headlines
    picks: list[dict] = []
    for c in on_topic:  # one per stance first...
        if len(picks) < n and c["stance_key"] not in {p["stance_key"] for p in picks}:
            picks.append(c)
    for c in ranked:  # ...then the most central of the rest
        if len(picks) < n and all(c is not p for p in picks):
            picks.append(c)
    return sorted(picks, key=lambda c: (9 if _num(c["stance_key"]) is None else _num(c["stance_key"]), c["at"]))


def _front_pages(store: Store, dates: set[str]) -> dict[str, dict[str, dict]]:
    """date -> story id -> {rank, headline, coverage} from that morning's front-page edition."""
    if not dates:
        return {}
    out: dict[str, dict[str, dict]] = {}
    marks = ",".join("?" * len(dates))
    for r in store.conn.execute(f"SELECT date, data FROM editions WHERE date IN ({marks})", sorted(dates)):
        stories = json.loads(r["data"]).get("stories", [])
        out[r["date"]] = {s["id"]: {"rank": s.get("rank"), "headline": s.get("headline"),
                                    "coverage": (s.get("summary") or {}).get("coverage")} for s in stories}
    return out


def detect(store: Store, settings: Settings, sources: SourcesConfig, now: datetime) -> list[dict]:
    """Every narrative in the database, ongoing first, then by last covered day and outlets (newest first)."""
    cfg = settings.narratives
    zone = ZoneInfo(settings.site.timezone)
    today = now.astimezone(zone).date()
    names = source_names(sources)
    countries = {f.id: f.country for f in sources.feeds} | {g.id: g.country for g in sources.gdelt_outlets}
    digests = {f.id for f in sources.feeds if f.role == "digest"}
    rows = store.conn.execute(
        f"SELECT i.id, i.story_id, i.source, i.kind, i.url, i.title, i.title_en, i.lang, {EVENT_AT} AS at, "
        "l.item_id AS labeled, l.stance, l.confidence FROM items i JOIN stories s ON s.id = i.story_id "
        "LEFT JOIN item_labels l ON l.item_id = i.id "
        "WHERE s.merged_into IS NULL AND i.relevant = 1 AND i.dup_of IS NULL AND i.kind IN ('news', 'newsletter')"
    ).fetchall()
    per_story: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r["source"] in digests or not r["at"]:
            continue
        day = datetime.fromisoformat(r["at"]).astimezone(zone).date().isoformat()
        if day > today.isoformat():
            continue
        per_story[r["story_id"]][day].append({
            "source": r["source"], "url": r["url"], "title": r["title"], "title_en": r["title_en"], "lang": r["lang"], "at": r["at"],
            "stance_key": _stance_key(r["stance"], r["confidence"], r["labeled"] is not None),
        })
    qualified = {sid: days for sid, days in per_story.items() if streak(sorted(days)) >= cfg.min_days}
    if not qualified:
        return []
    started = data_since(store)
    start_day = datetime.fromisoformat(started).astimezone(zone).date().isoformat() if started else None
    all_dates = {d for days in qualified.values() for d in days}
    fronts = _front_pages(store, all_dates)
    out = []
    for sid, days in qualified.items():
        dates = sorted(days)
        first, last = Date.fromisoformat(dates[0]), Date.fromisoformat(dates[-1])
        timeline = []
        total = Counter()
        outlets: set[str] = set()
        for i in range((last - first).days + 1):
            d = (first + timedelta(days=i)).isoformat()
            items = days.get(d, [])
            front = fronts.get(d, {}).get(sid)
            if not items:
                timeline.append({"date": d, "quiet": True, "outlets": 0, "items": 0, "mean": None, "stance": {}, "front": front, "headlines": []})
                continue
            st = Counter(it["stance_key"] for it in items)
            total.update(st)
            srcs = {it["source"] for it in items}
            outlets |= srcs
            timeline.append({
                "date": d, "quiet": False, "items": len(items), "outlets": len(srcs),
                "countries": len({countries[s] for s in srcs if countries.get(s)}),
                "stance": {k: st.get(k, 0) for k in STANCE_KEYS},
                "mean": stance_mean(st), "stance_summary": stance_summary({k: st.get(k, 0) for k in map(str, STANCES)}),
                "partial": bool(start_day and d < start_day), "today": d == today.isoformat(), "front": front,
                "headlines": [{"outlet": names.get(h["source"], h["source"]), "country": countries.get(h["source"]), "url": h["url"],
                               "title": h["title_en"] or h["title"], "original": h["title"] if h["title_en"] and h["title_en"] != h["title"] else None,
                               "lang": h["lang"], "stance": h["stance_key"]} for h in _pick_headlines(items, cfg.headlines_per_day)],
            })
        means = [t["mean"] for t in timeline if t["mean"] is not None and sum(t["stance"].get(str(k), 0) for k in STANCES) >= TREND_MIN_LABELS]
        latest_front = next((t["front"] for t in reversed(timeline) if t.get("front")), None)
        summary = store.conn.execute("SELECT data FROM story_summaries WHERE story_id = ?", (sid,)).fetchone()
        headline = ((latest_front or {}).get("headline") or (json.loads(summary["data"]).get("headline") if summary else None)
                    or representative_title(store, sid) or sid)
        overall = {k: total.get(k, 0) for k in STANCE_KEYS}
        out.append({
            "id": sid, "headline": headline, "first": dates[0], "last": dates[-1],
            "days": (last - first).days + 1, "covered": len(dates), "streak": streak(dates),
            "ongoing": (today - last).days <= cfg.ongoing_days,
            "outlets": len(outlets), "countries": len({countries[s] for s in outlets if countries.get(s)}),
            "stance": overall, "mean": stance_mean(overall), "stance_summary": stance_summary({k: overall[k] for k in map(str, STANCES)}),
            "first_mean": means[0] if len(means) > 1 else None, "last_mean": means[-1] if len(means) > 1 else None,
            "trend": trend(means[0], means[-1]) if len(means) > 1 else None,
            "front_days": sum(1 for t in timeline if t.get("front")),
            "timeline": timeline,
        })
    out.sort(key=lambda n: (n["ongoing"], n["last"], n["outlets"], n["id"]), reverse=True)
    return out


def compact(n: dict) -> dict:
    """What an edition keeps of a narrative: enough for the front-page row and its small chart."""
    keep = ("id", "headline", "first", "last", "days", "covered", "streak", "ongoing", "outlets", "countries", "mean",
            "first_mean", "last_mean", "trend")
    return {**{k: n[k] for k in keep},
            "timeline": [{"date": t["date"], "quiet": t["quiet"], "outlets": t["outlets"], "mean": t["mean"]} for t in n["timeline"]]}


def by_story(narratives: list[dict]) -> dict[str, dict]:
    """story id -> what a front-page card needs to show its narrative's seal: the days so far (first to latest
    covered day), the dates, outlets and the compact day by day."""
    out = {}
    for n in narratives:
        c = compact(n)
        out[n["id"]] = {k: c[k] for k in ("id", "days", "first", "last", "outlets", "ongoing", "timeline")}
    return out
