"""Relevance filter: is this item about AI? Keywords first, Haiku for the ambiguous rest.
Also fills title_en for non-English items (same Haiku call), and marks near-duplicate titles."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from pydantic import BaseModel

from quiet_ai.config import Settings, SourcesConfig
from quiet_ai.llm.client import LLM, NO_THINKING, LLMUnavailable, load_prompt
from quiet_ai.store.db import Store

log = logging.getLogger(__name__)
TASK = "relevance"

# Acronyms and names that collide with ordinary words when lowercased: matched case-sensitively.
_STRONG_CS = re.compile(
    r"\b(AI|A\.I\.|KI|IA|AGI|LLMs?|GPTs?|GPT-\d[\w.]*|GPUs?|TPUs?)\b"
    # Names, also in genitive form ("Nvidias", "OpenAI's").
    r"|\b(xAI|OpenAI|ChatGPT|Claude|Gemini|Copilot|Grok|Llama|Mistral|DeepSeek|Qwen|Kimi|Perplexity|Midjourney|"
    r"Sora|Anthropic|DeepMind|Nvidia|NVIDIA)(?:s|'s|’s)?\b"
)
_STRONG_CI = re.compile(
    r"\b(artificial intelligence|künstliche[rn]? intelligenz|intelligence artificielle|inteligencia artificial|"
    r"artificiell intelligens|machine learning|maskininlärning|deep learning|neural net\w*|"
    r"large language models?|language models?|språkmodell\w*|sprachmodell\w*|generative? ai|generativ\w* ai|"
    r"chatbot\w*|deepfakes?|superintelligen\w*|foundation models?|frontier models?|ai agents?|agentic|"
    r"hugging face|stable diffusion|data ?cent(?:er|re)s?|datacenters?|ai[- ]chips?|"
    r"sam altman|altman|dario amodei|amodei|demis hassabis|hassabis|jensen huang|mustafa suleyman|"
    r"yann lecun|geoffrey hinton|ilya sutskever|mira murati)\b",
    re.IGNORECASE,
)
# Topics often but not always about AI: decided by Haiku.
_WEAK = re.compile(
    r"\b(chips?|chipmakers?|semiconductors?|halvledare|halbleiter|tsmc|asml|export controls?|robots?|robotics|"
    r"automation|algorithms?|autonomous|self-driving|microsoft|google|alphabet|meta|apple|amazon|musk|tesla|"
    r"zuckerberg|pichai|nadella|bezos|tech giants?|big tech|silicon valley|startup\w*|copyright|surveillance)\b",
    re.IGNORECASE,
)
_NORM = re.compile(r"[^0-9a-zà-ÿ]+")


class _Verdict(BaseModel):
    i: int
    about_ai: bool
    title_en: str | None


class _Batch(BaseModel):
    items: list[_Verdict]


@dataclass
class RelevanceStats:
    by: dict[str, int] = field(default_factory=dict)
    llm_items: int = 0
    llm_calls: int = 0
    llm_cost_usd: float = 0.0
    pending: int = 0  # ambiguous items left undecided (no LLM)
    duplicates: int = 0
    note: str = ""


def keyword_verdict(kind: str, source: str, title: str, summary: str | None, ai_sources: set[str], always_kinds: set[str], always_sources: set[str]) -> tuple[bool | None, str]:
    if kind in always_kinds:
        return True, "kind"
    if source in ai_sources or source in always_sources:
        return True, "source"
    if _STRONG_CS.search(title) or _STRONG_CI.search(title):
        return True, "keyword"
    body = summary or ""
    if _STRONG_CS.search(body) or _STRONG_CI.search(body) or _WEAK.search(title) or _WEAK.search(body):
        return None, "ambiguous"
    return False, "keyword"


def norm_title(title: str) -> str:
    return _NORM.sub(" ", title.lower()).strip()


def mark_duplicates(store: Store) -> int:
    """Same source, same normalized title, different URL: keep the first seen."""
    rows = store.conn.execute(
        "SELECT id, source, title FROM items WHERE dup_of IS NULL AND kind IN ('news','newsletter','lab','aggregator') "
        "ORDER BY first_seen_at, id"
    ).fetchall()
    first: dict[tuple[str, str], str] = {}
    dups = []
    for r in rows:
        key = (r["source"], norm_title(r["title"]))
        if len(key[1]) < 12:
            continue
        if key in first:
            dups.append((first[key], r["id"]))
        else:
            first[key] = r["id"]
    with store.conn:
        store.conn.executemany("UPDATE items SET dup_of = ? WHERE id = ?", dups)
    return len(dups)


def run(store: Store, settings: Settings, sources: SourcesConfig, llm: LLM | None, since_iso: str) -> RelevanceStats:
    stats = RelevanceStats()
    stats.duplicates = mark_duplicates(store)
    ai_sources = {f.id for f in sources.feeds if f.ai_focused}
    # Publishers that opted out of AI input (Content-Signal: ai-input=no): keywords only, never Haiku.
    no_llm = {f.id for f in sources.feeds if not f.llm}
    rel = settings.relevance

    # 1. Keyword pass on items not yet decided (ambiguous ones again, so keyword fixes apply).
    rows = store.conn.execute(
        "SELECT id, kind, source, title, summary FROM items "
        "WHERE (relevance_by IS NULL OR relevance_by = 'ambiguous') AND first_seen_at >= ?", (since_iso,)
    ).fetchall()
    updates = []
    for r in rows:
        verdict, by = keyword_verdict(r["kind"], r["source"], r["title"], r["summary"], ai_sources, set(rel.always_kinds), set(rel.always_sources))
        if verdict is None and r["source"] in no_llm:
            body = r["summary"] or ""
            verdict, by = bool(_STRONG_CS.search(body) or _STRONG_CI.search(body)), "keyword"
        updates.append((None if verdict is None else int(verdict), by, r["id"]))
        stats.by[by] = stats.by.get(by, 0) + 1
    with store.conn:
        store.conn.executemany("UPDATE items SET relevant = ?, relevance_by = ? WHERE id = ?", updates)

    # 2. Haiku: ambiguous items, plus relevant non-English items that still need an English title.
    queue = store.conn.execute(
        "SELECT id, title, summary, lang, content_hash, relevance_by FROM items WHERE first_seen_at >= ? AND dup_of IS NULL AND "
        "(relevance_by = 'ambiguous' OR (relevant = 1 AND lang IS NOT NULL AND lang != 'en' AND title_en IS NULL)) "
        f"AND source NOT IN ({','.join('?' * len(no_llm))}) ORDER BY first_seen_at DESC",
        (since_iso, *sorted(no_llm)),
    ).fetchall()
    if not queue:
        return stats
    if llm is None or not llm.available:
        stats.pending = sum(1 for r in queue if r["relevance_by"] == "ambiguous")
        stats.note = "no ANTHROPIC_API_KEY: ambiguous items stay undecided and non-English titles untranslated"
        return stats

    version = rel.prompt
    cached = llm.cached(TASK, version, [r["content_hash"] for r in queue])
    todo = [r for r in queue if r["content_hash"] not in cached]
    system = load_prompt(version)
    for start in range(0, len(todo), rel.llm_batch_size):
        batch = todo[start : start + rel.llm_batch_size]
        user = "\n".join(
            f"[{n}] ({r['lang'] or 'en'}) {r['title']}" + (f" | {r['summary'][:200]}" if r["summary"] else "")
            for n, r in enumerate(batch)
        )
        try:
            out = llm.parse(TASK, settings.llm.item_model, system, user, _Batch, max_tokens=200 + 120 * len(batch), thinking=NO_THINKING)
        except LLMUnavailable as e:
            stats.note = str(e)
            break
        except Exception as e:  # API errors: keep what we have, retry next run
            log.warning("relevance batch failed: %s", e)
            stats.note = f"LLM error: {type(e).__name__}"
            continue
        results = {}
        for v in out.items:
            if 0 <= v.i < len(batch):
                results[batch[v.i]["content_hash"]] = {"about_ai": v.about_ai, "title_en": v.title_en}
        llm.remember(TASK, version, settings.llm.item_model, results)
        cached.update(results)
        stats.llm_items += len(results)
    stats.llm_calls, stats.llm_cost_usd = llm.calls, llm.cost_usd

    updates = []
    for r in queue:
        res = cached.get(r["content_hash"])
        if not res:
            continue
        title_en = res.get("title_en") if (r["lang"] or "en") != "en" else None
        if r["relevance_by"] == "ambiguous":
            updates.append((int(bool(res["about_ai"])), "llm", title_en, r["id"]))
        else:
            updates.append((1, r["relevance_by"], title_en, r["id"]))
    with store.conn:
        store.conn.executemany("UPDATE items SET relevant = ?, relevance_by = ?, title_en = COALESCE(?, title_en) WHERE id = ?", updates)
        # A new English title changes what gets embedded.
        store.conn.executemany("DELETE FROM embeddings WHERE item_id = ?", [(u[3],) for u in updates if u[2]])
    stats.pending = store.conn.execute(
        "SELECT COUNT(*) FROM items WHERE relevance_by = 'ambiguous' AND first_seen_at >= ?", (since_iso,)
    ).fetchone()[0]
    return stats
