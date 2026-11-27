"""Figures beside the energy desk's news: today's day-ahead power price per price area, with a week of daily means.

One request per publish to Energinet's Energi Data Service (CC BY 4.0, no key; docs/energy-data-plan.md). The
figures are stored as daily values (energy_daily), frozen into the energy desk's editions, and never labeled,
sent to a model or counted in the sentiment index. A failed fetch never stops the publish: the page keeps the
last day it has, dated.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from quiet_ai.config import Settings
from quiet_ai.http import FetchError, Http
from quiet_ai.store.db import Store, iso

SOURCE = "energinet"
FIXTURE_KEY = "energy:energinet:dayahead"
PAGE_URL = "https://www.energidataservice.dk/tso-electricity/DayAheadPrices"
# Energinet's start and end are Danish local time, the same zone as Stockholm's.
DK = ZoneInfo("Europe/Copenhagen")


def fetch_prices(http: Http, settings: Settings, now: datetime) -> list[dict]:
    """The 15-minute day-ahead prices of the configured areas, from the first sparkline day to the end of tomorrow
    (tomorrow's prices appear after the early-afternoon auction)."""
    cfg = settings.energy_data
    today = now.astimezone(DK).date()
    start = today - timedelta(days=cfg.days - 1)
    end = today + timedelta(days=2)
    r = http.get(cfg.prices_url, key=FIXTURE_KEY, params={
        "start": f"{start.isoformat()}T00:00",
        "end": f"{end.isoformat()}T00:00",
        "filter": json.dumps({"PriceArea": [a.code for a in cfg.price_areas]}, separators=(",", ":")),
        "sort": "TimeUTC asc",
        "limit": 20000,
    })
    return r.json().get("records") or []


def daily(records: list[dict], tz: str) -> dict[tuple[str, str], list[float]]:
    """(area, local date) -> that day's 15-minute prices in EUR/MWh."""
    zone = ZoneInfo(tz)
    out: dict[tuple[str, str], list[float]] = defaultdict(list)
    for rec in records:
        area, t, price = rec.get("PriceArea"), rec.get("TimeUTC"), rec.get("DayAheadPriceEUR")
        if not area or not t or price is None:
            continue
        day = datetime.fromisoformat(t).replace(tzinfo=timezone.utc).astimezone(zone).date().isoformat()
        out[(area, day)].append(float(price))
    return out


def save(store: Store, days: dict[tuple[str, str], list[float]], now: datetime) -> int:
    rows = []
    for (area, day), prices in days.items():
        for metric, value in (("price_mean", sum(prices) / len(prices)), ("price_min", min(prices)), ("price_max", max(prices))):
            rows.append((SOURCE, metric, area, day, round(value, 2), len(prices), iso(now)))
    with store.conn:
        store.conn.executemany(
            "INSERT INTO energy_daily(source, metric, zone, day, value, points, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(source, metric, zone, day) DO UPDATE SET value = excluded.value, points = excluded.points, "
            "updated_at = excluded.updated_at",
            rows,
        )
    return len(days)


def update(store: Store, http: Http, settings: Settings, now: datetime) -> str:
    """Fetch and store the prices. Never raises: returns a line for the run log."""
    cfg = settings.energy_data
    if not cfg.enabled or not cfg.price_areas:
        return "off"
    try:
        records = fetch_prices(http, settings, now)
    except FetchError as e:
        return f"prices not updated ({e})"
    except Exception as e:  # a changed response must not stop the publish
        return f"prices not updated ({type(e).__name__})"
    n = save(store, daily(records, settings.site.timezone), now)
    return f"{n} area-days of day-ahead prices"


def block(store: Store, settings: Settings, now: datetime) -> dict | None:
    """The edition's `energy_data`: each area's latest day up to today (mean, min, max) and its daily means over
    the sparkline's days. None until there is data."""
    cfg = settings.energy_data
    if not cfg.enabled or not cfg.price_areas:
        return None
    today = now.astimezone(ZoneInfo(settings.site.timezone)).date().isoformat()
    rows = store.conn.execute(
        "SELECT metric, zone, day, value, points FROM energy_daily WHERE source = ? AND day <= ? ORDER BY day",
        (SOURCE, today),
    ).fetchall()
    by: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(dict))
    for r in rows:
        by[r["zone"]][r["day"]][r["metric"]] = r["value"]
        by[r["zone"]][r["day"]]["points"] = r["points"]
    days = sorted({d for z in by.values() for d in z})
    if not days:
        return None
    latest = days[-1]
    areas = []
    for a in cfg.price_areas:
        z = by.get(a.code, {})
        if latest not in z:
            continue
        d = z[latest]
        series = [{"date": day, "value": z[day]["price_mean"]} for day in days[-cfg.days:] if day in z]
        areas.append({"code": a.code, "label": a.label, "mean": d["price_mean"], "min": d["price_min"],
                      "max": d["price_max"], "partial": d["points"] < cfg.min_points, "series": series})
    if not areas:
        return None
    return {"kind": "day_ahead_prices", "day": latest, "unit": "EUR/MWh", "source": "Energinet", "url": PAGE_URL,
            "license": "CC BY 4.0", "days": cfg.days, "areas": areas}
