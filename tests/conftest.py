from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from quiet_ai.config import load_accounts, load_settings, load_sources
from quiet_ai.fetchers.base import Context
from quiet_ai.http import Http

FIXTURES = Path(__file__).parent / "fixtures" / "http"
NOW = datetime(2026, 11, 24, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def settings():
    s = load_settings()
    s.http.min_interval_s = 0
    s.http.host_min_interval_s = {}
    s.http.backoff_base_s = 0
    return s


@pytest.fixture
def replay_ctx(settings):
    recorded_at = datetime.fromisoformat(json.loads((FIXTURES / "meta.json").read_text())["recorded_at"])
    http = Http(settings.http, mode="replay", fixtures_dir=FIXTURES)
    yield Context(settings=settings, sources=load_sources(), accounts=load_accounts(), http=http, now=recorded_at)
    http.close()


def make_ctx(settings, http, now=NOW, accounts=None, sources=None):
    return Context(
        settings=settings,
        sources=sources or load_sources(),
        accounts=accounts if accounts is not None else load_accounts(),
        http=http,
        now=now,
    )
