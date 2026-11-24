from __future__ import annotations

import json
from datetime import timedelta

from typer.testing import CliRunner

from quiet_ai.cli import app
from quiet_ai.pipeline.ingest import drop_stale, ingest
from quiet_ai.store.db import Store
from quiet_ai.store.models import Item, Metrics
from tests.conftest import NOW


def item(i, kind="news", stars=None, published=NOW, **kw) -> Item:
    return Item(id=f"x:{i}", source="s", kind=kind, url=f"https://e.com/{i}", title=f"t{i}",
                published_at=published, metrics=Metrics(stars=stars), fetched_at=NOW, **kw)


def test_upsert_is_idempotent_and_snapshots_metrics():
    st = Store(":memory:")
    assert st.upsert_items([item(1, kind="repo", stars=10), item(2)], NOW) == 2
    assert st.upsert_items([item(1, kind="repo", stars=25), item(2)], NOW + timedelta(hours=2)) == 0
    assert st.count_items() == {"repo": 1, "news": 1}
    snaps = st.conn.execute("SELECT metrics FROM metric_snapshots WHERE item_id='x:1' ORDER BY observed_at").fetchall()
    assert [json.loads(r["metrics"])["stars"] for r in snaps] == [10, 25]
    row = st.conn.execute("SELECT first_seen_at, last_seen_at FROM items WHERE id='x:1'").fetchone()
    assert row["first_seen_at"] < row["last_seen_at"]


def test_upsert_keeps_first_published_and_summary():
    st = Store(":memory:")
    st.upsert_items([item(1, summary="first")], NOW)
    st.upsert_items([item(1, summary=None, published=NOW + timedelta(days=1))], NOW + timedelta(hours=1))
    row = st.conn.execute("SELECT summary, published_at FROM items").fetchone()
    assert row["summary"] == "first" and row["published_at"].startswith("2026-11-24T08")


def test_fetch_state_roundtrip():
    st = Store(":memory:")
    st.save_fetch_state({"https://e.com/f": {"etag": '"a"', "last_modified": None, "key": "rss:e:0"}}, NOW)
    assert st.load_fetch_state() == {"https://e.com/f": {"etag": '"a"', "last_modified": None}}


def test_drop_stale_exempts_repos_and_undated():
    old = NOW - timedelta(days=30)
    kept = drop_stale([item(1, published=old), item(2, kind="repo", published=old), item(3, published=None), item(4)], NOW, 14)
    assert [i.id for i in kept] == ["x:2", "x:3", "x:4"]


def test_ingest_replay_records_health(replay_ctx):
    st = Store(":memory:")
    reports = ingest(replay_ctx, st, only=["news_rss", "github"], dry_run=True)
    assert reports and all(r.result.status in ("ok", "no_fixture") for r in reports)
    rows = st.conn.execute("SELECT status, COUNT(*) n FROM source_runs GROUP BY status").fetchall()
    assert {r["status"] for r in rows} <= {"ok", "no_fixture"}
    # Second run over the same fixtures adds nothing new.
    again = ingest(replay_ctx, st, only=["news_rss", "github"], dry_run=True)
    assert sum(r.new for r in again) == 0


def test_cli_dry_run_ingest_and_sources_check():
    runner = CliRunner()
    res = runner.invoke(app, ["ingest", "--dry-run", "-s", "hackernews", "-s", "techmeme"])
    assert res.exit_code == 0, res.output
    assert "new items stored" in res.output and "in memory only" in res.output
    res = runner.invoke(app, ["sources", "check", "--dry-run", "-s", "openrouter", "--strict"])
    assert res.exit_code == 0, res.output


def test_cli_dry_run_cluster():
    res = CliRunner().invoke(app, ["cluster", "--dry-run", "-n", "5"])
    assert res.exit_code == 0, res.output
    assert "stories, last 72h" in res.output and "placed" in res.output
