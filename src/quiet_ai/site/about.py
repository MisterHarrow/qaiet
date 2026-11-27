"""Facts for the /about page, read from the config and the database so the page never drifts
from what the pipeline actually does."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from quiet_ai import evaluate
from quiet_ai.config import Account, Settings, SourcesConfig
from quiet_ai.pipeline import relevance, sentiment
from quiet_ai.pipeline.edition import data_since
from quiet_ai.pipeline.stories import source_names
from quiet_ai.regions import REGIONS
from quiet_ai.store.db import Store, iso

GROUP_NAMES = {
    "us-mainstream": "United States, mainstream and business",
    "us-left": "United States, left-leaning and opinion",
    "us-right": "United States, right-leaning and libertarian",
    "tech": "Technology trade press",
    "canada": "Canada",
    "latam": "Latin America",
    "uk-eu": "United Kingdom and Western Europe",
    "nordics": "Nordics",
    "cee": "Central and Eastern Europe",
    "africa": "Africa",
    "middle-east": "Middle East",
    "east-asia": "East Asia",
    "south-asia": "South Asia",
    "southeast-asia": "Southeast Asia",
    "oceania": "Oceania",
    "global": "Global",
    "desk-energy": "Energy press and agencies",
    "desk-biotech": "Biotech and health press and regulators",
    "desk-space": "Space press and agencies",
    "desk-food": "Farm and food press and agencies",
}
FEATURE_NAMES = {
    "outlets": "Number of news outlets covering it",
    "countries": "Number of countries those outlets are in",
    "hn_points": "Hacker News points",
    "star_velocity": "GitHub stars gained per day",
    "hf_trending": "Hugging Face trending score and paper upvotes",
    "social": "Bluesky and Hugging Face posts, with their likes and reposts, and X posts the AINews recap links",
    "aggregators": "Led on Techmeme or Memeorandum",
    "digests": "Picked up by AI newsletters that summarize the day",
}


def _health(store: Store, names: dict[str, str]) -> dict | None:
    run = store.conn.execute(
        "SELECT run_id, started_at FROM runs WHERE command = 'ingest' AND dry_run = 0 ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if not run:
        return None
    rows = store.conn.execute("SELECT source, fetcher, status, error FROM source_runs WHERE run_id = ?", (run["run_id"],)).fetchall()
    ok = [r for r in rows if r["status"] in ("ok", "not_modified")]
    failing = [{"name": names.get(r["source"].split(":")[0], r["source"]) if not r["source"].startswith("bluesky:") else r["source"],
                "status": r["status"].replace("_", " "), "error": r["error"]} for r in rows if r["status"] not in ("ok", "not_modified")]
    return {"at": run["started_at"], "total": len(rows), "ok": len(ok), "failing": failing}


AINEWS_X = Path(__file__).resolve().parents[3] / "config" / "ainews_x_accounts.yaml"


def ainews_x_accounts(path: Path = AINEWS_X) -> dict | None:
    """The X accounts AINews links to (a counted snapshot), for the sources list on /about."""
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None


def _us_share(store: Store, settings: Settings, sources: SourcesConfig, now: datetime) -> dict | None:
    """Of the news outlets that counted in yesterday's index, how many were American (the Limits section)."""
    country = {f.id: f.country for f in sources.feeds if f.kind == "news"} | {g.id: g.country for g in sources.gdelt_outlets}
    day = (now.astimezone(ZoneInfo(settings.site.timezone)) - timedelta(days=1)).date()
    outlets = [o for o in sentiment.labeled_outlets(store, settings, day.isoformat(), sentiment.waiting(sources)) if country.get(o)]
    if not outlets:
        return None
    return {"day": f"{day.day} {day:%B}", "n": len(outlets), "us": sum(country[o] == "US" for o in outlets)}


def _waiting(news: list, now: datetime) -> dict | None:
    """Outlets still waiting to join the index (`index_from` after today), and the last day of the wait."""
    dates = [f.index_from for f in news if f.index_from and f.index_from > now.date()]
    if not dates:
        return None
    last = max(dates)
    return {"n": len(dates), "until": f"{last.day} {last:%B}"}


def about_context(store: Store, settings: Settings, sources: SourcesConfig, accounts: list[Account], now: datetime,
                  gold: Path | None = None, crosscheck: Path | None = None) -> dict:
    names = source_names(sources)
    feeds = [f for f in sources.feeds if f.enabled]
    news = [f for f in feeds if f.kind == "news"]
    by_group: dict[str, list] = {}
    for f in sorted(news, key=lambda f: f.name.lower()):
        by_group.setdefault(f.group or "global", []).append({"name": f.name, "country": f.country, "language": f.language,
                                                             "type": f.type, "opt_out": not f.llm})
    groups = [{"key": k, "label": GROUP_NAMES.get(k, k), "outlets": by_group[k]} for k in GROUP_NAMES if k in by_group]
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    spend = store.conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls WHERE created_at >= ?", (iso(month_start),)).fetchone()[0]
    w = settings.momentum.weights
    audit = [dict(r, label=GROUP_NAMES.get(r["key"], r["key"])) for r in evaluate.audit(store, sources, by="group", min_n=20)
             if r["key"] != "other" and r["mean"] is not None]
    agreement = evaluate.score(store, evaluate.load_gold(gold)) if gold else {"n": 0}
    cross = evaluate.score(store, evaluate.load_gold(crosscheck), sources) if crosscheck else {"n": 0}
    if cross["n"]:
        meta = evaluate.load_meta(crosscheck)
        cross["model"] = evaluate.model_name(meta.get("model", "a larger model"))
        cross["date"] = str(meta.get("labeled_at", ""))[:10]
    g, s = settings.gap, settings.sentiment
    return {
        "ainews_x": ainews_x_accounts(),
        "gap": {"quiet_max_outlets": g.quiet_max_outlets, "builder_min_pct": round(g.builder_min_rank * 100),
                "loud_min_outlets": g.loud_min_outlets, "floors": g.builder_floors},
        "sentiment": {"min_outlets": s.min_outlets, "medium_weight": s.confidence_weights.get("medium")},
        "narratives": {"min_days": settings.narratives.min_days, "headlines_per_day": settings.narratives.headlines_per_day},
        "audit": audit,
        "audit_labels": sum(r["n"] for r in audit),
        "agreement": agreement,
        "crosscheck": cross,
        "generated_at": iso(now),
        "counts": {
            "outlets": len(news),
            "countries": len({f.country for f in news if f.country}),
            "languages": len({f.language for f in news}),
            "aggregators": sum(1 for f in feeds if f.kind == "aggregator"),
            "digests": sum(1 for f in feeds if f.kind == "newsletter" and f.role == "digest"),
            "commentary": sum(1 for f in feeds if f.kind == "newsletter" and f.role != "digest"),
            "labs": sum(1 for f in feeds if f.kind == "lab"),
            "bluesky": sum(1 for a in accounts if a.bluesky and a.bluesky_active),
            "gdelt": len(sources.gdelt_outlets),
        },
        "groups": groups,
        "desks": [{"key": d.key, "name": d.name, "subject": d.subject, "stance": d.stance, "builders": d.builders,
                   "prefix": "" if i == 0 else f"{d.key}/"} for i, d in enumerate(settings.active_desks)],
        "regions": [{"name": name, "n": sum(1 for f in news if f.country in codes)} for name, codes in REGIONS],
        "us_share": _us_share(store, settings, sources, now),
        "waiting": _waiting(news, now),
        "keyword_languages": len(relevance.LANGUAGES),
        "gdelt_outlets": [{"name": g.name, "country": g.country, "type": g.type} for g in sources.gdelt_outlets],
        "aggregators": [f.name for f in feeds if f.kind == "aggregator"],
        "newsletters": sorted((f.name for f in feeds if f.kind == "newsletter"), key=str.lower),
        "labs": sorted((f.name for f in feeds if f.kind == "lab"), key=str.lower),
        "opt_out": [f.name for f in feeds if not f.llm],
        "weights": [{"name": FEATURE_NAMES[k], "weight": round(v * 100)} for k, v in sorted(w.items(), key=lambda kv: -kv[1]) if k in FEATURE_NAMES],
        "periods": [{"label": p.label, "half_life_days": round(p.half_life_hours / 24, 1), "merge": p.merge} for p in settings.site.periods],
        "collect_every_hours": settings.schedule.collect_every_hours,
        "publish_at": settings.schedule.publish_at,
        "window_hours": settings.cluster.window_hours,
        "item_model": settings.llm.item_model,
        "story_model": settings.llm.story_model,
        "prompts": {
            "relevance": settings.relevance.prompt, "news": settings.analysis.news_prompt, "builder": settings.analysis.builder_prompt,
            "summary": settings.analysis.summary_prompt, "weather": settings.analysis.weather_prompt,
        },
        "embed_model": settings.embed.model,
        "budget": settings.llm.monthly_budget_usd,
        "spend": round(spend, 2),
        "data_since": data_since(store),
        "health": _health(store, names),
        "top_stories": settings.analysis.top_stories,
    }
