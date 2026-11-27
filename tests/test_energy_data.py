"""The energy desk's day-ahead prices: fetched once per publish, stored as daily values, shown beside the news."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import httpx
from typer.testing import CliRunner

from quiet_ai.cli import app
from quiet_ai.http import Http
from quiet_ai.pipeline import energy_data
from quiet_ai.site import build
from quiet_ai.store.db import Store

NOW = datetime(2026, 11, 27, 5, 30, tzinfo=timezone.utc)  # 06:30 in Stockholm, the morning publish


def quarter_hours(area: str, day: str, price: float, n: int = 96) -> list[dict]:
    """A Stockholm day's 15-minute prices (CET is UTC+1 in November)."""
    start = datetime.fromisoformat(day).replace(tzinfo=timezone.utc) - timedelta(hours=1)
    return [{"TimeUTC": (start + timedelta(minutes=15 * i)).strftime("%Y-%m-%dT%H:%M:%S"), "PriceArea": area,
             "DayAheadPriceEUR": price + (i % 4)} for i in range(n)]


def http_returning(settings, records, seen=None, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json={"records": records})

    return Http(settings.http, transport=httpx.MockTransport(handler), sleep=lambda s: None)


def test_prices_are_grouped_by_stockholm_day():
    recs = [{"TimeUTC": "2026-11-26T22:45:00", "PriceArea": "SE3", "DayAheadPriceEUR": 10.0},  # 23:45 on the 26th
            {"TimeUTC": "2026-11-26T23:00:00", "PriceArea": "SE3", "DayAheadPriceEUR": 20.0}]  # 00:00 on the 27th
    days = energy_data.daily(recs, "Europe/Stockholm")
    assert days == {("SE3", "2026-11-26"): [10.0], ("SE3", "2026-11-27"): [20.0]}


def test_one_request_in_danish_time_for_the_configured_areas(settings):
    seen = []
    http = http_returning(settings, [], seen)
    energy_data.update(Store(":memory:"), http, settings, NOW)
    assert len(seen) == 1
    q = parse_qs(urlsplit(str(seen[0].url)).query)
    assert q["start"] == ["2026-11-21T00:00"] and q["end"] == ["2026-11-29T00:00"]  # a week back, through tomorrow
    assert all(a.code in q["filter"][0] for a in settings.energy_data.price_areas)


def test_block_shows_the_latest_day_and_a_week_of_means(settings):
    store = Store(":memory:")
    recs = []
    for i, day in enumerate(["2026-11-25", "2026-11-26", "2026-11-27", "2026-11-28"]):  # the 28th is tomorrow
        recs += quarter_hours("SE3", day, 100.0 + 10 * i)
    recs += quarter_hours("DE", "2026-11-27", -5.0, n=40)  # half a day so far
    assert energy_data.update(store, http_returning(settings, recs), settings, NOW).startswith("5 area-days")
    b = energy_data.block(store, settings, NOW)
    assert b["day"] == "2026-11-27" and b["source"] == "Energinet" and b["license"] == "CC BY 4.0"
    se3 = next(a for a in b["areas"] if a["code"] == "SE3")
    assert se3["mean"] == 121.5 and se3["min"] == 120.0 and se3["max"] == 123.0 and not se3["partial"]
    assert [p["date"] for p in se3["series"]] == ["2026-11-25", "2026-11-26", "2026-11-27"]  # not tomorrow
    de = next(a for a in b["areas"] if a["code"] == "DE")
    assert de["partial"] and de["min"] == -5.0
    assert [a["code"] for a in b["areas"]] == ["SE3", "DE"]  # areas without that day are left out, order kept


def test_a_failed_fetch_keeps_the_last_day_and_never_raises(settings):
    store = Store(":memory:")
    energy_data.update(store, http_returning(settings, quarter_hours("SE4", "2026-11-26", 50.0)), settings, NOW)
    note = energy_data.update(store, http_returning(settings, [], status=500), settings, NOW)
    assert note.startswith("prices not updated")
    assert energy_data.block(store, settings, NOW)["day"] == "2026-11-26"


def test_off_or_empty_gives_no_block(settings):
    store = Store(":memory:")
    assert energy_data.block(store, settings, NOW) is None
    settings.energy_data.enabled = False
    assert energy_data.update(store, None, settings, NOW) == "off"


def test_price_sparkline_is_ink_only():
    svg = str(build.price_spark([{"date": "2026-11-26", "value": -3.0}, {"date": "2026-11-27", "value": 120.4}], "Sweden SE3"))
    assert 'aria-label="Sweden SE3: daily mean over 2 days, −3 to 120 € per MWh"' in svg
    assert "polyline" in svg and 'class="now"' in svg
    for stance in ("crit", "pos", "area-", "signal"):
        assert stance not in svg


def test_dry_run_build_shows_the_strip_on_the_energy_desk_only(tmp_path):
    res = CliRunner().invoke(app, ["build", "--dry-run", "--out", str(tmp_path)])
    assert res.exit_code == 0, res.output
    energy = (tmp_path / "energy" / "index.html").read_text()
    assert '<section class="data-strip"' in energy and "Sweden SE3" in energy and "energidataservice.dk" in energy
    assert "data-strip" not in (tmp_path / "index.html").read_text()
    assert "data-strip" not in (tmp_path / "biotech" / "index.html").read_text()
    assert "under CC BY 4.0 (Source: Energinet)" in (tmp_path / "about" / "index.html").read_text()


def test_qa_energy_fetches_into_the_database_and_never_fails(settings, tmp_path, monkeypatch):
    from quiet_ai import cli
    from tests.conftest import make_ctx

    settings.db_path = str(tmp_path / "q.db")
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    recs = quarter_hours("SE3", "2026-11-27", 80.0)
    monkeypatch.setattr(cli, "_context", lambda mode, fetch_state=None: make_ctx(settings, http_returning(settings, recs), now=NOW))
    res = CliRunner().invoke(app, ["energy"])
    assert res.exit_code == 0 and "1 area-days" in res.output, res.output
    assert energy_data.block(Store(settings.db_path), settings, NOW)["areas"][0]["mean"] == 81.5
    monkeypatch.setattr(cli, "_context", lambda mode, fetch_state=None: make_ctx(settings, http_returning(settings, [], status=503), now=NOW))
    res = CliRunner().invoke(app, ["energy"])
    assert res.exit_code == 0 and "prices not updated" in res.output  # a deploy never fails on it
