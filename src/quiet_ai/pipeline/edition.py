"""Assemble the day's edition as plain data: the terminal view, the site (M4) and the
frozen daily archive (M5) all read this one structure."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from quiet_ai.config import PeriodSettings, Settings, SourcesConfig
from quiet_ai.pipeline import mentions as mentions_mod
from quiet_ai.pipeline.cluster import link_keys
from quiet_ai.pipeline.momentum import RisingItem, StoryScore
from quiet_ai.pipeline.stories import representative_title, representative_url, source_names
from quiet_ai.store.db import Store, iso
from quiet_ai.terms import term_key

STANCES = (-2, -1, 0, 1, 2)
_PRESS_KINDS = ("news", "newsletter")


def top_terms(store: Store, sources: SourcesConfig, settings: Settings, now, hours: float = 24, desk: str = "ai") -> list[dict]:
    """The names most outlets mentioned in the last `hours`, from the item labels.
    Counted once per outlet, so one outlet repeating a name doesn't inflate it."""
    s = settings.site
    aliases = {k.lower(): v for k, v in s.term_aliases.items()}
    stop = {w.lower() for w in s.term_stopwords}
    outlet_names = {f.name.lower() for f in sources.feeds} | {g.name.lower() for g in sources.gdelt_outlets}
    rows = store.conn.execute(
        "SELECT i.source, l.data FROM item_labels l JOIN items i ON i.id = l.item_id "
        "WHERE l.task = 'news' AND i.relevant = 1 AND COALESCE(i.desk, 'ai') = ? AND i.first_seen_at >= ?",
        (desk, iso(now - timedelta(hours=hours))),
    ).fetchall()
    outlets: dict[str, set] = defaultdict(set)
    spellings: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        for name in json.loads(r["data"]).get("entities", []):
            key = term_key(name, aliases)
            if not key or key in stop or key in outlet_names or len(key) < 2:
                continue
            outlets[key].add(r["source"])
            spellings[key][aliases.get(name.strip().lower(), name.strip())] += 1
    ranked = sorted(outlets.items(), key=lambda kv: (-len(kv[1]), kv[0]))[: s.terms_count]
    if not ranked:
        return []
    top = len(ranked[0][1])
    out = []
    for key, srcs in ranked:
        share = len(srcs) / top
        size = 4 if share >= 0.66 else 3 if share >= 0.4 else 2 if share >= 0.2 else 1
        out.append({"key": key, "label": spellings[key].most_common(1)[0][0], "outlets": len(srcs), "size": size})
    return out


def story_members(store: Store, story_ids: str | list[str]) -> list[dict]:
    """Items of one story, or of several stories shown together in a longer view."""
    ids = [story_ids] if isinstance(story_ids, str) else list(story_ids)
    rows = store.conn.execute(
        "SELECT i.id, i.kind, i.source, i.url, i.title, i.title_en, i.lang, i.published_at, i.metrics, i.extra, "
        "l.task, l.track, l.frame, l.stance, l.confidence, l.data AS label "
        f"FROM items i LEFT JOIN item_labels l ON l.item_id = i.id WHERE i.story_id IN ({','.join('?' * len(ids))}) "
        "AND i.relevant = 1 AND i.dup_of IS NULL ORDER BY i.published_at",
        ids,
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


def outlet_stances(press: list[dict]) -> Counter:
    """One stance per outlet, like the sentiment index: the mean of its confident labels in the story, rounded;
    "unclear" when it has only low-confidence ones, "unlabeled" when none. For the card's stripe, so an outlet that
    files many articles on one story counts once."""
    by_outlet: dict[str, list[dict]] = defaultdict(list)
    for m in press:
        by_outlet[m["source"]].append(m)
    out: Counter = Counter()
    for ms in by_outlet.values():
        sure = [m["stance"] for m in ms if m["label"] is not None and m["confidence"] != "low" and m["stance"] is not None]
        if sure:
            out[str(round(sum(sure) / len(sure)))] += 1
        else:
            out["unclear" if any(m["label"] is not None for m in ms) else "unlabeled"] += 1
    return out


def story_entry(store: Store, sources: SourcesConfig, score: StoryScore, rank: int,
                mentions: mentions_mod.Index = mentions_mod.EMPTY) -> dict[str, Any]:
    names = source_names(sources)
    feeds = {f.id: f for f in sources.feeds}
    countries = {f.id: f.country for f in sources.feeds} | {g.id: g.country for g in sources.gdelt_outlets}
    members = story_members(store, score.members)
    summary = store.conn.execute("SELECT data, prompt_version, model FROM story_summaries WHERE story_id = ?", (score.story_id,)).fetchone()
    summary_data = json.loads(summary["data"]) if summary else None

    press = [m for m in members if m["kind"] in _PRESS_KINDS and not (m["kind"] == "newsletter" and (feeds.get(m["source"]) and feeds[m["source"]].role == "digest"))]
    stance = Counter(_stance_key(m) for m in press)
    per_outlet = outlet_stances(press)
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
            "lang": m["lang"],
            "title": m["title"],
            "title_en": m["title_en"],
            "url": m["url"],
            "frame": m["frame"],
            "track": m["track"],
            "confidence": m["confidence"],
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
    # Links behind the counts in the Builders line: posts (most liked first) and each digest's issue.
    posts = sorted((m for m in members if m["kind"] == "social"),
                   key=lambda m: -((m["metrics"].get("likes") or 0) + (m["metrics"].get("reposts") or 0)))
    builders["posts"] = [{"url": m["url"], "title": m["title"], "source": names.get(m["source"], m["source"])} for m in posts]
    digest_links: dict[str, str] = {}
    for m in members:
        if m["kind"] == "newsletter" and feeds.get(m["source"]) and feeds[m["source"]].role == "digest":
            digest_links.setdefault(names.get(m["source"], m["source"]), m["url"])
    builders["digest_links"] = digest_links
    # X posts and Reddit threads a recap (AINews) linked next to one of this story's URLs, plus the
    # posts of recap bullets that joined the story by topic.
    talk = mentions.lookup(set().union(*(link_keys(m["kind"], m["url"], m["extra"]) for m in members)) if members else set(), names)
    recaps = [m for m in members if m["kind"] == "recap"]
    x = {p["url"]: p for p in talk["x"]}
    for m in recaps:
        for url in m["extra"].get("x", []):
            x.setdefault(url, {"url": url, "account": mentions_mod.account(url)})
    via = set(talk["via"]) | {mentions_mod.short_name(names.get(m["source"], m["source"])) for m in recaps}
    via_links = dict(talk["via_links"])
    for m in recaps:
        if m["extra"].get("issue"):
            via_links.setdefault(mentions_mod.short_name(names.get(m["source"], m["source"])), m["extra"]["issue"])
    builders |= {"x": list(x.values()), "reddit": talk["reddit"], "via": sorted(via), "via_links": via_links}
    headline = (summary_data or {}).get("headline") or representative_title(store, score.members[0]) or score.story_id
    # The card's link to its top source: the official post if a lab published one, else the press article
    # closest to the story's center (an English original first); a builders-only story links its top thread,
    # repository or model.
    by_url = {m["url"]: m for m in members}
    lead_url = representative_url(store, score.members[0])
    lead = by_url.get(lead_url) if lead_url else None
    if lead is None and press:
        lead = press[0]
    sources_out = []
    for m in [*(m for m in members if m["kind"] == "lab")][:1] + ([lead] if lead else []):
        sources_out.append({"outlet": names.get(m["source"], m["source"]), "url": m["url"], "title": m["title_en"] or m["title"],
                            "official": m["kind"] == "lab"})
    if not sources_out:
        for key, url_key, outlet in (("hn", "url", "Hacker News"), ("repos", "url", "GitHub"), ("models", "url", None), ("papers", "url", "Paper")):
            if builders[key]:
                b0 = builders[key][0]
                sources_out.append({"outlet": outlet or b0.get("source", ""), "url": b0[url_key], "title": b0["title"], "official": False})
                break
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
        "stance_outlets": {k: per_outlet.get(k, 0) for k in [*map(str, STANCES), "unclear", "unlabeled"]},
        "stance_summary": stance_summary({k: stance.get(k, 0) for k in map(str, STANCES)}),
        "coverage": [{"stance": k, "items": groups[k], "countries": _countries(groups[k])}
                     for k in [*map(str, STANCES), "unclear", "unlabeled"] if k in groups],
        "builders": builders,
        "builders_line": builders_line(builders),
        "source": sources_out[0] if sources_out else None,
        "items": sum(1 for m in members if m["kind"] != "recap"),  # recap bullets don't trigger new summaries
        "entities": sorted({e for m in members if m["label"] for e in m["label"].get("entities", [])}),
    }


def _countries(items: list[dict]) -> list[list]:
    """[[country code, outlets], ...], most outlets first: which countries a stance group's headlines come from."""
    counts = Counter(i["country"] for i in items if i.get("country"))
    return [[c, n] for c, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def stance_summary(stance: dict[str, int]) -> str | None:
    """A few words for the stance mix: 'mostly neutral', 'leans critical', 'split', ..."""
    counts = {int(k): v for k, v in stance.items() if k.lstrip("-").isdigit()}
    n = sum(counts.values())
    if n == 0:
        return None
    neg = sum(v for k, v in counts.items() if k < 0) / n
    pos = sum(v for k, v in counts.items() if k > 0) / n
    mean = sum(k * v for k, v in counts.items()) / n
    if neg >= 0.2 and pos >= 0.2:
        return "split"
    if mean <= -0.5:
        return "leans critical"
    if mean >= 0.5:
        return "leans positive"
    return "mostly neutral"


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
    if talk := mentions_mod.line({"x": b.get("x", []), "reddit": b.get("reddit", []), "via": b.get("via", [])}):
        parts.append(talk)
    return " · ".join(parts)


# Rising categories: what a project is (from its Haiku label), in display order.
RISING_CATEGORIES = [
    ("model", "Models"), ("agent", "Agents"), ("tool/library", "Tools & libraries"), ("infra", "Infrastructure"),
    ("dataset", "Datasets"), ("research paper", "Papers"), ("demo/app", "Apps & demos"),
]
# Before an item is labeled, its listing decides.
_DEFAULT_CATEGORY = {"repo": "tool/library", "model": "model", "dataset": "dataset", "space": "demo/app", "paper": "research paper"}


def rising_entries(store: Store, rising: list[RisingItem], mentions: mentions_mod.Index = mentions_mod.EMPTY,
                   names: dict[str, str] | None = None) -> list[dict]:
    out = []
    for r in rising:
        talk = mentions.lookup(link_keys(r.kind, r.url, r.extra), names)
        lab = store.conn.execute("SELECT data FROM item_labels WHERE item_id = ?", (r.item_id,)).fetchone()
        data = json.loads(lab["data"]) if lab else {}
        category = data.get("kind") or _DEFAULT_CATEGORY.get(r.kind, "tool/library")
        out.append({"id": r.item_id, "kind": r.kind, "category": category, "title": r.title, "url": r.url, "signal": r.signal,
                    "score": r.score, "what": data.get("what"), "why": data.get("why"), "story_id": r.story_id,
                    "talk": talk if (talk["x"] or talk["reddit"]) else None})
    return out


def rising_groups(entries: list[dict]) -> list[dict]:
    """Rising items grouped by category, in a fixed order, each group in listing-rank order."""
    groups = []
    for key, label in RISING_CATEGORIES:
        items = [e for e in entries if e["category"] == key]
        if items:
            slug = re.sub(r"[^a-z]+", "-", key).strip("-")
            groups.append({"key": key, "slug": slug, "label": label, "items": items})
    return groups


def weather_kind(period_key: str, desk: str = "ai") -> str:
    return f"weather:{period_key}" if desk == "ai" else f"weather:{desk}:{period_key}"


# Feeds carry roughly a day of older items, so the first run already covers about 24 hours.
FEED_BACKLOG_HOURS = 24


def data_since(store: Store) -> str | None:
    """When collection started (first item ever seen)."""
    row = store.conn.execute("SELECT MIN(first_seen_at) FROM items").fetchone()
    return row[0] if row else None


def covered_hours(store: Store, now: datetime) -> float | None:
    """How far back the data reasonably reaches: collection time plus the feeds' backlog."""
    since = data_since(store)
    if not since:
        return None
    return (now - datetime.fromisoformat(since)).total_seconds() / 3600 + FEED_BACKLOG_HOURS


def build(store: Store, settings: Settings, sources: SourcesConfig, scores: list[StoryScore], rising: list[RisingItem], now: datetime,
          top: int, period: PeriodSettings | None = None, desk: str = "ai") -> dict[str, Any]:
    period = period or settings.site.periods[0]
    weather = store.conn.execute("SELECT data FROM reports WHERE kind = ? ORDER BY id DESC LIMIT 1", (weather_kind(period.key, desk),)).fetchone()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    spend = store.conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls WHERE created_at >= ?", (iso(month_start),)).fetchone()[0]
    since = data_since(store)
    covered = covered_hours(store, now)
    partial = covered is not None and covered < period.hours
    terms = top_terms(store, sources, settings, now, period.hours, desk)
    keys = {t["key"] for t in terms}
    aliases = {k.lower(): v for k, v in settings.site.term_aliases.items()}
    talk = mentions_mod.load(store, [f.id for f in sources.feeds if f.mentions and f.enabled], now, period.hours)
    stories = [story_entry(store, sources, s, n, talk) for n, s in enumerate(scores[:top], 1)]
    for st in stories:
        st["terms"] = sorted({term_key(e, aliases) for e in st["entities"]} & keys)
        for t in terms:
            if t["key"] in st["terms"]:
                t["stories"] = t.get("stories", 0) + 1
    return {
        "generated_at": iso(now),
        "desk": desk,
        "period": {"key": period.key, "label": period.label, "hours": period.hours},
        "data_since": since if partial else None,  # set when the period reaches back before our first data
        "weather": json.loads(weather["data"])["sentence"] if weather else None,
        "terms": terms,
        "stories": stories,
        "rising": (rising_list := rising_entries(store, rising, talk, source_names(sources))),
        "rising_groups": rising_groups(rising_list),
        "llm": {"month_spend_usd": round(spend, 4), "budget_usd": settings.llm.monthly_budget_usd,
                "budget_reached": spend >= settings.llm.monthly_budget_usd},
    }
