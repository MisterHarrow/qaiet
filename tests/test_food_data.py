"""The food desk's EU farm prices: fetched once per publish, stored per week or month, shown beside the news."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import httpx
from typer.testing import CliRunner

from quiet_ai.cli import app
from quiet_ai.http import Http
from quiet_ai.pipeline import food_data
from quiet_ai.store.db import Store

NOW = datetime(2026, 11, 27, 5, 30, tzinfo=timezone.utc)


def weeks(n: int, last: date = date(2026, 11, 16)) -> list[str]:
    return [(last - timedelta(weeks=n - 1 - i)).strftime("%d/%m/%Y") for i in range(n)]


def api(cereal=None, dairy=None, fertiliser=None, seen=None, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if seen is not None:
            seen.append(request)
        if status != 200:
            return httpx.Response(status)
        path = request.url.path
        body = cereal if "cereal" in path else dairy if "dairy" in path else fertiliser
        return httpx.Response(200, json=body or [])

    return handler


def http(settings, handler):
    return Http(settings.http, transport=httpx.MockTransport(handler), sleep=lambda s: None)


def cereal_rows(name: str, prices: list[str]) -> list[dict]:
    return [{"memberStateCode": "EU", "beginDate": d, "price": p, "productName": name, "marketName": "National Average",
             "stageName": "Deliver to first customer"} for d, p in zip(weeks(len(prices)), prices)]


def test_prices_parse_both_decimal_marks_and_skip_junk():
    assert food_data.parse_price("€209,19") == 209.19
    assert food_data.parse_price("€402.80") == 402.8
    assert food_data.parse_price("€1.234,56") == 1234.56 and food_data.parse_price("€1,234.56") == 1234.56
    assert food_data.parse_price(469.0) == 469.0
    for junk in ("€#######", "€,99", None, ""):
        assert food_data.parse_price(junk) is None


def test_eu_averages_by_week_with_a_four_week_change(settings):
    store = Store(":memory:")
    prices = ["€200,00"] * 8 + ["€190,00", "€195,00", "€205,00", "€209,00", "€209,19"]  # 13 weeks, newest last
    rows = cereal_rows("Milling wheat", prices) + [
        {**cereal_rows("Milling wheat", ["€999,00"])[0], "marketName": "Rouen"},     # a single market, not the average
        {**cereal_rows("Feed maize", ["€#######"])[0]},                               # junk is skipped
    ]
    dairy = [{"memberStateCode": "EU", "beginDate": d, "price": "€402.80", "product": "BUTTER"} for d in weeks(2)]
    fert = [{"year": 2026, "month": m, "product": "N (Nitrogen)", "price": p} for m, p in (("Aug", 454.0), ("Sep", 469.0))]
    seen = []
    note = food_data.update(store, http(settings, api(rows, dairy, fert, seen)), settings, NOW)
    assert note.endswith("food prices") and len(seen) == 3
    q = parse_qs(urlsplit(str(seen[0].url)).query)
    assert q["memberStateCodes"] == ["EU"] and q["productCodes"] == ["BLTPAN,MAI,ORGFOUR"] and q["endDate"] == ["27/11/2026"]
    b = food_data.block(store, settings)
    assert b["week"] == "2026-11-16" and b["source"] == "European Commission" and b["license"] == "CC BY 4.0"
    wheat, butter, nitrogen = (next(f for f in b["figures"] if f["label"] == x) for x in ("Milling wheat", "Butter", "Nitrogen fertiliser"))
    assert wheat["value"] == 209.19 and wheat["change_pct"] == 10.1 and wheat["change_over"] == "4 wk"  # vs €190
    assert len(wheat["series"]) == settings.food_data.points and wheat["unit"] == "€/t"
    assert butter["unit"] == "€/100 kg" and butter["change_pct"] is None  # two weeks: no four-week change yet
    assert nitrogen["monthly"] and nitrogen["period"] == "2026-09-01" and nitrogen["change_pct"] == 3.3
    assert [f["label"] for f in b["figures"]] == ["Milling wheat", "Butter", "Nitrogen fertiliser"]  # no data, no row


def test_a_failed_fetch_keeps_the_last_values_and_never_raises(settings):
    store = Store(":memory:")
    food_data.update(store, http(settings, api(cereal_rows("Feed barley", ["€179,19"]))), settings, NOW)
    note = food_data.update(store, http(settings, api(status=500)), settings, NOW)  # an unknown filter gives 500
    assert note.startswith("food prices not updated")
    assert food_data.block(store, settings)["figures"][0]["value"] == 179.19


def test_off_gives_no_block(settings):
    settings.food_data.enabled = False
    assert food_data.update(Store(":memory:"), None, settings, NOW) == "off"
    assert food_data.block(Store(":memory:"), settings) is None


def test_dry_run_build_shows_the_strip_on_the_food_desk_only(tmp_path):
    res = CliRunner().invoke(app, ["build", "--dry-run", "--out", str(tmp_path)])
    assert res.exit_code == 0, res.output
    food = (tmp_path / "food" / "index.html").read_text()
    assert 'id="farm-h">EU farm prices' in food and "Milling wheat" in food and "Nitrogen fertiliser · Sep 2026" in food
    assert "agridata.ec.europa.eu" in food and "€ per 100 kg" in food
    for page in ("index.html", "energy/index.html", "space/index.html"):
        assert "farm-h" not in (tmp_path / page).read_text(), page
    assert "Agri-food Data Portal</a> under CC BY 4.0" in (tmp_path / "about" / "index.html").read_text()
