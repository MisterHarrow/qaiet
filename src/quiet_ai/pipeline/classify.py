"""Item labels with Haiku.

News and commentary: track, frame, stance (-2..2), evidence phrases, rationale, confidence,
entities. Builder items: what it is, why it matters, kind. Results are cached by content hash
and prompt version; every label records the prompt version that produced it.

Changing a prompt version relabels items in the window on the next run.

Evidence is checked: a phrase counts only if it appears in the item's own headline or summary.
A real quote longer than 12 words is cut to its first 12. A label with no surviving evidence
drops to low confidence, which the site shows as "unclear".
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel

from quiet_ai.config import Settings, SourcesConfig
from quiet_ai.llm.client import LLM, NO_THINKING, LLMUnavailable, load_prompt
from quiet_ai.store.db import Store, iso

log = logging.getLogger(__name__)

Track = Literal["technical", "political", "economic"]
FRAMES: dict[str, tuple[str, ...]] = {
    "technical": ("hype", "grounded", "skeptical"),
    "political": ("pro-regulation", "pro-acceleration", "national-competition", "neutral"),
    "economic": ("boom", "bubble", "disruption-concern", "neutral"),
}
Frame = Literal["hype", "grounded", "skeptical", "pro-regulation", "pro-acceleration", "national-competition", "boom", "bubble", "disruption-concern", "neutral"]
BuilderKind = Literal["model", "tool/library", "agent", "infra", "dataset", "research paper", "demo/app"]
MAX_EVIDENCE_WORDS = 12


class NewsLabel(BaseModel):
    i: int
    track: Track
    track2: Track | None
    frame: Frame
    stance: Literal[-2, -1, 0, 1, 2]
    evidence: list[str]
    rationale: str
    confidence: Literal["low", "medium", "high"]
    entities: list[str]


class NewsBatch(BaseModel):
    items: list[NewsLabel]


class BuilderLabel(BaseModel):
    i: int
    what: str
    why: str
    kind: BuilderKind


class BuilderBatch(BaseModel):
    items: list[BuilderLabel]


@dataclass
class LabelStats:
    labeled: int = 0
    from_cache: int = 0
    calls: int = 0
    evidence_dropped: int = 0
    low_confidence: int = 0
    skipped_llm_false: int = 0
    notes: list[str] = field(default_factory=list)


def _norm(text: str) -> str:
    """Lowercase words only: quotes, dashes, ellipses and other punctuation don't decide a match."""
    text = unicodedata.normalize("NFKC", text).lower()
    return " ".join(re.findall(r"\w+", text))


def check_news_label(raw: dict, sources_text: list[str]) -> dict:
    """Keep evidence that is really in the item's text; repair impossible frames."""
    texts = [" " + _norm(t) + " " for t in sources_text if t]
    kept, rejected, truncated = [], [], 0
    for p in raw.get("evidence", []):
        p = p.strip()
        if not (p and _norm(p) and any(f" {_norm(p)} " in t for t in texts)):
            rejected.append(p)
            continue
        words = p.split()
        if len(words) > MAX_EVIDENCE_WORDS:  # a real quote, too long: keep its first 12 words
            p = " ".join(words[:MAX_EVIDENCE_WORDS]).rstrip(",;:") + "…"
            truncated += 1
        kept.append(p)
    out = dict(raw)
    out["evidence"] = kept[:2]
    out["evidence_rejected"] = rejected
    out["evidence_dropped"] = len(rejected)
    out["evidence_truncated"] = truncated
    if out.get("track2") == out.get("track"):
        out["track2"] = None
    if out.get("track") == "technical" and out.get("frame") == "neutral":
        # The brief gives technical items no neutral frame; plain technical reporting is "grounded".
        out["frame"], out["frame_repaired"] = "grounded", "neutral"
    if out.get("frame") not in FRAMES.get(out.get("track"), ()):
        out["frame"] = "neutral" if "neutral" in FRAMES.get(out.get("track"), ()) else None
        out["confidence"] = "low"
    if not out["evidence"]:
        out["confidence"] = "low"
    out["entities"] = list(dict.fromkeys(e.strip() for e in raw.get("entities", []) if e.strip()))[:8]
    return out


def _news_line(n: int, r) -> str:
    title = r["title"]
    if r["title_en"] and r["title_en"] != r["title"]:
        title += f" (English: {r['title_en']})"
    line = f"[{n}] ({r['lang'] or 'en'}) headline: {title}"
    if r["summary"]:
        line += f" | summary: {_cut(r['summary'], 300)}"
    return line


def _cut(text: str, n: int) -> str:
    """Cut at a word boundary, so the model never sees (and quotes) half a word."""
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0]


def _builder_line(n: int, r) -> str:
    extra = json.loads(r["extra"] or "{}")
    bits = [f"[{n}] ({r['kind']}) {r['title']}"]
    if r["summary"]:
        bits.append(_cut(r["summary"], 300))
    tags = extra.get("topics") or extra.get("tags") or extra.get("keywords") or []
    if tags:
        bits.append("tags: " + ", ".join(map(str, tags[:8])))
    if extra.get("language"):
        bits.append(f"language: {extra['language']}")
    return " | ".join(bits)


def _store_labels(store: Store, rows, results: dict[str, dict], task: str, version: str, model: str) -> None:
    now = iso(datetime.now(timezone.utc))
    with store.conn:
        for r in rows:
            res = results.get(r["content_hash"])
            if not res:
                continue
            store.conn.execute(
                "INSERT OR REPLACE INTO item_labels(item_id, task, prompt_version, model, track, track2, frame, stance, confidence, data, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r["id"], task, version, model, res.get("track"), res.get("track2"), res.get("frame"), res.get("stance"),
                 res.get("confidence"), json.dumps(res, ensure_ascii=False, sort_keys=True), now),
            )


def _run_batches(llm: LLM, task: str, version: str, model: str, rows, line_fn, output, batch_size: int, max_tokens_per_item: int, stats: LabelStats, check=None) -> dict[str, dict]:
    cached = llm.cached(task, version, [r["content_hash"] for r in rows])
    stats.from_cache += sum(1 for r in rows if r["content_hash"] in cached)
    todo = list({r["content_hash"]: r for r in rows if r["content_hash"] not in cached}.values())
    system = load_prompt(version)
    for start in range(0, len(todo), batch_size):
        batch = todo[start : start + batch_size]
        user = "\n".join(line_fn(n, r) for n, r in enumerate(batch))
        try:
            out = llm.parse(task, model, system, user, output, max_tokens=300 + max_tokens_per_item * len(batch), thinking=NO_THINKING)
        except LLMUnavailable as e:
            stats.notes.append(str(e))
            break
        except Exception as e:  # API trouble: keep what we have; the rest is retried next run
            log.warning("%s batch failed: %s", task, e)
            stats.notes.append(f"{task}: {type(e).__name__}")
            continue
        stats.calls += 1
        results = {}
        for lab in out.items:
            if not 0 <= lab.i < len(batch):
                continue
            row = batch[lab.i]
            raw = lab.model_dump(exclude={"i"})
            if check:
                raw = check(raw, row)
                stats.evidence_dropped += raw.get("evidence_dropped", 0)
                stats.low_confidence += raw.get("confidence") == "low"
            raw["prompt_version"] = version
            results[row["content_hash"]] = raw
        llm.remember(task, version, model, results)
        cached.update(results)
        stats.labeled += len(results)
    return cached


def label_news(store: Store, settings: Settings, sources: SourcesConfig, llm: LLM, since_iso: str) -> LabelStats:
    a = settings.analysis
    stats = LabelStats()
    no_llm = sorted(f.id for f in sources.feeds if not f.llm)
    digests = sorted(f.id for f in sources.feeds if f.role == "digest")
    kinds = a.stance_kinds
    rows = store.conn.execute(
        f"SELECT i.id, i.title, i.title_en, i.summary, i.lang, i.source, i.content_hash FROM items i "
        f"LEFT JOIN item_labels l ON l.item_id = i.id "
        f"WHERE (l.item_id IS NULL OR l.prompt_version != ?) AND i.relevant = 1 AND i.dup_of IS NULL AND i.first_seen_at >= ? "
        f"AND i.kind IN ({','.join('?' * len(kinds))}) AND i.source NOT IN ({','.join('?' * len(digests))}) "
        f"ORDER BY i.first_seen_at DESC",
        (a.news_prompt, since_iso, *kinds, *digests),
    ).fetchall()
    stats.skipped_llm_false = sum(1 for r in rows if r["source"] in no_llm)
    rows = [r for r in rows if r["source"] not in no_llm]
    if not rows:
        return stats
    results = _run_batches(
        llm, "news_label", a.news_prompt, settings.llm.item_model, rows, _news_line, NewsBatch, a.label_batch_size, 220, stats,
        check=lambda raw, row: check_news_label(raw, [row["title"], row["title_en"], row["summary"]]),
    )
    _store_labels(store, rows, results, "news", a.news_prompt, settings.llm.item_model)
    return stats


def label_builders(store: Store, settings: Settings, llm: LLM, item_ids: list[str]) -> LabelStats:
    a = settings.analysis
    stats = LabelStats()
    if not item_ids:
        return stats
    rows = store.conn.execute(
        f"SELECT i.id, i.kind, i.title, i.summary, i.extra, i.content_hash FROM items i LEFT JOIN item_labels l ON l.item_id = i.id "
        f"WHERE (l.item_id IS NULL OR l.prompt_version != ?) AND i.id IN ({','.join('?' * len(item_ids))})",
        [a.builder_prompt, *item_ids],
    ).fetchall()
    if not rows:
        return stats
    results = _run_batches(llm, "builder_label", a.builder_prompt, settings.llm.item_model, rows, _builder_line, BuilderBatch, a.label_batch_size, 90, stats)
    _store_labels(store, rows, results, "builder", a.builder_prompt, settings.llm.item_model)
    return stats
