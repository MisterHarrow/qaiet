"""Figures beside the food desk's news: the EU's average farm-gate prices for cereals and dairy (weekly) and
fertiliser (monthly), with their recent change.

Three requests per publish to the European Commission's Agri-food Data Portal (CC BY 4.0, no key;
docs/food-data-plan.md). Values are stored per week or month (desk_figures), frozen into the food desk's editions,
and never labeled, sent to a model or counted in the sentiment index. A failed fetch never stops the publish:
the page keeps the last values it has, dated.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from quiet_ai.config import Settings
from quiet_ai.http import FetchError, Http
from quiet_ai.store.db import Store, iso

SOURCE_URL = "https://agridata.ec.europa.eu/extensions/DataPortal/prices.html"
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
UNITS = {"cereal": "€/t", "dairy": "€/100 kg", "fertiliser": "€/t"}
UNIT_WORDS = {"cereal": "€ per tonne", "dairy": "€ per 100 kg", "fertiliser": "€ per tonne"}
_NUMBER = re.compile(r"^\d+(\.\d+)?$")


def parse_price(v) -> float | None:
    """'€209,19' (cereals), '€402.80' (dairy) or 469.0 (fertiliser) -> a float; None for empty or junk values."""
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    s = v.replace("€", "").replace(" ", "").replace(" ", "").strip()
    if "," in s and "." in s:  # the last mark is the decimal one
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    else:
        s = s.replace(",", ".")
    return float(s) if _NUMBER.match(s) else None


def _day(d: str) -> str:
    """'16/11/2026' -> '2026-11-16'."""
    return datetime.strptime(d, "%d/%m/%Y").date().isoformat()


def fetch(http: Http, settings: Settings, today: date) -> dict[str, dict[str, float]]:
    """metric -> {period start: value} for the configured products."""
    cfg = settings.food_data
    weeks = cfg.points + cfg.change_weeks + 2
    begin, end = (today - timedelta(weeks=weeks)).strftime("%d/%m/%Y"), today.strftime("%d/%m/%Y")
    out: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    if cfg.cereals:
        rows = http.get(cfg.api_url + "cereal/prices", key="agri:cereal:eu", params={
            "memberStateCodes": "EU", "productCodes": ",".join(f.code for f in cfg.cereals),
            "beginDate": begin, "endDate": end}).json()
        # Cereal rows carry the product's name, not its code, so they're stored by name (a cereal's label in
        # settings is the API's name, e.g. BLTPAN comes back as "Milling wheat").
        for r in rows:
            if r.get("marketName") != "National Average" or (p := parse_price(r.get("price"))) is None:
                continue
            out[f"cereal:{r['productName']}"][_day(r["beginDate"])].append(p)
    if cfg.dairy:
        rows = http.get(cfg.api_url + "dairy/prices", key="agri:dairy:eu", params={
            "memberStateCodes": "EU", "products": ",".join(f.code for f in cfg.dairy),
            "beginDate": begin, "endDate": end}).json()
        for r in rows:
            if (p := parse_price(r.get("price"))) is not None:
                out[f"dairy:{r['product']}"][_day(r["beginDate"])].append(p)
    if cfg.fertiliser:
        rows = http.get(cfg.api_url + "fertiliser/prices", key="agri:fertiliser",
                        params={"years": f"{today.year - 1},{today.year}"}).json()
        wanted = {f.code for f in cfg.fertiliser}
        for r in rows:
            if r.get("product") not in wanted or r.get("month") not in MONTHS or (p := parse_price(r.get("price"))) is None:
                continue
            out[f"fertiliser:{r['product']}"][date(int(r["year"]), MONTHS[r["month"]], 1).isoformat()].append(p)
    return {m: {d: sum(v) / len(v) for d, v in by.items()} for m, by in out.items()}


def save(store: Store, settings: Settings, values: dict[str, dict[str, float]], now: datetime) -> int:
    rows = [(settings.food_data.desk, m, d, round(v, 2), iso(now)) for m, by in values.items() for d, v in by.items()]
    with store.conn:
        store.conn.executemany(
            "INSERT INTO desk_figures(desk, metric, period, value, updated_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(desk, metric, period) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            rows,
        )
    return len(rows)


def update(store: Store, http: Http, settings: Settings, now: datetime) -> str:
    """Fetch and store the prices. Never raises: returns a line for the run log."""
    cfg = settings.food_data
    if not cfg.enabled or not (cfg.cereals or cfg.dairy or cfg.fertiliser):
        return "off"
    today = now.astimezone(ZoneInfo(settings.site.timezone)).date()
    try:
        values = fetch(http, settings, today)
    except FetchError as e:
        return f"food prices not updated ({e})"
    except Exception as e:  # a changed response must not stop the publish
        return f"food prices not updated ({type(e).__name__})"
    return f"{save(store, settings, values, now)} weekly or monthly food prices"


def _metrics(settings: Settings) -> list[tuple[str, str, str]]:
    """(kind, metric, label) in display order."""
    cfg = settings.food_data
    out = [("cereal", f"cereal:{f.label}", f.label) for f in cfg.cereals]
    out += [("dairy", f"dairy:{f.code}", f.label) for f in cfg.dairy]
    out += [("fertiliser", f"fertiliser:{f.code}", f.label) for f in cfg.fertiliser]
    return out


def block(store: Store, settings: Settings) -> dict | None:
    """The edition's `food_data`: each figure's latest period, its value, the change over `change_weeks` (weekly)
    or one month (monthly), and its last `points` values. None until there is data."""
    cfg = settings.food_data
    if not cfg.enabled:
        return None
    figures = []
    for kind, metric, label in _metrics(settings):
        rows = store.conn.execute(
            "SELECT period, value FROM desk_figures WHERE desk = ? AND metric = ? ORDER BY period", (cfg.desk, metric)
        ).fetchall()
        if not rows:
            continue
        series = [{"date": r["period"], "value": r["value"]} for r in rows]
        back = cfg.change_weeks if kind != "fertiliser" else 1
        before = series[-1 - back]["value"] if len(series) > back else None
        latest = series[-1]
        figures.append({
            "kind": kind, "label": label, "unit": UNITS[kind], "unit_words": UNIT_WORDS[kind], "period": latest["date"],
            "monthly": kind == "fertiliser", "value": latest["value"],
            "change_pct": round(100 * (latest["value"] - before) / before, 1) if before else None,
            "change_over": f"{back} wk" if kind != "fertiliser" else "1 mo",
            "series": series[-cfg.points:],
        })
    if not figures:
        return None
    weekly = [f["period"] for f in figures if not f["monthly"]]
    return {"kind": "farm_prices", "week": max(weekly) if weekly else None, "source": "European Commission",
            "url": SOURCE_URL, "license": "CC BY 4.0", "points": cfg.points, "figures": figures}
