"""Render the edition to static HTML: one page, one stylesheet, a few lines of JS.

No external requests from the page: system fonts, no CDN, no analytics, no images.
"""

from __future__ import annotations

import json
import math
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import re

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

HERE = Path(__file__).parent
STANCE_NAMES = {
    "-2": "Strongly critical", "-1": "Critical", "0": "Neutral", "1": "Positive", "2": "Enthusiastic",
    "unclear": "Unclear", "unlabeled": "Not labeled",
}
KIND_NAMES = {"news": "", "newsletter": "commentary"}
# Outlet countries (ISO codes in sources.yaml), named on hover.
COUNTRY_NAMES = {
    "AU": "Australia", "BE": "Belgium", "CA": "Canada", "CN": "China", "DE": "Germany", "ES": "Spain", "FR": "France",
    "GB": "United Kingdom", "HK": "Hong Kong", "IN": "India", "JP": "Japan", "KR": "South Korea", "QA": "Qatar",
    "SE": "Sweden", "SG": "Singapore", "US": "United States",
}


# Where the day's coverage comes from: a small dot map and a legend by region (front page masthead).
# Coarse continent outlines (lon, lat) drawn into code: enough for a dot map, no map data to fetch.
_CONTINENTS = [
    [(-165, 66), (-140, 70), (-110, 72), (-90, 70), (-80, 62), (-65, 60), (-55, 50), (-66, 44), (-76, 37), (-81, 30), (-80, 25),
     (-90, 29), (-97, 26), (-98, 18), (-88, 15), (-80, 8), (-92, 14), (-105, 19), (-112, 28), (-117, 32), (-124, 40), (-125, 49),
     (-135, 58), (-150, 60), (-165, 60)],
    [(-55, 60), (-43, 60), (-20, 70), (-20, 80), (-60, 82), (-70, 77)],
    [(-80, 8), (-60, 11), (-50, 0), (-35, -6), (-40, -22), (-48, -28), (-58, -38), (-65, -55), (-72, -50), (-73, -40), (-71, -20), (-81, -5)],
    [(-10, 36), (-9, 43), (-2, 44), (-5, 48), (0, 50), (5, 53), (8, 57), (5, 62), (15, 69), (28, 71), (40, 67), (45, 60), (40, 45),
     (30, 45), (26, 40), (23, 36), (15, 38), (12, 44), (8, 44), (3, 43), (-5, 36)],
    [(-6, 50), (2, 51), (0, 55), (-3, 59), (-6, 57), (-5, 54)],
    [(-17, 21), (-10, 30), (-5, 36), (10, 37), (20, 32), (32, 31), (35, 28), (43, 12), (51, 12), (40, -2), (40, -15), (35, -25),
     (28, -33), (19, -35), (13, -20), (12, -5), (9, 4), (-8, 4), (-17, 14)],
    [(26, 40), (36, 36), (35, 32), (43, 14), (55, 22), (58, 24), (67, 25), (72, 20), (77, 8), (80, 15), (90, 22), (98, 16), (103, 1),
     (105, 10), (109, 22), (121, 30), (122, 40), (130, 43), (135, 48), (142, 53), (160, 60), (180, 66), (180, 72), (140, 73),
     (110, 77), (80, 73), (68, 70), (60, 68), (45, 60), (40, 45), (30, 45)],
    [(130, 31), (135, 34), (140, 36), (142, 40), (141, 45), (139, 42), (132, 34)],
    [(95, 5), (105, -6), (115, -8), (125, -9), (140, -8), (130, -2), (120, 1), (110, 2), (100, -1)],
    [(114, -22), (122, -17), (131, -12), (137, -12), (142, -11), (146, -19), (153, -26), (150, -37), (141, -38), (130, -32), (117, -35), (114, -28)],
    [(166, -46), (174, -41), (178, -38), (173, -35), (170, -44)],
]
# Each outlet country's rough center (lat, lon), and the regions of the legend.
COUNTRY_POS = {"US": (39, -98), "CA": (56, -106), "GB": (54, -2), "SE": (62, 16), "DE": (51, 10), "FR": (46, 2), "BE": (50.5, 4.5),
               "ES": (40, -4), "QA": (25, 51), "CN": (34, 104), "HK": (22, 114), "IN": (22, 79), "JP": (36, 138), "KR": (36, 128),
               "SG": (1, 104), "AU": (-25, 134)}
REGIONS = [("Americas", ["US", "CA"]), ("Europe", ["GB", "SE", "DE", "FR", "BE", "ES"]), ("Middle East", ["QA"]),
           ("Asia", ["CN", "HK", "IN", "JP", "KR", "SG"]), ("Oceania", ["AU"])]
MAP_W, MAP_H = 170, 70


def _inside(lon: float, lat: float, poly: list[tuple[float, float]]) -> bool:
    hit = False
    for (x1, y1), (x2, y2) in zip(poly, poly[-1:] + poly[:-1]):
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def coverage_map(stories: list[dict]) -> dict | None:
    """Outlets per country across the view's stories (one per outlet), as a dot map and a region legend.
    Land is a 5-degree dot grid; dots near a covered country light up, wider for more outlets. Each lit dot
    carries a delay (west to east) for the greeting."""
    outlets: dict[str, str] = {}
    for s in stories:
        for g in s.get("coverage") or []:
            for c in g["items"]:
                if c.get("country") in COUNTRY_POS:
                    outlets.setdefault(c["outlet"], c["country"])
    counts: dict[str, int] = {}
    for country in outlets.values():
        counts[country] = counts.get(country, 0) + 1
    if not counts:
        return None
    land, lit = [], []
    for lat in range(80, -57, -5):
        for lon in range(-170, 181, 5):
            if not any(_inside(lon, lat, p) for p in _CONTINENTS):
                continue
            x, y = (lon + 180) / 360 * (MAP_W - 2) + 1, (80 - lat) / 136 * (MAP_H - 2) + 1
            best = None
            for code, n in counts.items():
                clat, clon = COUNTRY_POS[code]
                reach = 11 if n > 10 else 7 if n > 3 else 5.5
                dist = ((lon - clon) ** 2 + ((lat - clat) * 1.3) ** 2) ** 0.5
                if dist <= reach and (best is None or dist < best[1]):
                    best = (n, dist)
            if best:
                lit.append((x, y, best[0], lon))
            else:
                land.append(f"M{x:.1f} {y:.1f}h0")
    dots = "".join(f'<circle class="lit{" few" if n <= 3 else ""}" cx="{x:.1f}" cy="{y:.1f}" r="1.25" style="--d:{int(250 + (lon + 180) * 1.6)}ms"/>'
                   for x, y, n, lon in sorted(lit, key=lambda d: d[3]))
    svg = Markup(f'<svg class="geo-map" viewBox="0 0 {MAP_W} {MAP_H}" width="{MAP_W}" height="{MAP_H}" aria-hidden="true" focusable="false">'
                 f'<path class="geo-land" d="{"".join(land)}"/>{dots}</svg>')
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    regions = [{"name": name, "countries": [{"code": c, "name": COUNTRY_NAMES.get(c, c), "n": counts.get(c, 0)} for c in codes],
                "n": sum(counts.get(c, 0) for c in codes)} for name, codes in REGIONS]
    return {"svg": svg, "outlets": len(outlets), "countries": [[c, n] for c, n in ranked], "regions": regions}


def _a(url: str, text: str) -> Markup:
    return Markup('<a href="{}" rel="noopener">{}</a>').format(url, text)


def builders_html(b: dict) -> Markup:
    """The Builders line with each part linked to its source: the top HN thread, the first repo, model or
    paper, the most liked post, each digest's issue, the first X post and Reddit thread, and the recap issue.
    Same words as edition.builders_line; parts without a stored link stay plain text."""
    parts: list[Markup] = []
    hn = b.get("hn") or []
    if hn:
        parts.append(_a(hn[0]["url"], f"HN {sum(h['points'] for h in hn):,} points, {sum(h['comments'] for h in hn):,} comments"))
    for key, word in (("repos", "repo"), ("models", "model"), ("papers", "paper")):
        items = b.get(key) or []
        if items:
            parts.append(_a(items[0]["url"], f"{len(items)} {word}{'s' if len(items) > 1 else ''}"))
    if b.get("social"):
        text = f"{b['social']} post{'s' if b['social'] > 1 else ''}"
        posts = b.get("posts") or []
        parts.append(_a(posts[0]["url"], text) if posts else Markup.escape(text))
    if b.get("digests"):
        links = b.get("digest_links") or {}
        parts.append(Markup("in ") + Markup(", ").join(_a(links[n], n) if n in links else Markup.escape(n) for n in b["digests"][:3]))
    x, reddit = b.get("x") or [], b.get("reddit") or []
    if x or reddit:
        bits = []
        if x:
            bits.append(_a(x[0]["url"], f"{len(x)} X post{'s' if len(x) > 1 else ''}"))
        if reddit:
            bits.append(_a(reddit[0]["url"], f"{len(reddit)} Reddit thread{'s' if len(reddit) > 1 else ''}"))
        talk = Markup(", ").join(bits)
        via, via_links = b.get("via") or [], b.get("via_links") or {}
        if via:
            talk += Markup(" via ") + Markup(" and ").join(_a(via_links[v], v) if v in via_links else Markup.escape(v) for v in via)
        parts.append(talk)
    return Markup(" · ").join(parts)


_PLATFORMS = re.compile(r"\b(Hacker News|GitHub|Hugging Face|Bluesky|Reddit)\b|(?<=\bon )X\b|\bX(?= (?:posts?|users)\b)")


def link_platforms(text: str, b: dict) -> Markup:
    """Link the first mention of each platform in a builders summary to that platform's top source."""
    targets: dict[str, str] = {}
    if b.get("hn"):
        targets["Hacker News"] = b["hn"][0]["url"]
    if b.get("repos"):
        targets["GitHub"] = b["repos"][0]["url"]
    models = b.get("models") or []
    if hf := [m for m in models if "Hugging Face" in (m.get("source") or "")] or models:
        targets["Hugging Face"] = hf[0]["url"]
    if bsky := [p for p in b.get("posts") or [] if (p.get("source") or "").startswith("Bluesky")]:
        targets["Bluesky"] = bsky[0]["url"]
    if b.get("reddit"):
        targets["Reddit"] = b["reddit"][0]["url"]
    if b.get("x"):
        targets["X"] = b["x"][0]["url"]
    used: set[str] = set()

    def link(m: re.Match) -> str:
        name = m.group(0)
        if name in targets and name not in used:
            used.add(name)
            return str(_a(targets[name], name))
        return name

    return Markup(_PLATFORMS.sub(link, str(escape(text or ""))))


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(HERE / "templates"),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["thousands"] = lambda n: f"{int(n):,}"
    env.filters["builders_html"] = builders_html
    env.filters["link_platforms"] = link_platforms
    env.filters["signed"] = lambda v: "–" if v is None else (f"{v:+.2f}".replace("-", "−"))
    env.filters["date_range"] = date_range
    env.filters["day_label"] = day_label
    env.filters["narrative_chart"] = narrative_chart
    env.filters["seal"] = seal
    env.globals.update(stance_names=STANCE_NAMES, kind_names=KIND_NAMES, country_names=COUNTRY_NAMES)
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


def day_label(d: str) -> str:
    """'2026-11-21' -> 'Sat 21 Nov'."""
    dt = datetime.fromisoformat(d)
    return f"{dt:%a} {dt.day} {dt:%b}"


def date_range(first: str, last: str) -> str:
    """'21–25 Nov', '28 Nov – 2 Dec', or with years when they differ."""
    a, b = datetime.fromisoformat(first), datetime.fromisoformat(last)
    if a.year != b.year:
        return f"{a.day} {a:%b %Y} – {b.day} {b:%b %Y}"
    if a.month != b.month:
        return f"{a.day} {a:%b} – {b.day} {b:%b}"
    return f"{a.day} {a:%b}" if a.day == b.day else f"{a.day}–{b.day} {b:%b}"


def _stance_class(v: float) -> str:
    return "d-2" if v <= -1.25 else "d-1" if v <= -0.25 else "d0" if v < 0.25 else "d1" if v < 1.25 else "d2"


def narrative_chart(timeline: list[dict], mini: bool = False) -> Markup:
    """A narrative day by day as inline SVG: the day's average stance as a line (broken on quiet days) with a dot
    per day colored by stance, over bars of outlets per day. Fixed -1..+1 scale, wider if a day falls outside.
    The mini version (front page, lists) has no labels; the full one names the days and counts, with hover values."""
    n = len(timeline)
    if not n:
        return Markup("")
    w, h = (160, 46) if mini else (560, 200)
    pad_l, pad_r = (6, 6) if mini else (8, 34)
    line_top, line_bot = (5, 25) if mini else (14, 100)
    bar_top, bar_bot = (31, 46) if mini else (132, 172)
    step = (w - pad_l - pad_r) / n
    x = lambda i: pad_l + step * (i + 0.5)  # noqa: E731
    lim = max([1.0] + [abs(t["mean"]) for t in timeline if t.get("mean") is not None])
    y = lambda v: line_top + (lim - v) / (2 * lim) * (line_bot - line_top)  # noqa: E731
    top = max([1] + [t["outlets"] for t in timeline])
    bw = max(2.0, min(step * 0.55, 26 if not mini else 9))
    cls = "nchart mini" if mini else "nchart"
    attrs = ' aria-hidden="true" focusable="false"' if mini else f' role="img" aria-label="Average stance and outlets per day, {n} days"'
    parts = [f'<svg class="{cls}" viewBox="0 0 {w} {h}"{attrs}>']
    parts.append(f'<line class="zero" x1="{pad_l}" x2="{w - pad_r}" y1="{y(0):.1f}" y2="{y(0):.1f}"/>')
    if not mini:
        for v in (lim, -lim):
            parts.append(f'<line class="grid" x1="{pad_l}" x2="{w - pad_r}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>')
        parts.append(f'<text class="axis" x="{w - pad_r + 6}" y="{y(lim) + 4:.1f}">+{lim:g}</text>')
        parts.append(f'<text class="axis" x="{w - pad_r + 6}" y="{y(0) + 4:.1f}">0</text>')
        parts.append(f'<text class="axis" x="{w - pad_r + 6}" y="{y(-lim) + 4:.1f}">−{lim:g}</text>')
    for i, t in enumerate(timeline):
        bh = (bar_bot - bar_top) * t["outlets"] / top
        if t["outlets"]:
            partial = " partial" if t.get("partial") else ""
            parts.append(f'<rect class="bar{partial}" x="{x(i) - bw / 2:.1f}" y="{bar_bot - bh:.1f}" width="{bw:.1f}" height="{bh:.1f}"/>')
            if not mini:
                parts.append(f'<text class="count" x="{x(i):.1f}" y="{bar_bot - bh - 4:.1f}">{t["outlets"]}</text>')
    segs, cur = [], []
    for i, t in enumerate(timeline):
        if t.get("mean") is None:
            if cur:
                segs.append(cur)
            cur = []
        else:
            cur.append(f"{x(i):.1f},{y(t['mean']):.1f}")
    if cur:
        segs.append(cur)
    parts += [f'<polyline class="line" points="{" ".join(sg)}"/>' for sg in segs if len(sg) > 1]
    for i, t in enumerate(timeline):
        if t.get("mean") is None:
            continue
        r = 3 if mini else 5
        dot = f'<circle class="dot {_stance_class(t["mean"])}" cx="{x(i):.1f}" cy="{y(t["mean"]):.1f}" r="{r}"/>'
        if mini:
            parts.append(dot)
        else:
            val = f"{t['mean']:+.2f}".replace("-", "−")
            parts.append(f'<g class="pt"><title>{day_label(t["date"])}: average {val}, {t["outlets"]} outlet{"s" if t["outlets"] != 1 else ""}</title>{dot}</g>')
    if not mini:
        every = max(1, -(-n // 10))
        for i, t in enumerate(timeline):
            if i % every == 0 or i == n - 1:
                d = datetime.fromisoformat(t["date"])
                parts.append(f'<text class="day" x="{x(i):.1f}" y="{h - 8}">{d.day} {d:%b}</text>')
    parts.append("</svg>")
    return Markup("".join(parts))


# The narrative seal: a guilloché engraving (the fine line work on banknotes and passports) generated from the
# narrative. Two petals per day; an outer ring with an arc per day (thickness: outlets, color: that day's stance);
# the day count in the middle. It rests still. On a narrative's page app.js lets its strings spell the day count,
# "day" and "narrative" before they wind back into the seal; the data-* attributes carry what it needs. The lattice
# curve is defined once per page (seal_defs) and reused; each lattice is its own layer so it can turn cheaply.
SEAL_R0, SEAL_AMP, SEAL_PTS = 29.0, 7.5, 240


def seal_petals(days: int) -> int:
    return 2 * max(2, min(days, 14))


def _lattice_path(k: int) -> str:
    pts = []
    for i in range(SEAL_PTS):
        t = 2 * math.pi * i / SEAL_PTS
        r = SEAL_R0 + SEAL_AMP * math.sin(k * t)
        pts.append(f"{50 + r * math.cos(t):.2f} {50 + r * math.sin(t):.2f}")
    return "M" + "L".join(pts) + "Z"


def seal_defs(narratives: list[dict]) -> Markup:
    """The lattice curves the page's seals use, once each; empty when the page has no seal."""
    petals = sorted({seal_petals(len(n.get("timeline") or [])) for n in narratives if n and n.get("timeline")})
    if not petals:
        return Markup("")
    paths = "".join(f'<path id="seal-k{k}" d="{_lattice_path(k)}"/>' for k in petals)
    return Markup(f'<svg class="seal-defs" aria-hidden="true" focusable="false"><defs>{paths}</defs></svg>')


def _arc(r: float, a0: float, a1: float) -> str:
    p = lambda a: (50 + r * math.cos(math.radians(a)), 50 + r * math.sin(math.radians(a)))  # noqa: E731
    (x0, y0), (x1, y1) = p(a0), p(a1)
    return f"M{x0:.2f} {y0:.2f}A{r} {r} 0 {1 if a1 - a0 > 180 else 0} 1 {x1:.2f} {y1:.2f}"


def seal(n: dict, big: bool = False, label: str | None = None) -> Markup:
    """A narrative's seal from {id, timeline: [{outlets, mean, quiet}], first, last, outlets}. Small on cards and rows,
    big on the narrative's page. `label` makes it an image with that name; otherwise it is
    decoration inside a link that names it."""
    timeline = n.get("timeline") or []
    days = len(timeline)
    if not days:
        return Markup("")
    k = seal_petals(days)
    top = max([1] + [t.get("outlets") or 0 for t in timeline])
    span = 360 / days
    gap = min(2.2, span * 0.18)
    ring = []
    for i, t in enumerate(timeline):
        a0, a1 = -90 + i * span + gap, -90 + (i + 1) * span - gap
        if t.get("quiet") or not t.get("outlets"):
            ring.append(f'<path class="day quiet" d="{_arc(45.5, a0, a1)}" pathLength="1" style="--i:{i}"/>')
            continue
        cls = _stance_class(t["mean"]).replace("d", "s", 1) if t.get("mean") is not None else "sna"
        w = (1.1 + 2.6 * t["outlets"] / top) if big else (1.8 + 3.4 * t["outlets"] / top)
        ring.append(f'<path class="day {cls}" d="{_arc(45.5, a0, a1)}" stroke-width="{w:.2f}" pathLength="1" style="--i:{i}"/>')
    m = 6 if big else 3
    lat = lambda sign: "".join(f'<use href="#seal-k{k}" transform="rotate({sign * j * 180 / (m * k):.3f} 50 50)"/>' for j in range(m))  # noqa: E731
    vb = 'viewBox="0 0 100 100" aria-hidden="true" focusable="false"'
    inner = 15 if big else 17
    num_size = (15 if days < 100 else 11) if big else (30 if days < 10 else 23 if days < 100 else 16)
    num_y = 55.5 if big else 50 + num_size * 0.36
    cap = (f'<circle class="cap" cx="50" cy="50" r="{inner}"/><circle class="hair" cx="50" cy="50" r="{inner}"/>'
           f'<text class="seal-n" x="50" y="{num_y:.1f}" font-size="{num_size}">{days}</text>'
           + ('<text class="seal-l" x="50" y="63" font-size="3.6">DAYS</text>' if big else ""))
    attrs = f' role="img" aria-label="{escape(label)}"' if label else ' aria-hidden="true"'
    if big:  # what the seal's strings spell on the narrative's page (app.js)
        attrs += f' data-k="{k}" data-m="{m}" data-days="{days}"'
    return Markup(
        f'<span class="seal{" big" if big else ""}"{attrs}>'
        f'<svg class="seal-base" {vb}>{"".join(ring)}<circle class="hair" cx="50" cy="50" r="42.6"/></svg>'
        f'<svg class="seal-lat a" {vb}>{lat(1)}</svg><svg class="seal-lat b" {vb}>{lat(-1)}</svg>'
        f'<svg class="seal-cap" {vb}>{cap}</svg></span>')


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
        geo=coverage_map(edition["stories"]),
        seal_defs=seal_defs([s.get("narrative") for s in edition["stories"]] + list((edition.get("narratives") or {}).get("items") or [])),
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


# Hosting config for Vercel (news.b3njamin.ai). The pages link with relative paths
# ("../static/style.css"), so a folder URL must end in a slash: /archive has to become /archive/.
# GitHub Pages redirects like that by itself; Vercel only with trailingSlash.
VERCEL_CONFIG = {"trailingSlash": True}


def render_404(out_dir: Path) -> Path:
    """404.html at the site root, which the host serves for any missing address; its links are absolute."""
    path = out_dir / "404.html"
    path.write_text(_env().get_template("404.html.j2").render(root="/"), encoding="utf-8")
    return path


def write_host_config(out_dir: Path) -> Path:
    path = out_dir / "vercel.json"
    path.write_text(json.dumps(VERCEL_CONFIG, indent=1) + "\n", encoding="utf-8")
    return path


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


def render_narratives(narratives: list[dict], out_dir: Path, tz: str = "Europe/Stockholm", min_days: int = 4) -> Path:
    """/narratives/ (ongoing, then ended) and one page per narrative at /narratives/<story id>/."""
    env = _env()
    page_dir = out_dir / "narratives"
    page_dir.mkdir(parents=True, exist_ok=True)
    for n in narratives:
        d = page_dir / n["id"]
        d.mkdir(parents=True, exist_ok=True)
        for t in n["timeline"]:
            t["segments"] = stance_segments(t["stance"]) if t.get("stance") else []
            t["stance_label"] = stance_label(t["stance"], f"Stance on {day_label(t['date'])}") if t.get("stance") else ""
        (d / "index.html").write_text(env.get_template("narrative.html.j2").render(
            n=n, root="../../", seal_defs=seal_defs([n]), segments=stance_segments(n["stance"]), stance_text=stance_label(n["stance"], "Stance of every article"),
            min_days=min_days), encoding="utf-8")
    ongoing = [n for n in narratives if n["ongoing"]]
    ended = [n for n in narratives if not n["ongoing"]]
    html = env.get_template("narratives.html.j2").render(ongoing=ongoing, ended=ended, root="../", min_days=min_days, seal_defs=seal_defs(narratives))
    (page_dir / "index.html").write_text(html, encoding="utf-8")
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


# What each track covers: the same lists the labeling prompt (news_label_v3) and the About page use.
TRACK_NOTES = {
    "all": "Every labeled article, whatever its angle.",
    "technical": "Models, research, capabilities, benchmarks, tools and safety research.",
    "political": "Regulation, policy, geopolitics, chips and export controls, elections and courts.",
    "economic": "Stock markets, earnings, adoption, data centers, jobs, funding and valuations.",
}


def render_sentiment(history: dict, out_dir: Path, tz: str = "Europe/Stockholm") -> Path:
    """/sentiment/: the daily AI sentiment index, overall and per track, with a table view."""
    from quiet_ai.pipeline.sentiment import describe

    page_dir = out_dir / "sentiment"
    page_dir.mkdir(parents=True, exist_ok=True)
    series = [("all", "All coverage"), ("technical", "Technical"), ("political", "Political"), ("economic", "Economic")]
    charts = [{"key": k, "label": lab, "note": TRACK_NOTES[k], "svg": sparkline(history.get(k, []), lab), "latest": (history.get(k) or [None])[-1]}
              for k, lab in series]
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
