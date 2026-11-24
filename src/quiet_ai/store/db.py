"""SQLite store: plain sqlite3 plus a small repository layer."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from quiet_ai.store.models import Item

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id            TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    kind          TEXT NOT NULL,
    url           TEXT NOT NULL,
    title         TEXT NOT NULL,
    original_title TEXT,
    lang          TEXT,
    published_at  TEXT,
    author        TEXT,
    summary       TEXT,
    metrics       TEXT NOT NULL DEFAULT '{}',
    extra         TEXT NOT NULL DEFAULT '{}',
    content_hash  TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS items_source ON items(source);
CREATE INDEX IF NOT EXISTS items_kind_published ON items(kind, published_at);
CREATE INDEX IF NOT EXISTS items_first_seen ON items(first_seen_at);
CREATE INDEX IF NOT EXISTS items_url ON items(url);

-- One row per item per run where it had metrics: star velocity, points growth, etc.
CREATE TABLE IF NOT EXISTS metric_snapshots (
    item_id     TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    observed_at TEXT NOT NULL,
    metrics     TEXT NOT NULL,
    PRIMARY KEY (item_id, observed_at)
);

-- Conditional GET state per feed URL.
CREATE TABLE IF NOT EXISTS fetch_state (
    url           TEXT PRIMARY KEY,
    etag          TEXT,
    last_modified TEXT,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    command     TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    dry_run     INTEGER NOT NULL DEFAULT 0
);

-- Source health: one row per source per run.
CREATE TABLE IF NOT EXISTS source_runs (
    run_id      TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    source      TEXT NOT NULL,
    fetcher     TEXT NOT NULL,
    status      TEXT NOT NULL,   -- ok | not_modified | error | robots_blocked | no_fixture | disabled
    http_status INTEGER,
    items_seen  INTEGER NOT NULL DEFAULT 0,
    items_new   INTEGER NOT NULL DEFAULT 0,
    error       TEXT,
    duration_s  REAL,
    PRIMARY KEY (run_id, source)
);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.migrate()

    def close(self) -> None:
        self.conn.close()

    def migrate(self) -> None:
        with self.conn:
            self.conn.executescript(SCHEMA)
            self.conn.execute(
                "INSERT INTO meta(key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(SCHEMA_VERSION),),
            )

    # -- runs ----------------------------------------------------------------------------

    def start_run(self, command: str, dry_run: bool, now: datetime) -> str:
        run_id = now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
        with self.conn:
            self.conn.execute(
                "INSERT INTO runs(run_id, command, started_at, dry_run) VALUES (?, ?, ?, ?)",
                (run_id, command, iso(now), int(dry_run)),
            )
        return run_id

    def finish_run(self, run_id: str, now: datetime) -> None:
        with self.conn:
            self.conn.execute("UPDATE runs SET finished_at = ? WHERE run_id = ?", (iso(now), run_id))

    def record_source_run(
        self,
        run_id: str,
        source: str,
        fetcher: str,
        status: str,
        http_status: int | None,
        items_seen: int,
        items_new: int,
        error: str | None,
        duration_s: float | None,
    ) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO source_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, source, fetcher, status, http_status, items_seen, items_new, error, duration_s),
            )

    # -- items ---------------------------------------------------------------------------

    def upsert_items(self, items: Iterable[Item], observed_at: datetime) -> int:
        """Insert new items, refresh existing ones. Returns how many were new."""
        items = list({it.id: it for it in items}.values())
        if not items:
            return 0
        seen = iso(observed_at)
        existing = self._existing_ids([it.id for it in items])
        with self.conn:
            for it in items:
                metrics = it.metrics.nonempty()
                self.conn.execute(
                    """
                    INSERT INTO items (id, source, kind, url, title, original_title, lang, published_at, author,
                                       summary, metrics, extra, content_hash, first_seen_at, last_seen_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title        = excluded.title,
                        original_title = COALESCE(excluded.original_title, items.original_title),
                        summary      = COALESCE(excluded.summary, items.summary),
                        author       = COALESCE(items.author, excluded.author),
                        published_at = COALESCE(items.published_at, excluded.published_at),
                        metrics      = excluded.metrics,
                        extra        = excluded.extra,
                        content_hash = excluded.content_hash,
                        last_seen_at = excluded.last_seen_at
                    """,
                    (
                        it.id, it.source, it.kind, it.url, it.title, it.original_title, it.lang,
                        iso(it.published_at), it.author, it.summary, json.dumps(metrics, sort_keys=True),
                        json.dumps(it.extra, sort_keys=True, default=str), it.content_hash, seen, seen,
                    ),
                )
                if metrics:
                    self.conn.execute(
                        "INSERT OR REPLACE INTO metric_snapshots(item_id, observed_at, metrics) VALUES (?, ?, ?)",
                        (it.id, seen, json.dumps(metrics, sort_keys=True)),
                    )
        return sum(1 for it in items if it.id not in existing)

    def _existing_ids(self, ids: list[str]) -> set[str]:
        out: set[str] = set()
        for i in range(0, len(ids), 500):
            chunk = ids[i : i + 500]
            rows = self.conn.execute(f"SELECT id FROM items WHERE id IN ({','.join('?' * len(chunk))})", chunk)
            out.update(r["id"] for r in rows)
        return out

    def urls_for_sources(self, sources: list[str]) -> set[str]:
        if not sources:
            return set()
        rows = self.conn.execute(f"SELECT url FROM items WHERE source IN ({','.join('?' * len(sources))})", sources)
        return {r["url"] for r in rows}

    def count_items(self) -> dict[str, int]:
        rows = self.conn.execute("SELECT kind, COUNT(*) AS n FROM items GROUP BY kind ORDER BY n DESC")
        return {r["kind"]: r["n"] for r in rows}

    # -- conditional GET state -----------------------------------------------------------

    def load_fetch_state(self) -> dict[str, dict]:
        rows = self.conn.execute("SELECT url, etag, last_modified FROM fetch_state")
        return {r["url"]: {"etag": r["etag"], "last_modified": r["last_modified"]} for r in rows}

    def save_fetch_state(self, updates: dict[str, dict], now: datetime) -> None:
        with self.conn:
            for url, st in updates.items():
                self.conn.execute(
                    "INSERT INTO fetch_state(url, etag, last_modified, updated_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(url) DO UPDATE SET etag = excluded.etag, "
                    "last_modified = excluded.last_modified, updated_at = excluded.updated_at",
                    (url, st.get("etag"), st.get("last_modified"), iso(now)),
                )
