"""Ingest: run every fetcher, store items, record source health."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from quiet_ai.fetchers import FETCHERS
from quiet_ai.fetchers.base import Context, FetchResult, Task, run_tasks
from quiet_ai.store.db import Store
from quiet_ai.store.models import Item

# Kinds whose published_at is a publication date. For repos/models/datasets/spaces it's a
# creation date, and an old repo can still be trending.
DATED_KINDS = {"news", "aggregator", "newsletter", "lab", "launch", "hn", "social", "paper"}


@dataclass
class SourceReport:
    result: FetchResult
    new: int


def build_tasks(ctx: Context, only: list[str] | None = None) -> list[Task]:
    tasks = [t for module in FETCHERS.values() for t in module.tasks(ctx)]
    if only:
        wanted = set(only)
        tasks = [t for t in tasks if t.source in wanted or t.fetcher in wanted or t.source.split(":")[0] in wanted]
    return tasks


def drop_stale(items: list[Item], now: datetime, max_age_days: int) -> list[Item]:
    cutoff = now - timedelta(days=max_age_days)
    return [it for it in items if it.kind not in DATED_KINDS or not it.published_at or it.published_at >= cutoff]


def ingest(ctx: Context, store: Store, only: list[str] | None = None, dry_run: bool = False) -> list[SourceReport]:
    run_id = store.start_run("ingest", dry_run, ctx.now)
    results = run_tasks(build_tasks(ctx, only), ctx.settings.http.workers)
    reports = []
    failed_prefixes = []
    for res in results:
        res.items = drop_stale(res.items, ctx.now, ctx.settings.ingest.max_age_days)
        new = store.upsert_items(res.items, ctx.now) if res.status in ("ok", "not_modified") else 0
        if res.status not in ("ok", "not_modified"):
            failed_prefixes.append(f"rss:{res.source}:")
        store.record_source_run(
            run_id, res.source, res.fetcher, res.status, res.http_status, len(res.items), new, res.error, res.duration_s
        )
        reports.append(SourceReport(res, new))
    # Don't remember ETags for feeds whose body we failed to parse, or we'd never re-read them.
    updates = {
        url: st for url, st in ctx.http.state_updates.items()
        if not any(str(st.get("key", "")).startswith(p) for p in failed_prefixes)
    }
    store.save_fetch_state(updates, ctx.now)
    store.finish_run(run_id, datetime.now(ctx.now.tzinfo))
    return reports
