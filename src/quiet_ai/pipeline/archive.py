"""Daily editions and housekeeping.

Every run stores the front-page edition under its local date (Europe/Stockholm). Once a date
is over (00:00 local), its last edition is written to editions/<date>.json, committed by the
workflow and rendered as a permanent page under /archive/<date>/.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from quiet_ai.store.db import Store, iso


def local_date(now: datetime, tz: str) -> str:
    return now.astimezone(ZoneInfo(tz)).date().isoformat()


def save_day_edition(store: Store, edition: dict, now: datetime, tz: str) -> str:
    date = local_date(now, tz)
    with store.conn:
        store.conn.execute(
            "INSERT INTO editions(date, data, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(date) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
            (date, json.dumps(edition, ensure_ascii=False, default=str), iso(now)),
        )
    return date


def freeze(store: Store, editions_dir: Path, now: datetime, tz: str) -> list[str]:
    """Write every finished day that has no file yet. Returns the dates written."""
    today = local_date(now, tz)
    editions_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for r in store.conn.execute("SELECT date, data FROM editions WHERE date < ? ORDER BY date", (today,)):
        path = editions_dir / f"{r['date']}.json"
        if path.exists():
            continue
        edition = json.loads(r["data"])
        edition["frozen"] = {"date": r["date"], "at": iso(now)}
        path.write_text(json.dumps(edition, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        written.append(r["date"])
    return written


def load_frozen(editions_dir: Path) -> list[dict]:
    """Frozen editions, newest first."""
    out = []
    for path in sorted(editions_dir.glob("*.json"), reverse=True):
        out.append(json.loads(path.read_text(encoding="utf-8")))
    return out


def prune(store: Store, now: datetime, vacuum: bool = False) -> dict[str, int]:
    """Keep the database small enough to download on every run:
    - items judged not about AI: dropped after 15 days (feeds stop returning them after 14);
    - everything else: kept 400 days, enough for the 1-year view;
    - metric snapshots older than 7 days: thinned to one per item per day;
    - run logs: 30 days; weather reports: 60 days.
    """
    day = lambda n: iso(now - timedelta(days=n))  # noqa: E731
    counts = {}
    with store.conn:
        counts["irrelevant_items"] = store.conn.execute(
            "DELETE FROM items WHERE relevant = 0 AND first_seen_at < ?", (day(15),)).rowcount
        counts["old_items"] = store.conn.execute("DELETE FROM items WHERE first_seen_at < ?", (day(400),)).rowcount
        counts["snapshots"] = store.conn.execute(
            "DELETE FROM metric_snapshots WHERE observed_at < ? AND rowid NOT IN ("
            "SELECT MAX(rowid) FROM metric_snapshots WHERE observed_at < ? GROUP BY item_id, substr(observed_at, 1, 10))",
            (day(7), day(7)),
        ).rowcount
        counts["empty_stories"] = store.conn.execute(
            "DELETE FROM stories WHERE NOT EXISTS (SELECT 1 FROM items WHERE items.story_id = stories.id) AND last_item_at < ?",
            (day(3),),
        ).rowcount
        counts["runs"] = store.conn.execute("DELETE FROM runs WHERE started_at < ?", (day(30),)).rowcount
        counts["reports"] = store.conn.execute("DELETE FROM reports WHERE created_at < ?", (day(60),)).rowcount
    if vacuum:
        store.conn.execute("VACUUM")
    return counts
