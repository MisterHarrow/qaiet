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
    env.globals.update(stance_names=STANCE_NAMES, kind_names=KIND_NAMES)
    return env


def stance_segments(stance: dict[str, int]) -> list[dict]:
    """Widths (percent) for the small stance bar; unlabeled items are left out of it."""
    keys = ["-2", "-1", "0", "1", "2", "unclear"]
    total = sum(stance.get(k, 0) for k in keys)
    if not total:
        return []
    return [{"key": k, "n": stance[k], "pct": round(100 * stance[k] / total, 2), "name": STANCE_NAMES[k]} for k in keys if stance.get(k)]


def stance_label(stance: dict[str, int]) -> str:
    parts = [f"{stance[k]} {STANCE_NAMES[k].lower()}" for k in ["-2", "-1", "0", "1", "2", "unclear", "unlabeled"] if stance.get(k)]
    return "Stance of the coverage: " + ", ".join(parts) if parts else "No stance labels"


def _long_date(dt: datetime) -> str:
    return f"{dt:%A} {dt.day} {dt:%B %Y}"


def period_path(index: int, key: str) -> str:
    """The first view is the front page; the others live in their own folder."""
    return "" if index == 0 else f"{key}/"


def render(edition: dict, out_dir: Path, tz: str = "Europe/Stockholm", periods: list[dict] | None = None) -> Path:
    """Render one view. `periods` lists every view ({key, label, path}) for the switcher."""
    period = edition.get("period") or {"key": "day", "label": "24 hours"}
    periods = periods or [{"key": period["key"], "label": period["label"], "path": ""}]
    me = next((p for p in periods if p["key"] == period["key"]), periods[0])
    page_dir = out_dir / me["path"]
    page_dir.mkdir(parents=True, exist_ok=True)
    root = "../" * me["path"].count("/")
    zone = ZoneInfo(tz)
    local = datetime.fromisoformat(edition["generated_at"]).astimezone(zone)
    for s in edition["stories"]:
        s["segments"] = stance_segments(s["stance"])
        s["stance_label"] = stance_label(s["stance"])
    since = edition.get("data_since")
    html = _env().get_template("index.html.j2").render(
        e=edition,
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
