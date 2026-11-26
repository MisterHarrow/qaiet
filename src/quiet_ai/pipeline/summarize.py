"""Story summaries and the daily weather report, with Sonnet. Only the top stories are
summarized, and only again when they have grown since the last summary."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from quiet_ai.config import PeriodSettings, Settings, SourcesConfig
from quiet_ai.llm.client import LLM, LLMUnavailable, load_prompt
from quiet_ai.pipeline.edition import covered_hours, story_entry, weather_kind
from quiet_ai.pipeline.momentum import RisingItem, StoryScore
from quiet_ai.store.db import Store, iso

log = logging.getLogger(__name__)
STANCE_WORD = {"-2": "strongly critical", "-1": "critical", "0": "neutral", "1": "positive", "2": "strongly positive",
               "unclear": "unclear", "unlabeled": "unlabeled"}


class Frame(BaseModel):
    frame: str          # how these outlets frame the story: a short verb phrase ("Report the ruling plainly")
    outlets: list[str]  # outlet names as given in the material


class StorySummary(BaseModel):
    headline: str
    track: Literal["technical", "political", "economic"]
    coverage: str | None
    frames: list[Frame]  # story_summary_v4: the coverage split as a list, each framing with its outlets
    builders: str | None


class Weather(BaseModel):
    sentence: str


@dataclass
class SummaryStats:
    summarized: int = 0
    unchanged: int = 0
    weather: bool = False
    notes: list[str] = field(default_factory=list)


def material(entry: dict, max_headlines: int = 40) -> str:
    """What Sonnet sees for one story. Outlets that opted out of AI input appear by name only."""
    lines = [f"Story covered by {entry['outlets']} outlets in {entry['countries']} countries."]
    n = 0
    withheld = []
    for group in entry["coverage"]:
        for c in group["items"]:
            if c["llm_opt_out"]:
                withheld.append(c["outlet"])
                continue
            if n >= max_headlines:
                break
            title = c["title"] + (f" (English: {c['title_en']})" if c["title_en"] and c["title_en"] != c["title"] else "")
            label = STANCE_WORD.get(group["stance"], group["stance"])
            if c["frame"]:
                label += f", {c['frame']}"
            ev = f'; evidence: "{c["evidence"][0]}"' if c["evidence"] else ""
            lines.append(f"- {c['outlet']} ({c['country'] or '?'}), {c['kind']}: {title} [{label}{ev}]")
            n += 1
    if withheld:
        lines.append(f"Also covered by (text withheld at the publisher's request): {', '.join(withheld)}")
    b = entry["builders"]
    lines.append("Builder signals:")
    for h in b["hn"][:3]:
        lines.append(f"- Hacker News: {h['title']} ({h['points']} points, {h['comments']} comments)")
    for r in b["repos"][:5]:
        lines.append(f"- GitHub repo {r['title']} ({r['stars']} stars)")
    for m in b["models"][:5]:
        lines.append(f"- {m['source']}: {m['title']}")
    for p in b["papers"][:3]:
        lines.append(f"- Paper: {p['title']}")
    for o in b["official"][:2]:
        lines.append(f"- Official post ({o['source']}): {o['title']}")
    if b["social"]:
        lines.append(f"- {b['social']} posts on Bluesky / Hugging Face")
    if not any((b["hn"], b["repos"], b["models"], b["papers"], b["social"])):
        lines.append("- none")
    return "\n".join(lines)


def needs_refresh(prev, entry: dict, a, summary_prompt: str | None = None, news_prompt: str | None = None) -> bool:
    """Re-summarize when the story grew by about 30%, gained about 20% more outlets, or its labels
    changed underneath the summary (new label prompt, or stance counts moved by 20% / at least 3)."""
    summary_prompt, news_prompt = summary_prompt or a.summary_prompt, news_prompt or a.news_prompt
    if prev["prompt_version"] != summary_prompt:
        return True
    grow_items = max(a.resummarize_new_items, math.ceil(prev["item_count"] * a.resummarize_growth))
    grow_outlets = max(1, math.ceil(prev["outlet_count"] * a.resummarize_growth * 2 / 3))
    if entry["items"] >= prev["item_count"] + grow_items or entry["outlets"] >= prev["outlet_count"] + grow_outlets:
        return True
    basis = json.loads(prev["data"]).get("basis") or {}
    if basis.get("news_prompt") != news_prompt:
        return True
    old = basis.get("stance") or {}
    # Half the L1 distance = how many labels changed bucket (each move counts out of one, into another).
    moved = sum(abs(entry["stance"].get(k, 0) - old.get(k, 0)) for k in set(old) | set(entry["stance"])) / 2
    return moved >= max(3, 0.2 * sum(old.values()))


def desk_line(settings: Settings, desk: str) -> str:
    """The first line of the material on desks other than AI (whose prompts were written for AI alone)."""
    d = settings.desk(desk)
    return f"Desk: {d.name}" + (f" ({d.subject})" if d.subject else "") + "\n"


def summarize_top(store: Store, settings: Settings, sources: SourcesConfig, llm: LLM, scores: list[StoryScore], now: datetime,
                  desk: str = "ai") -> SummaryStats:
    a = settings.analysis
    stats = SummaryStats()
    summary_prompt, news_prompt = settings.summary_prompt(desk), settings.news_prompt(desk)
    system = load_prompt(summary_prompt)
    head = desk_line(settings, desk) if desk != "ai" else ""
    for n, score in enumerate(scores[: a.summarize_top], 1):
        entry = story_entry(store, sources, score, n)
        prev = store.conn.execute("SELECT item_count, outlet_count, prompt_version, data FROM story_summaries WHERE story_id = ?", (score.story_id,)).fetchone()
        if prev and not needs_refresh(prev, entry, a, summary_prompt, news_prompt):
            stats.unchanged += 1
            continue
        try:
            out = llm.parse("story_summary", settings.llm.story_model, system, head + material(entry), StorySummary, max_tokens=2000, fallbacks=True)
        except LLMUnavailable as e:
            stats.notes.append(str(e))
            break
        except Exception as e:
            log.warning("summary failed for %s: %s", score.story_id, e)
            stats.notes.append(f"summary: {type(e).__name__}")
            continue
        data = out.model_dump()
        data["basis"] = {"news_prompt": news_prompt, "stance": entry["stance"]}  # what the summary was written from
        with store.conn:
            store.conn.execute(
                "INSERT OR REPLACE INTO story_summaries(story_id, prompt_version, model, data, item_count, outlet_count, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (score.story_id, summary_prompt, settings.llm.story_model, json.dumps(data), entry["items"], entry["outlets"], iso(now)),
            )
        stats.summarized += 1
    return stats


def weather(store: Store, settings: Settings, sources: SourcesConfig, llm: LLM, scores: list[StoryScore], rising: list[RisingItem], top: int,
            now: datetime, period: PeriodSettings | None = None, desk: str = "ai") -> SummaryStats:
    """One sentence per view: regenerated when the view's top 3 stories change, or when the
    rest of the top list changed and the line is older than `weather_min_hours`."""
    stats = SummaryStats()
    period = period or settings.site.periods[0]
    kind = weather_kind(period.key, desk)
    prompt = settings.weather_prompt(desk)
    top_ids = [s.story_id for s in scores[:top]]
    last = store.conn.execute("SELECT data, prompt_version, created_at FROM reports WHERE kind = ? ORDER BY id DESC LIMIT 1", (kind,)).fetchone()
    if last and last["prompt_version"] == prompt:
        prev_ids = json.loads(last["data"]).get("story_ids") or []
        age_h = (now - datetime.fromisoformat(last["created_at"])).total_seconds() / 3600
        top3_same = set(prev_ids[:3]) == set(top_ids[:3])
        if prev_ids == top_ids or (top3_same and age_h < settings.analysis.weather_min_hours):
            return stats
    if not top_ids:
        return stats
    lines = ([desk_line(settings, desk).strip()] if desk != "ai" else []) + [f"Period: the last {period.label}."]
    covered = covered_hours(store, now)
    if covered is not None and covered < period.hours:
        span = "about the last day" if covered < 36 else f"about the last {covered / 24:.0f} days"
        lines.append(f"Data covers only {span} of this period (collection started recently).")
    lines.append("Top stories:")
    for n, s in enumerate(scores[:top], 1):
        e = story_entry(store, sources, s, n)
        lines.append(f"- {e['headline']} [{e['track'] or 'unknown angle'}; {e['outlets']} outlets]")
    if settings.desk(desk).builders:
        lines.append("Rising builder projects:")
        for r in rising[:10]:
            lines.append(f"- {r.kind}: {r.title}")
    try:
        out = llm.parse("weather", settings.llm.story_model, load_prompt(prompt), "\n".join(lines), Weather, max_tokens=600, fallbacks=True)
    except LLMUnavailable as e:
        stats.notes.append(str(e))
        return stats
    except Exception as e:
        stats.notes.append(f"weather: {type(e).__name__}")
        return stats
    with store.conn:
        store.conn.execute(
            "INSERT INTO reports(kind, prompt_version, model, data, created_at) VALUES (?, ?, ?, ?, ?)",
            (kind, prompt, settings.llm.story_model, json.dumps({"sentence": out.sentence, "story_ids": top_ids}), iso(now)),
        )
    stats.weather = True
    return stats
