"""Render the edition to static HTML: one page, one stylesheet, a few lines of JS.

No external requests from the page: system fonts, no CDN, no analytics, no images.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

HERE = Path(__file__).parent
STANCE_NAMES = {
    "-2": "Strongly critical", "-1": "Critical", "0": "Neutral", "1": "Positive", "2": "Enthusiastic",
    "unclear": "Unclear", "unlabeled": "Not labeled",
}
KIND_NAMES = {"news": "", "newsletter": "commentary"}


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(HERE / "templates"),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["thousands"] = lambda n: f"{int(n):,}"
    env.filters["signed"] = lambda v: "–" if v is None else (f"{v:+.2f}".replace("-", "−"))
    env.globals.update(stance_names=STANCE_NAMES, kind_names=KIND_NAMES)
    return env


def stance_segments(stance: dict[str, int]) -> list[dict]:
    """Widths (percent) for the small stance bar; unlabeled items are left out of it."""
    keys = ["-2", "-1", "0", "1", "2", "unclear"]
    total = sum(stance.get(k, 0) for k in keys)
    if not total:
        return []
    return [{"key": k, "n": stance[k], "pct": round(100 * stance[k] / total, 2), "name": STANCE_NAMES[k]} for k in keys if stance.get(k)]


def stance_label(stance: dict[str, int], prefix: str = "Stance of the coverage") -> str:
    parts = [f"{stance[k]} {STANCE_NAMES[k].lower()}" for k in ["-2", "-1", "0", "1", "2", "unclear", "unlabeled"] if stance.get(k)]
    return f"{prefix}: " + ", ".join(parts) if parts else "No stance labels"


def _long_date(dt: datetime) -> str:
    return f"{dt:%A} {dt.day} {dt:%B %Y}"


def period_path(index: int, key: str) -> str:
    """The first view is the front page; the others live in their own folder."""
    return "" if index == 0 else f"{key}/"


def render(edition: dict, out_dir: Path, tz: str = "Europe/Stockholm", periods: list[dict] | None = None, rel_path: str | None = None) -> Path:
    """Render one view. `periods` lists every view ({key, label, path}) for the switcher.
    `rel_path` overrides where the page goes (used for archive pages, which get no switcher)."""
    period = edition.get("period") or {"key": "day", "label": "24 hours"}
    periods = periods if periods is not None else [{"key": period["key"], "label": period["label"], "path": ""}]
    me = next((p for p in periods if p["key"] == period["key"]), {"path": ""})
    rel = rel_path if rel_path is not None else me["path"]
    page_dir = out_dir / rel
    page_dir.mkdir(parents=True, exist_ok=True)
    root = "../" * rel.count("/")
    zone = ZoneInfo(tz)
    local = datetime.fromisoformat(edition["generated_at"]).astimezone(zone)
    mix: dict[str, int] = {}
    for s in edition["stories"]:
        s["segments"] = stance_segments(s["stance"])
        s["stance_label"] = stance_label(s["stance"])
        for k, n in s["stance"].items():
            mix[k] = mix.get(k, 0) + n
    since = edition.get("data_since")
    frozen = edition.get("frozen")
    html = _env().get_template("index.html.j2").render(
        frozen_date=_long_date(datetime.fromisoformat(frozen["date"])) if frozen else None,
        e=edition,
        mix_segments=stance_segments(mix),  # the masthead rule: every article in this view, by stance
        mix_label=stance_label(mix, "Stance of every article in this view"),
        root=root,
        period=period,
        periods=[{**p, "href": root + p["path"], "active": p["key"] == period["key"]} for p in periods],
        date_long=_long_date(local),
        updated=f"{local:%H:%M}",
        tz_name=tz.split("/")[-1],
        data_since=_long_date(datetime.fromisoformat(since).astimezone(zone)) if since else None,
    )
    (page_dir / "index.html").write_text(html, encoding="utf-8")
    shutil.copytree(HERE / "static", out_dir / "static", dirs_exist_ok=True)
    (page_dir / "edition.json").write_text(json.dumps(edition, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return page_dir / "index.html"


def render_all(editions: list[dict], out_dir: Path, tz: str = "Europe/Stockholm") -> list[Path]:
    """Render every view with a shared switcher. `editions` are in display order."""
    periods = [{"key": e["period"]["key"], "label": e["period"]["label"], "path": period_path(i, e["period"]["key"])} for i, e in enumerate(editions)]
    return [render(e, out_dir, tz, periods) for e in editions]


def render_about(context: dict, out_dir: Path, tz: str = "Europe/Stockholm") -> Path:
    """The /about page: how the site works, with numbers read from the config and the database."""
    page_dir = out_dir / "about"
    page_dir.mkdir(parents=True, exist_ok=True)
    zone = ZoneInfo(tz)
    a = dict(context)
    if a.get("data_since"):
        a["data_since_long"] = _long_date(datetime.fromisoformat(a["data_since"]).astimezone(zone))
    if a.get("health"):
        a["health"] = {**a["health"], "at_local": datetime.fromisoformat(a["health"]["at"]).astimezone(zone).strftime("%H:%M")}
    html = _env().get_template("about.html.j2").render(a=a, root="../")
    (page_dir / "index.html").write_text(html, encoding="utf-8")
    shutil.copytree(HERE / "static", out_dir / "static", dirs_exist_ok=True)
    return page_dir / "index.html"


def render_archive(editions: list[dict], out_dir: Path, tz: str = "Europe/Stockholm") -> Path:
    """One frozen page per finished day, plus /archive/ listing them (newest first)."""
    days = []
    for e in editions:
        date = e["frozen"]["date"]
        render(e, out_dir, tz, periods=[], rel_path=f"archive/{date}/")
        days.append({
            "date": date,
            "long": _long_date(datetime.fromisoformat(date)),
            "weather": e.get("weather"),
            "headlines": [s["headline"] for s in e.get("stories", [])[:3]],
            "stories": len(e.get("stories", [])),
        })
    page_dir = out_dir / "archive"
    page_dir.mkdir(parents=True, exist_ok=True)
    (page_dir / "index.html").write_text(_env().get_template("archive.html.j2").render(days=days, root="../"), encoding="utf-8")
    shutil.copytree(HERE / "static", out_dir / "static", dirs_exist_ok=True)
    return page_dir / "index.html"


def sparkline(points: list[dict], label: str) -> Markup:
    """One series of the sentiment index as a small SVG line chart: fixed -1..+1 scale (wider if
    a value falls outside), zero line, 2px line, 8px markers, hover values via <title>, and the
    latest value labeled at the end, and the area to zero shaded by sign. Colors come from CSS custom properties."""
    w, h, pad_l, pad_r, pad_y = 480, 120, 8, 56, 12
    if not points:
        return Markup(f'<p class="nodata">No {label.lower()} values yet.</p>')
    lim = max(1.0, max(abs(p["value"]) for p in points))
    y = lambda v: pad_y + (lim - v) / (2 * lim) * (h - 2 * pad_y)  # noqa: E731
    n = len(points)
    x = (lambda i: pad_l + (w - pad_l - pad_r) / 2) if n == 1 else (lambda i: pad_l + i * (w - pad_l - pad_r) / (n - 1))  # noqa: E731
    parts = [f'<svg class="spark" viewBox="0 0 {w} {h}" role="img" aria-label="{label}: daily sentiment index, {n} days">']
    for v, cls in ((lim, "grid"), (0, "zero"), (-lim, "grid")):
        parts.append(f'<line class="{cls}" x1="{pad_l}" x2="{w - pad_r}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>')
    parts.append(f'<text class="axis" x="{w - pad_r + 6}" y="{y(lim) + 4:.1f}">+{lim:g}</text>')
    parts.append(f'<text class="axis" x="{w - pad_r + 6}" y="{y(-lim) + 4:.1f}">−{lim:g}</text>')
    if n > 1:
        pts = " ".join(f"{x(i):.1f},{y(p['value']):.1f}" for i, p in enumerate(points))
        # Shade between the line and zero: sage above (positive), umber below (critical).
        y0, cid = y(0), "spark-" + "".join(c if c.isalnum() else "-" for c in label.lower())
        area = f"{x(0):.1f},{y0:.1f} {pts} {x(n - 1):.1f},{y0:.1f}"
        parts.append(f'<defs><clipPath id="{cid}-up"><rect x="0" y="0" width="{w}" height="{y0:.1f}"/></clipPath>'
                     f'<clipPath id="{cid}-dn"><rect x="0" y="{y0:.1f}" width="{w}" height="{h - y0:.1f}"/></clipPath></defs>')
        parts.append(f'<polygon class="area-pos" clip-path="url(#{cid}-up)" points="{area}"/>')
        parts.append(f'<polygon class="area-neg" clip-path="url(#{cid}-dn)" points="{area}"/>')
        parts.append(f'<polyline class="line" points="{pts}"/>')
    for i, p in enumerate(points):
        val = f"{p['value']:+.2f}".replace("-", "−")
        parts.append(f'<g class="pt"><title>{p["date"]}: {val} ({p["outlets"]} outlets, {p["labels"]} labels)</title>'
                     f'<circle class="hit" cx="{x(i):.1f}" cy="{y(p["value"]):.1f}" r="12"/>'
                     f'<circle class="dot" cx="{x(i):.1f}" cy="{y(p["value"]):.1f}" r="4"/></g>')
    last = points[-1]
    parts.append(f'<text class="last" x="{x(n - 1) + 10:.1f}" y="{y(last["value"]) + 5:.1f}">{f"{last["value"]:+.2f}".replace("-", "−")}</text>')
    parts.append("</svg>")
    return Markup("".join(parts))


def render_sentiment(history: dict, out_dir: Path, tz: str = "Europe/Stockholm") -> Path:
    """/sentiment/: the daily AI sentiment index, overall and per track, with a table view."""
    from quiet_ai.pipeline.sentiment import describe

    page_dir = out_dir / "sentiment"
    page_dir.mkdir(parents=True, exist_ok=True)
    series = [("all", "All coverage"), ("technical", "Technical"), ("political", "Political"), ("economic", "Economic")]
    charts = [{"key": k, "label": lab, "svg": sparkline(history.get(k, []), lab), "latest": (history.get(k) or [None])[-1]} for k, lab in series]
    dates = sorted({p["date"] for pts in history.values() for p in pts}, reverse=True)
    table = [{"date": d, "long": _long_date(datetime.fromisoformat(d)),
              **{k: next((p for p in history.get(k, []) if p["date"] == d), None) for k, _ in series}} for d in dates[:60]]
    latest = charts[0]["latest"]
    html = _env().get_template("sentiment.html.j2").render(
        root="../", charts=charts, table=table, latest=latest,
        latest_long=_long_date(datetime.fromisoformat(latest["date"])) if latest else None,
        words=describe(latest["value"]) if latest else None, tracks=charts[1:], days=len(dates),
    )
    (page_dir / "index.html").write_text(html, encoding="utf-8")
    shutil.copytree(HERE / "static", out_dir / "static", dirs_exist_ok=True)
    return page_dir / "index.html"
