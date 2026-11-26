"""Relevance filter: which desk (AI, energy, biotech, space, food) is this item about, if any?
Keywords first for AI, Haiku for the rest. Also fills title_en for non-English items (same Haiku call), and marks
near-duplicate titles.

With only the AI desk, items with no AI keyword are dropped without a model call. With more desks, press items
(news, newsletters, aggregators, Hacker News) with no AI keyword go to Haiku too, which sorts them onto a desk or
drops them; so no desk needs keyword lists in every language. Sources that opted out of AI input are sorted by
keywords alone (`DESK_KEYWORDS`, English)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from typing import Literal

from pydantic import BaseModel

from quiet_ai.config import Settings, SourcesConfig
from quiet_ai.llm.client import LLM, NO_THINKING, LLMUnavailable, load_prompt
from quiet_ai.store.db import Store

log = logging.getLogger(__name__)
TASK = "relevance"
TRANSLATE_TASK = "translate"

# Languages the keyword lists below cover (the About page says how many).
LANGUAGES = ("en", "sv", "de", "fr", "es", "pt", "it", "nl", "no", "da", "fi", "pl", "cs", "hu", "uk",
             "ja", "ko", "zh", "hi", "id", "vi", "ar", "tr")

# Latin acronyms and names sit inside Japanese, Chinese and Korean text with no space ("生成AIが", "OpenAI发布"),
# where \b never matches (those scripts count as word characters). So they are bounded by "no Latin letter or
# digit next to it" instead.
_L = r"(?<![0-9A-Za-zÀ-ÖØ-öø-ÿ_])"
_R = r"(?![0-9A-Za-zÀ-ÖØ-öø-ÿ_])"
# Acronyms and names that collide with ordinary words when lowercased: matched case-sensitively.
_STRONG_CS = re.compile(
    _L + r"(AI|A\.I\.|KI|IA|AGI|LLMs?|GPTs?|GPT-\d[\w.]*|GPUs?|TPUs?)" + _R
    # Names, also in genitive form ("Nvidias", "OpenAI's").
    + r"|" + _L + r"(xAI|OpenAI|ChatGPT|Claude|Gemini|Copilot|Grok|Llama|Mistral|DeepSeek|Qwen|Kimi|Perplexity|Midjourney|"
    r"Sora|Anthropic|DeepMind|Nvidia|NVIDIA)(?:s|'s|’s)?" + _R
)
_STRONG_CI = re.compile(
    r"\b(artificial intelligence|künstliche[rn]? intelligenz|intelligence artificielle|inteligencia artificial|inteligência artificial|"
    r"artificiell intelligens|intelligenza artificiale|kunstmatige intelligentie|kunstig intelligens|tekoäly\w*|"
    r"sztuczn\w+ inteligencj\w+|uměl\w+ inteligenc\w+|mesterséges intelligenci\w*|"
    r"yapay zek[aâ]\w*|kecerdasan buatan|kecerdasan artifisial|trí tuệ nhân tạo|"
    r"machine learning|maskininlärning|maskinlæring|apprendimento automatico|aprendizaje automático|aprendizado de máquina|"
    r"deep learning|neural net\w*|"
    r"large language models?|language models?|språkmodell\w*|sprogmodel\w*|sprachmodell\w*|taalmodel\w*|kielimalli\w*|"
    r"modelos? de (?:lenguaje|linguagem)|modell[io] linguistic\w*|model\w* językow\w*|jazykov\w+ model\w*|nyelvi modell\w*|"
    r"büyük dil modeli\w*|"
    r"generative? ai|generativ\w* ai|"
    r"chatbot\w*|deepfakes?|superintelligen\w*|foundation models?|frontier models?|ai agents?|agentic|"
    r"hugging face|stable diffusion|data ?cent(?:er|re)s?|datacenters?|datacentr\w*|datasent\w*|datakeskus\w*|adatközpont\w*|"
    r"centr\w* danych|datov\w+ centr\w*|centros? de (?:datos|dados)|veri merkez\w*|pusat data|"
    r"ai[- ]chips?|"
    r"sam altman|altman|dario amodei|amodei|demis hassabis|hassabis|jensen huang|mustafa suleyman|"
    r"yann lecun|geoffrey hinton|ilya sutskever|mira murati)\b",
    re.IGNORECASE,
)
# The same in scripts without spaces or case (Japanese, Chinese, Korean) and in Arabic and Hindi: no word boundaries.
_STRONG_SCRIPT = re.compile(
    "人工智能|人工智慧|人工知能|生成式|大模型|大语言模型|大語言模型|大规模语言模型|大規模言語モデル|智能体|智慧體|"
    "英伟达|輝達|辉达|黄仁勋|黃仁勳|深度求索|通义千问|文心一言|智谱|月之暗面|"
    "エヌビディア|オープンAI|チャットGPT|"
    "인공지능|생성형|초거대|거대언어모델|엔비디아|오픈AI|챗GPT|챗봇|젠슨 황|"
    "الذكاء الاصطناعي|ذكاء اصطناعي|إنفيديا|انفيديا|أوبن إيه آي|شات جي بي تي|روبوت دردشة|"
    "एआई|आर्टिफिशियल इंटेलिजेंस|कृत्रिम बुद्धिमत्ता|चैटजीपीटी|एनवीडिया|"
    # Ukrainian: the acronym ШІ only as a word of its own
    "(?i:штучн[а-яіїєґ]* інтелект[а-яіїєґ]*|нейромереж[а-яіїєґ]*)|(?<![А-ЯІЇЄҐа-яіїєґ])ШІ(?![А-ЯІЇЄҐа-яіїєґ])"
)
# Topics often but not always about AI: decided by Haiku.
_WEAK = re.compile(
    r"\b(chips?|chipmakers?|semiconductors?|semiconductores|semicondutores|yarı iletken\w*|semikonduktor|bán dẫn|"
    r"halvledare|halbleiter|tsmc|asml|export controls?|"
    r"robots?|robôs?|robotics|robótica|algoritmos|"
    r"automation|algorithms?|autonomous|self-driving|microsoft|google|alphabet|meta|apple|amazon|musk|tesla|"
    r"zuckerberg|pichai|nadella|bezos|tech giants?|big tech|silicon valley|startup\w*|copyright|surveillance)\b",
    re.IGNORECASE,
)
_WEAK_SCRIPT = re.compile("半导体|半導體|半導体|芯片|晶片|算力|机器人|機器人|ロボット|반도체|로봇|أشباه الموصلات|رقائق|روبوت|सेमीकंडक्टर|चिप")


def _strong(text: str) -> bool:
    return bool(_STRONG_CS.search(text) or _STRONG_CI.search(text) or _STRONG_SCRIPT.search(text))


# Sources with `llm: false` never reach the model, so their items are sorted by these (English) keywords.
DESK_KEYWORDS: dict[str, re.Pattern] = {
    "energy": re.compile(
        r"\b(energy|oil prices?|crude|lng|opec|nuclear (?:power|plants?|energy|reactors?)|fusion energy|solar (?:power|panels?|farms?)|"
        r"wind (?:farms?|power|turbines?)|power grids?|electricity|renewables?|coal|hydrogen|batteries|heat pumps?|"
        r"emissions|carbon capture|uranium|pipelines?|blackouts?)\b", re.I),
    "biotech": re.compile(
        r"\b(biotech\w*|vaccines?|gene (?:therapy|editing)|crispr|mrna|drugmakers?|drug (?:prices?|approvals?|trials?)|fda|"
        r"clinical trials?|pharma\w*|glp-1|ozempic|wegovy|medtech|novo nordisk|eli lilly|pfizer|astrazeneca)\b", re.I),
    "space": re.compile(
        r"\b(spacex|nasa|esa|rockets?|satellites?|starship|starlink|lunar|moon (?:landing|mission)|mars|astronauts?|"
        r"space station|spacecraft|telescope|asteroid|blue origin)\b", re.I),
    "food": re.compile(
        r"\b(farmers?|agricultur\w*|crops?|harvests?|wheat|maize|rice prices?|soybeans?|cocoa|fertili[sz]ers?|"
        r"food (?:prices?|security|supply|aid|inflation|crisis)|famine|hunger|livestock|fisheries)\b", re.I),
}
# Kinds that can be about another desk; everything else collected (repos, models, Bluesky posts from AI accounts...)
# is AI or nothing.
DESK_KINDS = ("news", "newsletter", "aggregator", "hn")


def keyword_desk(text: str, desks: set[str]) -> str | None:
    """The first non-AI desk whose keywords appear in the text (for sources the model never sees)."""
    return next((d for d, rx in DESK_KEYWORDS.items() if d in desks and rx.search(text)), None)


def _weak(text: str) -> bool:
    return bool(_WEAK.search(text) or _WEAK_SCRIPT.search(text))


_NORM = re.compile(r"[\W_]+")  # any script's letters and digits count


DeskKey = Literal["ai", "energy", "biotech", "space", "food"]


class _Verdict(BaseModel):
    i: int
    desk: DeskKey | None
    title_en: str | None


class _Batch(BaseModel):
    items: list[_Verdict]


class _Translation(BaseModel):
    i: int
    title_en: str


class _Translations(BaseModel):
    items: list[_Translation]


@dataclass
class RelevanceStats:
    by: dict[str, int] = field(default_factory=dict)
    llm_items: int = 0
    llm_calls: int = 0
    llm_cost_usd: float = 0.0
    pending: int = 0  # ambiguous items left undecided (no LLM)
    translated: int = 0  # English titles filled in by the translation-only call
    duplicates: int = 0
    note: str = ""


def keyword_verdict(kind: str, source: str, title: str, summary: str | None, ai_sources: set[str], always_kinds: set[str], always_sources: set[str]) -> tuple[bool | None, str]:
    if kind in always_kinds:
        return True, "kind"
    if source in ai_sources or source in always_sources:
        return True, "source"
    if _strong(title):
        return True, "keyword"
    body = summary or ""
    if _strong(body) or _weak(title) or _weak(body):
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
    desks = {d.key for d in settings.active_desks}
    ai_sources = {f.id for f in sources.feeds if f.ai_focused}
    desk_sources = {f.id: f.desk for f in sources.feeds if f.desk and not f.ai_focused and f.desk in desks}
    # Publishers that opted out of AI input (Content-Signal: ai-input=no): keywords only, never Haiku.
    no_llm = {f.id for f in sources.feeds if not f.llm}
    rel = settings.relevance

    # 1. Keyword pass on items not yet decided (ambiguous ones again, so keyword fixes apply).
    rows = store.conn.execute(
        "SELECT id, kind, source, title, summary, dup_of FROM items "
        "WHERE (relevance_by IS NULL OR relevance_by = 'ambiguous') AND first_seen_at >= ?", (since_iso,)
    ).fetchall()
    updates = []
    others = desks - {"ai"}
    for r in rows:
        if r["source"] in desk_sources:  # a feed wholly about one desk
            updates.append((1, "source", desk_sources[r["source"]], r["id"]))
            stats.by["source"] = stats.by.get("source", 0) + 1
            continue
        verdict, by = keyword_verdict(r["kind"], r["source"], r["title"], r["summary"], ai_sources, set(rel.always_kinds), set(rel.always_sources))
        desk = "ai" if verdict else None
        if verdict is None and r["source"] in no_llm:
            verdict, by = _strong(r["summary"] or ""), "keyword"
            desk = "ai" if verdict else None
        if verdict is False and others and r["kind"] in DESK_KINDS and not r["dup_of"]:
            if r["source"] in no_llm:  # sorted by keywords only
                desk = keyword_desk(f"{r['title']} {r['summary'] or ''}", others)
                verdict = desk is not None
            else:  # not AI by its words; the model decides whether another desk takes it
                verdict, by = None, "ambiguous"
        updates.append((None if verdict is None else int(verdict), by, desk, r["id"]))
        stats.by[by] = stats.by.get(by, 0) + 1
    with store.conn:
        store.conn.executemany("UPDATE items SET relevant = ?, relevance_by = ?, desk = ? WHERE id = ?", updates)

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
            f"[{n}] ({r['lang'] or 'en'}) {r['title']}" + (f" | {r['summary'][:200].rsplit(' ', 1)[0]}" if r["summary"] else "")
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
                results[batch[v.i]["content_hash"]] = {"desk": v.desk, "title_en": v.title_en}
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
            desk = res.get("desk")
            if desk is None and res.get("about_ai"):  # answers cached by relevance_v2
                desk = "ai"
            desk = desk if desk in desks else None
            updates.append((int(desk is not None), "llm", desk, title_en, r["id"]))
        else:
            updates.append((1, r["relevance_by"], None, title_en, r["id"]))
    with store.conn:
        store.conn.executemany("UPDATE items SET relevant = ?, relevance_by = ?, desk = COALESCE(?, desk), "
                               "title_en = COALESCE(?, title_en) WHERE id = ?", updates)
        # A new English title changes what gets embedded.
        store.conn.executemany("DELETE FROM embeddings WHERE item_id = ?", [(u[4],) for u in updates if u[3]])
    stats.translated, note = translate_missing(store, settings, llm, since_iso, no_llm)
    stats.note = stats.note or note
    stats.llm_calls, stats.llm_cost_usd = llm.calls, llm.cost_usd
    stats.pending = store.conn.execute(
        "SELECT COUNT(*) FROM items WHERE relevance_by = 'ambiguous' AND first_seen_at >= ?", (since_iso,)
    ).fetchone()[0]
    return stats


def translate_missing(store: Store, settings: Settings, llm: LLM, since_iso: str, no_llm: set[str]) -> tuple[int, str]:
    """English titles for relevant headlines in other languages that still have none. The relevance call leaves
    title_en empty for some of them, and its cached answer is never asked again, so they would stay untranslated:
    shown in the original language and, in a non-Latin script, never clustered. A translation-only call fills them in.
    Empty answers aren't cached, so they are asked again next run. Returns (titles filled, note)."""
    rows = store.conn.execute(
        "SELECT id, title, lang, content_hash FROM items WHERE first_seen_at >= ? AND relevant = 1 AND dup_of IS NULL AND "
        "lang IS NOT NULL AND lang != 'en' AND title_en IS NULL "
        f"AND source NOT IN ({','.join('?' * len(no_llm))}) ORDER BY first_seen_at DESC",
        (since_iso, *sorted(no_llm)),
    ).fetchall()
    if not rows:
        return 0, ""
    version = settings.relevance.translate_prompt
    cached = llm.cached(TRANSLATE_TASK, version, [r["content_hash"] for r in rows])
    todo = [r for r in rows if r["content_hash"] not in cached]
    system = load_prompt(version)
    size = settings.relevance.llm_batch_size
    note = ""
    for start in range(0, len(todo), size):
        batch = todo[start : start + size]
        user = "\n".join(f"[{n}] ({r['lang']}) {r['title']}" for n, r in enumerate(batch))
        try:
            out = llm.parse(TRANSLATE_TASK, settings.llm.item_model, system, user, _Translations,
                            max_tokens=200 + 150 * len(batch), thinking=NO_THINKING)
        except LLMUnavailable as e:
            note = str(e)
            break
        except Exception as e:  # API errors: retry next run
            log.warning("translation batch failed: %s", e)
            note = f"LLM error: {type(e).__name__}"
            continue
        results = {}
        for t in out.items:
            text = " ".join(t.title_en.split())[: settings.ingest.title_max_chars]
            if 0 <= t.i < len(batch) and text:
                results[batch[t.i]["content_hash"]] = {"title_en": text}
        llm.remember(TRANSLATE_TASK, version, settings.llm.item_model, results)
        cached.update(results)
    updates = [(cached[r["content_hash"]]["title_en"], r["id"]) for r in rows if r["content_hash"] in cached]
    with store.conn:
        store.conn.executemany("UPDATE items SET title_en = ? WHERE id = ? AND title_en IS NULL", updates)
        store.conn.executemany("DELETE FROM embeddings WHERE item_id = ?", [(u[1],) for u in updates])  # re-embed in English
    return len(updates), note
