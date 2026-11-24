"""Group items into stories over a rolling window, keeping story IDs stable across runs.

Each run only places items that have no story yet, in time order:
1. Link evidence first: an HN post or Bluesky post linking to an article, a Techmeme lead
   pointing at an outlet's URL, a paper naming its GitHub repo, all join the story of the
   item they point to.
2. Otherwise cosine similarity to existing story centroids (plus a small boost per shared
   name), joining the best story above `join_threshold` (`strict_join_threshold` for repos,
   models, datasets, spaces, papers and launches, whose descriptions are generic).
3. Otherwise the item starts a new story, whose ID derives from the item's ID.
Then near-identical stories that share a name are merged into the older one.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import numpy as np

from quiet_ai.config import ClusterSettings
from quiet_ai.pipeline.embed import from_blob, normalize, to_blob
from quiet_ai.store.db import Store, iso
from quiet_ai.text import canonical_url

BUILDER_KINDS = ("repo", "model", "dataset", "space")
# SQL: when an item "happened". Repos/models are dated by creation, so use first sighting.
EVENT_AT = (
    "CASE WHEN i.kind IN ('repo','model','dataset','space') THEN i.first_seen_at "
    "ELSE MIN(COALESCE(i.published_at, i.first_seen_at), i.first_seen_at) END"
)

_ENTITY_NAMES = re.compile(
    r"\b(OpenAI|Anthropic|DeepMind|Google|Alphabet|Microsoft|Meta|Apple|Amazon|AWS|Nvidia|NVIDIA|AMD|Intel|TSMC|ASML|"
    r"Huawei|Alibaba|Tencent|Baidu|ByteDance|Samsung|xAI|Mistral|Cohere|Perplexity|Hugging Face|DeepSeek|Qwen|Kimi|"
    r"Moonshot|Zhipu|Sakana|Thinking Machines|Ai2|Stability|Midjourney|ChatGPT|Claude|Gemini|Copilot|Grok|Llama|Sora|"
    r"Inkling|Altman|Amodei|Hassabis|Huang|Musk|Zuckerberg|Nadella|Pichai|Suleyman|LeCun|Hinton|Sutskever|Murati|"
    r"Trump|Biden|Congress|Senate|EU|European Commission|China|Beijing|Taiwan|India|Japan|Korea|UK|Britain|"
    r"FTC|SEC|Pentagon|OpenRouter|GitHub|Cursor|Windsurf)\b"
)
_VERSIONED = re.compile(r"\b([A-Z][A-Za-z]{1,15})[- ]?(\d+(?:\.\d+)*)\b")


_WORD = re.compile(r"[A-Za-zÀ-ÿ][\w'’-]*")
_NOT_NAMES = {
    "the", "a", "an", "ai", "and", "or", "but", "how", "why", "what", "who", "when", "where", "is", "are", "was", "will",
    "new", "this", "that", "its", "it's", "after", "as", "in", "on", "at", "for", "of", "to", "with", "from", "by", "us",
    "ceo", "llm", "ki", "ia", "der", "die", "das", "le", "la", "les", "el", "en", "och", "det", "den", "i",
}


def entities(text: str, extra: list[str] | None = None) -> set[str]:
    """Names in a headline: a fixed list of AI companies/people/places, versioned model
    names ("GPT-6.2"), and, in sentence-case headlines, capitalized words after the first.
    `extra` adds names an LLM label already extracted."""
    out = {m.lower() for m in _ENTITY_NAMES.findall(text)}
    out |= {f"{a.lower()}-{b}" for a, b in _VERSIONED.findall(text) if not a.isupper() or len(a) <= 4}
    words = _WORD.findall(text)
    caps = [w for w in words[1:] if w[0].isupper()]
    if words and len(caps) <= 0.5 * (len(words) - 1):  # Title Case headlines capitalize everything
        out |= {w.lower().rstrip("'’s") for w in caps if len(w) > 2 and w.lower() not in _NOT_NAMES}
    out |= {e.lower() for e in extra or [] if e.lower() not in _NOT_NAMES}
    return out


def norm_key(url: str | None) -> str | None:
    """A comparable key for link evidence; None for URLs too generic to link on."""
    if not url or not url.startswith("http"):
        return None
    c = canonical_url(url)
    parts = urlsplit(c)
    host = parts.netloc.lower().removeprefix("www.")
    segs = [s for s in parts.path.split("/") if s]
    if not segs:
        return None
    if host == "github.com":
        return "github.com/" + "/".join(segs[:2]).lower() if len(segs) >= 2 else None
    if host == "huggingface.co":
        if segs[0] == "papers" and len(segs) >= 2:
            return "arxiv:" + re.sub(r"v\d+$", "", segs[1])
        n = 3 if segs[0] in ("datasets", "spaces") else 2
        return "huggingface.co/" + "/".join(segs[:n]).lower() if len(segs) >= n else None
    if host == "arxiv.org" and len(segs) >= 2 and segs[0] in ("abs", "pdf", "html"):
        return "arxiv:" + re.sub(r"(v\d+)?(\.pdf)?$", "", segs[1])
    query = f"?{parts.query}" if parts.query else ""
    return f"{host}/{'/'.join(segs)}{query}"


def link_keys(kind: str, url: str, extra: dict) -> set[str]:
    keys = {norm_key(url)}
    if kind == "hn":
        keys.add(norm_key(extra.get("hn_url")))
    keys |= {norm_key(u) for u in extra.get("links", [])}
    keys.add(norm_key(extra.get("lead_url")))
    if extra.get("github_repo"):
        keys.add(norm_key(extra["github_repo"]))
    if extra.get("arxiv_url"):
        keys.add(norm_key(extra["arxiv_url"]))
    if extra.get("hugging_face_id"):
        keys.add(norm_key(f"https://huggingface.co/{extra['hugging_face_id']}"))
    keys.discard(None)
    return keys  # type: ignore[return-value]


def story_id_for(item_id: str) -> str:
    return "s-" + hashlib.sha1(item_id.encode()).hexdigest()[:10]


@dataclass
class _Story:
    id: str
    mean: np.ndarray
    count: int
    first_at: str
    last_at: str
    created_at: str
    entities: Counter = field(default_factory=Counter)
    keys: set[str] = field(default_factory=set)
    is_new: bool = False
    dirty: bool = False
    loose: bool = False  # has a member outside the strict kinds (news, HN, posts...)

    @property
    def unit(self) -> np.ndarray:
        return normalize(self.mean[None, :])[0]

    def add(self, vec: np.ndarray, at: str, ents: set[str], keys: set[str], loose: bool) -> None:
        self.loose = self.loose or loose
        self.mean = (self.mean * self.count + vec) / (self.count + 1)
        self.count += 1
        self.first_at, self.last_at = min(self.first_at, at), max(self.last_at, at)
        self.entities.update(ents)
        self.keys |= keys
        self.dirty = True


@dataclass
class ClusterStats:
    placed: int = 0
    by_link: int = 0
    by_similarity: int = 0
    new_stories: int = 0
    merged: int = 0
    active_stories: int = 0


def _window_items(store: Store, model: str, since: str, strict_kinds: set[str]) -> list[dict]:
    rows = store.conn.execute(
        f"SELECT i.id, i.kind, i.url, i.title, i.title_en, i.extra, i.story_id, {EVENT_AT} AS event_at, e.vector, l.data AS label "
        "FROM items i JOIN embeddings e ON e.item_id = i.id AND e.model = ? LEFT JOIN item_labels l ON l.item_id = i.id "
        f"WHERE i.relevant = 1 AND i.dup_of IS NULL AND {EVENT_AT} >= ? ORDER BY event_at, i.id",
        (model, since),
    ).fetchall()
    out = []
    for r in rows:
        extra = json.loads(r["extra"] or "{}")
        text = r["title_en"] or r["title"]
        out.append({
            "id": r["id"], "kind": r["kind"], "strict": r["kind"] in strict_kinds, "story_id": r["story_id"], "event_at": r["event_at"], "vec": from_blob(r["vector"]),
            "ents": entities(text, json.loads(r["label"]).get("entities") if r["label"] else None),
            "keys": link_keys(r["kind"], r["url"], extra),
        })
    return out


def _load_stories(store: Store, model: str, since: str, members: dict[str, list[dict]]) -> dict[str, _Story]:
    """Active stories with their centroids; `members` are their items inside the window."""
    rows = store.conn.execute(
        "SELECT * FROM stories WHERE merged_into IS NULL AND last_item_at >= ?", (since,)
    ).fetchall()
    stories = {}
    for r in rows:
        mem = members.get(r["id"], [])
        if r["centroid"] is not None and r["model"] == model:
            mean = from_blob(r["centroid"]).copy()
        elif mem:
            mean = np.mean([m["vec"] for m in mem], axis=0)
        else:
            continue
        st = _Story(r["id"], mean, r["item_count"], r["first_item_at"], r["last_item_at"], r["created_at"])
        st.loose = any(not m["strict"] for m in mem)
        for m in mem:
            st.entities.update(m["ents"])
            st.keys |= m["keys"]
        stories[st.id] = st
    return stories


def run(store: Store, model: str, cfg: ClusterSettings, now: datetime) -> ClusterStats:
    stats = ClusterStats()
    since = iso(now - timedelta(hours=cfg.window_hours))
    items = _window_items(store, model, since, set(cfg.strict_kinds))
    members: dict[str, list[dict]] = {}
    for it in items:
        if it["story_id"]:
            members.setdefault(it["story_id"], []).append(it)
    stories = _load_stories(store, model, since, members)
    key_index: dict[str, set[str]] = {}
    for st in stories.values():
        for k in st.keys:
            key_index.setdefault(k, set()).add(st.id)

    assignments: list[tuple[str, str]] = []
    for it in items:
        if it["story_id"] and it["story_id"] in stories:
            continue
        if it["story_id"]:  # its story left the window; leave the item where it is
            continue
        target, how = None, ""
        linked = {sid for k in it["keys"] for sid in key_index.get(k, ()) if sid in stories}
        if linked:
            target = max(linked, key=lambda sid: float(stories[sid].unit @ it["vec"]))
            how = "link"
        elif stories:
            ids = list(stories)
            sims = np.stack([stories[s].unit for s in ids]) @ it["vec"]
            boost = np.array([cfg.entity_boost * min(sum(1 for e in it["ents"] if e in stories[s].entities), 2) for s in ids])
            # Repos, models and papers have generic descriptions ("an agent framework for..."):
            # they join, or are joined, by similarity only when it is very close.
            thresholds = np.array([
                cfg.join_threshold if (not it["strict"] and stories[s].loose) else cfg.strict_join_threshold for s in ids
            ])
            # Generic AI headlines sit around 0.6 to each other. In the band between join_threshold
            # and confident_threshold an item needs a shared name to join.
            shared = boost > 0
            gated = (sims + boost >= thresholds) & ((sims >= cfg.confident_threshold) | shared | (thresholds > cfg.join_threshold))
            margin = np.where(gated, sims + boost - thresholds, -1.0)
            best = int(np.argmax(margin))
            if margin[best] >= 0:
                target, how = ids[best], "similarity"
        if target:
            stories[target].add(it["vec"], it["event_at"], it["ents"], it["keys"], not it["strict"])
            stats.by_link += how == "link"
            stats.by_similarity += how == "similarity"
        else:
            target = story_id_for(it["id"])
            stories[target] = _Story(target, it["vec"].copy(), 1, it["event_at"], it["event_at"], iso(now),
                                     Counter(it["ents"]), set(it["keys"]), is_new=True, dirty=True, loose=not it["strict"])
            stats.new_stories += 1
        for k in it["keys"]:
            key_index.setdefault(k, set()).add(target)
        assignments.append((target, it["id"]))
        stats.placed += 1

    merges = _merge(stories, cfg)
    stats.merged = len(merges)
    for loser, winner in merges:
        assignments = [(winner if sid == loser else sid, iid) for sid, iid in assignments]

    with store.conn:
        store.conn.executemany("UPDATE items SET story_id = ? WHERE id = ?", assignments)
        for loser, winner in merges:
            store.conn.execute("UPDATE items SET story_id = ? WHERE story_id = ?", (winner, loser))
            store.conn.execute("UPDATE stories SET merged_into = ?, updated_at = ? WHERE id = ?", (winner, iso(now), loser))
        for st in stories.values():
            if not st.dirty:
                continue
            count = store.conn.execute("SELECT COUNT(*) FROM items WHERE story_id = ?", (st.id,)).fetchone()[0]
            store.conn.execute(
                "INSERT INTO stories(id, created_at, updated_at, first_item_at, last_item_at, item_count, centroid, model) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at, "
                "first_item_at = excluded.first_item_at, last_item_at = excluded.last_item_at, "
                "item_count = excluded.item_count, centroid = excluded.centroid, model = excluded.model, merged_into = NULL",
                (st.id, st.created_at, iso(now), st.first_at, st.last_at, count, to_blob(st.mean), model),
            )
    stats.active_stories = len(stories)
    return stats


def _merge(stories: dict[str, _Story], cfg: ClusterSettings) -> list[tuple[str, str]]:
    """Merge pairs above merge_threshold that share a name or a link; newer joins older."""
    ids = list(stories)
    if len(ids) < 2:
        return []
    units = np.stack([stories[s].unit for s in ids])
    sims = units @ units.T
    pairs = sorted(
        ((sims[a, b], ids[a], ids[b]) for a in range(len(ids)) for b in range(a + 1, len(ids)) if sims[a, b] >= cfg.merge_threshold),
        reverse=True,
    )
    gone: set[str] = set()
    merges = []
    for _, x, y in pairs:
        if x in gone or y in gone:
            continue
        sx, sy = stories[x], stories[y]
        shared_link = bool(sx.keys & sy.keys)
        if not shared_link and (not (sx.loose and sy.loose) or not set(sx.entities) & set(sy.entities)):
            continue
        older, newer = (sx, sy) if (sx.first_at, sx.id) <= (sy.first_at, sy.id) else (sy, sx)
        older.mean = (older.mean * older.count + newer.mean * newer.count) / (older.count + newer.count)
        older.count += newer.count
        older.first_at, older.last_at = min(older.first_at, newer.first_at), max(older.last_at, newer.last_at)
        older.entities.update(newer.entities)
        older.keys |= newer.keys
        older.loose = older.loose or newer.loose
        older.dirty = True
        gone.add(newer.id)
        merges.append((newer.id, older.id))
    for g in gone:
        stories.pop(g)
    return merges
