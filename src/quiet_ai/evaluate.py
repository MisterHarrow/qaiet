"""Checking the labels.

- sample: a blind, stratified set of articles for a person to label (tests/gold/labels.yaml).
- score:  agreement between the model's current labels and the hand labels, per field.
- audit:  how stance is distributed by outlet group, type and country, to spot skew in the
          classifier itself (a group that always comes out critical, say).
"""

from __future__ import annotations

import random
from collections import defaultdict
from pathlib import Path

import yaml

from quiet_ai.config import SourcesConfig
from quiet_ai.store.db import Store

GOLD_HEADER = """\
# Hand labels for checking the model. Label each article from its headline and summary alone,
# the way the model sees it. Don't look at the site's labels first.
#
# track:  technical | political | economic          (the main angle)
# frame:  technical -> hype | grounded | skeptical
#         political -> pro-regulation | pro-acceleration | national-competition | neutral
#         economic  -> boom | bubble | disruption-concern | neutral
# stance: -2 strongly critical | -1 critical | 0 neutral or plain reporting | 1 positive | 2 enthusiastic
#         (the article's attitude toward AI or the AI industry, not whether the news is good or bad)
#
# Leave a field empty if you can't tell; skip an item entirely by leaving all three empty.
# Then run: uv run qa eval score
"""


def _bucket(stance: int | None) -> str:
    return "neg" if (stance or 0) < 0 else "pos" if (stance or 0) > 0 else "zero"


def sample(store: Store, sources: SourcesConfig, n: int, seed: int = 7) -> list[dict]:
    """Stratified by track and stance direction so rare cells (enthusiastic political, ...) appear.
    One article per outlet per cell at most, and no publisher that opted out of AI processing."""
    no_llm = {f.id for f in sources.feeds if not f.llm}
    rows = store.conn.execute(
        "SELECT i.id, i.source, i.title, i.title_en, i.summary, i.lang, l.track, l.stance FROM item_labels l "
        "JOIN items i ON i.id = l.item_id WHERE l.task = 'news' AND i.kind = 'news' AND i.relevant = 1 AND i.dup_of IS NULL"
    ).fetchall()
    cells: dict[tuple, list] = defaultdict(list)
    for r in rows:
        if r["source"] not in no_llm:
            cells[(r["track"], _bucket(r["stance"]))].append(r)
    rng = random.Random(seed)
    for v in cells.values():
        rng.shuffle(v)
    picked, used = [], set()
    order = sorted(cells)
    while len(picked) < n and any(cells[c] for c in order):
        for c in order:
            while cells[c]:
                r = cells[c].pop()
                if (r["source"], c) in used:
                    continue
                used.add((r["source"], c))
                picked.append(r)
                break
            if len(picked) >= n:
                break
    rng.shuffle(picked)
    return [
        {"id": r["id"], "headline": r["title"], **({"english": r["title_en"]} if r["title_en"] and r["lang"] != "en" else {}),
         "summary": (r["summary"] or "")[:300], "track": None, "frame": None, "stance": None}
        for r in picked
    ]


def write_gold(items: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(GOLD_HEADER + "\n")
        yaml.safe_dump({"items": items}, fh, sort_keys=False, allow_unicode=True, width=110)


def load_gold(path: Path) -> list[dict]:
    if not path.exists():
        return []
    items = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("items") or []
    return [g for g in items if g.get("track") or g.get("frame") or g.get("stance") is not None]


def score(store: Store, gold: list[dict]) -> dict:
    """Per field: how often the model agrees with the hand label (only where both exist)."""
    if not gold:
        return {"n": 0}
    ids = [g["id"] for g in gold]
    labels = {
        r["item_id"]: r for r in store.conn.execute(
            f"SELECT item_id, track, frame, stance, confidence FROM item_labels WHERE item_id IN ({','.join('?' * len(ids))})", ids
        )
    }
    track = frame = stance_exact = stance_near = 0
    n_track = n_frame = n_stance = 0
    abs_err = 0.0
    by_conf: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    missing = 0
    for g in gold:
        m = labels.get(g["id"])
        if not m:
            missing += 1
            continue
        if g.get("track"):
            n_track += 1
            track += g["track"] == m["track"]
            if g.get("frame") and g["track"] == m["track"]:
                n_frame += 1
                frame += g["frame"] == m["frame"]
        if g.get("stance") is not None and m["stance"] is not None:
            n_stance += 1
            d = abs(int(g["stance"]) - int(m["stance"]))
            stance_exact += d == 0
            stance_near += d <= 1
            abs_err += d
            by_conf[m["confidence"] or "?"][0] += d <= 1
            by_conf[m["confidence"] or "?"][1] += 1
    pct = lambda a, b: round(100 * a / b) if b else None  # noqa: E731
    return {
        "n": len(gold) - missing,
        "missing": missing,
        "track": {"agree": pct(track, n_track), "n": n_track},
        "frame": {"agree": pct(frame, n_frame), "n": n_frame},
        "stance_exact": {"agree": pct(stance_exact, n_stance), "n": n_stance},
        "stance_within_1": {"agree": pct(stance_near, n_stance), "n": n_stance},
        "stance_mae": round(abs_err / n_stance, 2) if n_stance else None,
        "stance_within_1_by_confidence": {k: {"agree": pct(a, b), "n": b} for k, (a, b) in sorted(by_conf.items())},
    }


def audit(store: Store, sources: SourcesConfig, by: str = "group", min_n: int = 1) -> list[dict]:
    """Stance by outlet group / type / country: n, mean of confident labels, share critical and
    positive, share unclear. Rows sorted by mean stance."""
    attr = {f.id: getattr(f, by, None) for f in sources.feeds} | {g.id: getattr(g, by, None) for g in sources.gdelt_outlets}
    rows = store.conn.execute(
        "SELECT i.source, l.stance, l.confidence FROM item_labels l JOIN items i ON i.id = l.item_id "
        "WHERE l.task = 'news' AND i.kind = 'news' AND i.relevant = 1"
    ).fetchall()
    acc: dict[str, list] = defaultdict(list)
    for r in rows:
        key = attr.get(r["source"]) or "other"
        acc[key].append(r)
    out = []
    for key, rs in acc.items():
        conf = [r for r in rs if r["confidence"] != "low" and r["stance"] is not None]
        if len(rs) < min_n:
            continue
        mean = sum(r["stance"] for r in conf) / len(conf) if conf else None
        out.append({
            "key": key, "n": len(rs), "confident": len(conf),
            "mean": round(mean, 2) if mean is not None else None,
            "critical": round(100 * sum(r["stance"] < 0 for r in conf) / len(conf)) if conf else None,
            "positive": round(100 * sum(r["stance"] > 0 for r in conf) / len(conf)) if conf else None,
            "unclear": round(100 * (len(rs) - len(conf)) / len(rs)),
        })
    out.sort(key=lambda r: (r["mean"] is None, r["mean"] or 0))
    return out

