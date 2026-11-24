"""Shared fetcher plumbing: a Task fetches one source and returns its items."""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime

from quiet_ai.config import Account, Settings, SourcesConfig
from quiet_ai.http import FetchError, FixtureMissing, Http, RobotsBlocked
from quiet_ai.store.models import Item


@dataclass
class Context:
    settings: Settings
    sources: SourcesConfig
    accounts: list[Account]
    http: Http
    now: datetime
    known_urls: set[str] = field(default_factory=set)  # sitemap fetcher skips pages already stored


@dataclass
class FetchResult:
    source: str
    fetcher: str
    status: str  # ok | not_modified | error | robots_blocked | no_fixture
    items: list[Item] = field(default_factory=list)
    http_status: int | None = None
    error: str | None = None
    duration_s: float = 0.0


@dataclass
class Task:
    source: str  # health label, e.g. "nyt", "github", "bluesky:simonwillison.net"
    fetcher: str  # fetcher module name, e.g. "news_rss"
    run: Callable[[], list[Item] | tuple[list[Item], str]]

    def execute(self) -> FetchResult:
        t0 = time.monotonic()
        res = FetchResult(self.source, self.fetcher, "ok")
        try:
            out = self.run()
            if isinstance(out, tuple):
                res.items, res.status = out
            else:
                res.items = out
        except RobotsBlocked as e:
            res.status, res.error = "robots_blocked", str(e)
        except FixtureMissing as e:
            res.status, res.error = "no_fixture", str(e)
        except FetchError as e:
            res.status, res.error, res.http_status = "error", str(e), e.status
        except Exception as e:  # a parsing bug in one source must not stop the run
            res.status, res.error = "error", f"{type(e).__name__}: {e}"[:300]
        res.duration_s = round(time.monotonic() - t0, 2)
        return res


def run_tasks(tasks: list[Task], workers: int) -> list[FetchResult]:
    """Run tasks in parallel; Http serializes requests to the same host."""
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        return list(ex.map(Task.execute, tasks))
