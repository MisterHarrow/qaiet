"""Every configured source parses its recorded fixture into items."""

from __future__ import annotations

import pytest

from quiet_ai.fetchers import FETCHERS
from quiet_ai.pipeline.ingest import build_tasks

# Sources that could not be recorded on the fixture date (see docs/m0-report.md).
KNOWN_MISSING: set[str] = set()


def _task_ids(ctx):
    return [t.source for t in build_tasks(ctx)]


def test_every_fetcher_has_tasks(replay_ctx):
    fetchers = {t.fetcher for t in build_tasks(replay_ctx)}
    assert fetchers == set(FETCHERS)


def test_every_source_parses_its_fixture(replay_ctx):
    failures = []
    for task in build_tasks(replay_ctx):
        res = task.execute()
        if res.status == "no_fixture" and task.source in KNOWN_MISSING:
            continue
        # A Bluesky account's latest posts can all be reposts, which we skip.
        if res.status != "ok" or (not res.items and task.fetcher != "bluesky"):
            failures.append(f"{task.source}: {res.status} {res.error or ''} items={len(res.items)}")
            continue
        for it in res.items:
            assert it.url.startswith("http"), (task.source, it.url)
            assert it.title.strip(), task.source
            assert it.fetched_at == replay_ctx.now
    assert not failures, "\n".join(failures)


def test_bluesky_fixtures_yield_posts(replay_ctx):
    tasks = [t for t in build_tasks(replay_ctx) if t.fetcher == "bluesky"]
    assert len(tasks) >= 40
    assert sum(len(t.execute().items) for t in tasks) >= 100


@pytest.mark.parametrize("fetcher", sorted(FETCHERS))
def test_item_ids_are_stable(replay_ctx, fetcher):
    tasks = [t for t in build_tasks(replay_ctx) if t.fetcher == fetcher][:5]
    first = [it.id for t in tasks for it in t.execute().items]
    second = [it.id for t in tasks for it in t.execute().items]
    assert first == second
    assert len(first) == len(set(first)) or fetcher == "news_rss"  # one feed may repeat a URL
