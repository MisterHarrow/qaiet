"""X and Reddit, second-hand: the posts and threads a recap newsletter (AINews) links to.

We never fetch x.com or reddit.com (both robots.txt files block us, and X is out by design).
AINews publishes a daily recap of AI X and Reddit; each bullet links the posts or the thread it
summarizes next to the article, repository or model they are about. We keep only those links:
the post URL and account, the thread URL, subreddit, title and AINews's activity count, plus
the other URLs in the same bullet ("targets"). A story or Rising project whose own URL matches a
target shows the posts and threads, credited to AINews.

Most X bullets link only posts, no article, so `x_bullets` also turns each X bullet into a small
"recap" item (its bold lead as the title, its text as the short summary, the posts and other URLs in
`extra`). Recap items join an existing story by link or by similarity, like a Bluesky post, but never
start one, and are never labeled by a model. Reddit bullets stay link-only.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import urlsplit

from quiet_ai.pipeline.cluster import norm_key
from quiet_ai.store.db import Store, iso
from quiet_ai.text import canonical_url, clean_text

_X_POST = re.compile(r"^/([A-Za-z0-9_]{1,15})/status/(\d+)")
_REDDIT_THREAD = re.compile(r"^/r/([A-Za-z0-9_]{2,21})/comments/([a-z0-9]+)", re.I)
_ACTIVITY = re.compile(r"\(Activity:\s*([\d,]+)\)")
_NOT_TARGETS = ("latent.space", "smol.ai", "substack.com", "substackcdn.com", "buttondown.com", "x.com", "twitter.com",
                "reddit.com", "redd.it", "t.co", "youtube.com", "youtu.be", "linkedin.com", "bsky.app", "discord.com", "discord.gg")
_IMAGE = re.compile(r"\.(png|jpe?g|gif|webp|svg|mp4)$", re.I)
MAX_X, MAX_REDDIT = 400, 80  # per issue, a safety cap


class _Bullets(HTMLParser):
    """Top-level list items (with their nested items) as blocks of (href, anchor text) and plain text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.blocks: list[dict] = []
        self.cur: dict | None = None
        self.anchor: list | None = None
        self.bold: list | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self.depth += 1
            if self.depth == 1:
                self.cur = {"links": [], "text": [], "lead": None}
        elif tag == "a" and self.cur is not None:
            self.anchor = [dict(attrs).get("href"), []]
        elif tag in ("b", "strong") and self.cur is not None and self.cur["lead"] is None and self.bold is None:
            self.bold = []

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor is not None and self.cur is not None:
            href, parts = self.anchor
            if href:
                self.cur["links"].append((href, "".join(parts)))
            self.anchor = None
        elif tag in ("b", "strong") and self.bold is not None and self.cur is not None:
            self.cur["lead"] = "".join(self.bold)
            self.bold = None
        elif tag == "li" and self.depth:
            self.depth -= 1
            if self.depth == 0 and self.cur is not None:
                self.cur["text"] = "".join(self.cur["text"])
                self.blocks.append(self.cur)
                self.cur = None

    def handle_data(self, data):
        if self.cur is not None:
            self.cur["text"].append(data)
            if self.anchor is not None:
                self.anchor[1].append(data)
            if self.bold is not None:
                self.bold.append(data)


def _host(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.").removeprefix("old.").removeprefix("mobile.")


def _bullets(html: str) -> list[dict]:
    """Each top-level bullet: its lead, text, X post URLs, Reddit threads, and other URLs (as link keys and as URLs)."""
    parser = _Bullets()
    parser.feed(html or "")
    out = []
    for b in parser.blocks:
        x, reddit, targets, urls = [], [], [], []
        activities = [int(a.replace(",", "")) for a in _ACTIVITY.findall(b["text"])]
        for href, text in b["links"]:
            if not href.startswith("http"):
                continue
            host, path = _host(href), urlsplit(href).path
            if host in ("x.com", "twitter.com") and (m := _X_POST.match(path)):
                url = f"https://x.com/{m.group(1)}/status/{m.group(2)}"
                if url not in x:
                    x.append(url)
            elif host.endswith("reddit.com") and (m := _REDDIT_THREAD.match(path)):
                url = f"https://www.reddit.com/r/{m.group(1)}/comments/{m.group(2).lower()}"
                if all(r["url"] != url for r in reddit):
                    reddit.append({"url": url, "sub": m.group(1), "title": clean_text(text, 200) or None,
                                   "activity": activities[len(reddit)] if len(reddit) < len(activities) else None})
            elif not any(host == h or host.endswith("." + h) for h in _NOT_TARGETS) and not _IMAGE.search(path):
                key = norm_key(href)
                if key and key not in targets:
                    targets.append(key)
                    urls.append(canonical_url(href))
        out.append({"lead": b["lead"], "text": b["text"], "x": x, "reddit": reddit, "targets": targets, "urls": urls})
    return out


def x_bullets(html: str) -> list[dict]:
    """Bullets that link X posts and no Reddit thread: {"lead", "text", "x": [post URLs], "urls": [other URLs]}."""
    return [{k: b[k] for k in ("lead", "text", "x", "urls")} for b in _bullets(html) if b["x"] and not b["reddit"]][:MAX_X]


def extract(html: str) -> list[dict]:
    """Bullets that link X posts or Reddit threads next to at least one other URL.

    Each block: {"targets": [link keys], "x": [post URLs], "reddit": [{"url", "sub", "title", "activity"}]}."""
    out, n_x, n_reddit = [], 0, 0
    for b in _bullets(html):
        x, reddit, targets = b["x"], b["reddit"], b["targets"]
        if targets and (x or reddit):
            x, reddit = x[: max(0, MAX_X - n_x)], reddit[: max(0, MAX_REDDIT - n_reddit)]
            n_x, n_reddit = n_x + len(x), n_reddit + len(reddit)
            out.append({"targets": targets, "x": x, "reddit": reddit})
    return out


def account(post_url: str) -> str:
    m = _X_POST.match(urlsplit(post_url).path)
    return m.group(1) if m else ""


def short_name(name: str) -> str:
    """'AINews (Latent Space)' -> 'AINews'."""
    return re.sub(r"\s*\(.*\)$", "", name)


class Index:
    """Link key -> the X posts and Reddit threads that recap bullets put next to it."""

    def __init__(self, blocks: list[tuple]):
        """blocks: (source, block) or (source, block, issue URL)."""
        self.by_key: dict[str, list[tuple[str, dict, str | None]]] = {}
        for source, block, *issue in blocks:
            for key in block["targets"]:
                self.by_key.setdefault(key, []).append((source, block, issue[0] if issue else None))

    def lookup(self, keys: set[str], names: dict[str, str] | None = None) -> dict:
        """{"x": [{"url", "account"}], "reddit": [{...}], "via": [newsletter names], "via_links": {name: issue URL}}
        for any of these link keys."""
        x: dict[str, dict] = {}
        reddit: dict[str, dict] = {}
        via: set[str] = set()
        via_links: dict[str, str] = {}
        for key in keys:
            for source, block, issue in self.by_key.get(key, []):
                name = short_name((names or {}).get(source, source))
                via.add(name)
                if issue:
                    via_links.setdefault(name, issue)
                for url in block["x"]:
                    x.setdefault(url, {"url": url, "account": account(url)})
                for r in block["reddit"]:
                    prev = reddit.get(r["url"])
                    if prev is None or (r.get("activity") or 0) > (prev.get("activity") or 0):
                        reddit[r["url"]] = r
        threads = sorted(reddit.values(), key=lambda r: -(r.get("activity") or 0))
        return {"x": list(x.values()), "reddit": threads, "via": sorted(via), "via_links": via_links}


EMPTY = Index([])


def load(store: Store, sources: list[str], now: datetime, hours: float) -> Index:
    """Recap blocks from these newsletters published in the window (plus a day: a recap covers the day before)."""
    if not sources:
        return EMPTY
    since = iso(now - timedelta(hours=hours + 24))
    rows = store.conn.execute(
        f"SELECT source, url, extra FROM items WHERE source IN ({','.join('?' * len(sources))}) "
        "AND COALESCE(published_at, first_seen_at) >= ?", (*sources, since)).fetchall()
    blocks = [(r["source"], b, r["url"]) for r in rows for b in json.loads(r["extra"] or "{}").get("mentions", [])]
    return Index(blocks)


def line(found: dict) -> str | None:
    """'12 X posts, 2 Reddit threads via AINews' (None when there are none)."""
    parts = []
    if found["x"]:
        parts.append(f"{len(found['x'])} X post{'s' if len(found['x']) > 1 else ''}")
    if found["reddit"]:
        parts.append(f"{len(found['reddit'])} Reddit thread{'s' if len(found['reddit']) > 1 else ''}")
    if not parts:
        return None
    return ", ".join(parts) + (" via " + " and ".join(found["via"]) if found["via"] else "")
