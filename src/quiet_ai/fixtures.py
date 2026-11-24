"""Recorded HTTP responses for --dry-run and tests.

Responses are stored by a stable logical key (e.g. "rss:nyt:0", "github:new:llm"), not by
URL, because many URLs contain dates or timestamps. Before saving, bodies are trimmed to a
few items and long text is cut, so fixtures hold no more than the site itself would show
(headline + short summary) and stay small.
"""

from __future__ import annotations

import html
import json
import re
import threading
from pathlib import Path
from typing import Any

from quiet_ai.text import clean_text

MAX_ITEMS = 5
MAX_TEXT = 500

_ITEM_START = re.compile(rb"<(?:item|entry)(?:\s[^>]*)?>")
_ITEM_END = re.compile(rb"</(?:item|entry)>")
_CONTENT_ENCODED = re.compile(rb"<content:encoded>.*?</content:encoded>", re.S)
_ATOM_CONTENT = re.compile(rb"<content(?:\s[^>]*)?>.*?</content>", re.S)
_DESC = re.compile(rb"<(description|summary)(\s[^>]*)?>(.*?)</\1>", re.S)
_CDATA = re.compile(rb"^\s*<!\[CDATA\[(.*)\]\]>\s*$", re.S)
_LONG_CATEGORY = re.compile(rb"<category(?:\s[^>]*)?>(?:(?!</category>).){300,}?</category>", re.S)

# JSON keys no fetcher reads that make fixtures large (thread context, avatars, URL templates).
_DROP_KEYS = {
    "reply", "viewer", "labels", "avatar", "banner", "commentators", "mentions", "attachments", "mediaUrls",
    "endpoints", "architecture", "supported_parameters", "default_parameters", "benchmarks",
    "per_request_limits", "top_provider", "thumbnail", "authorData", "_highlightResult", "submittedOnDailyBy",
}


def _short_desc(m: re.Match[bytes]) -> bytes:
    tag, attrs, inner = m.group(1), m.group(2) or b"", m.group(3)
    cd = _CDATA.match(inner)
    raw = (cd.group(1) if cd else inner).decode("utf-8", "replace")
    if len(clean_text(raw) or "") <= MAX_TEXT:
        return m.group(0)  # short text: keep the markup (aggregators put the lead link in it)
    text = clean_text(raw, MAX_TEXT) or ""
    return b"<" + tag + attrs + b">" + html.escape(text, quote=False).encode() + b"</" + tag + b">"


_SITEMAP_URL = re.compile(rb"<url>.*?</url>", re.S)
_LASTMOD = re.compile(rb"<lastmod>\s*([^<\s]+)")
_HEAD_META = re.compile(rb"<meta\s+[^>]*(?:og:title|og:description|article:published_time|name=[\"']description)[^>]*>", re.I)
_TITLE = re.compile(rb"<title>.*?</title>", re.S | re.I)


def sanitize_sitemap(body: bytes, keep: int = 40) -> bytes:
    """Keep the most recently modified entries (the only ones the fetcher reads)."""
    urls = _SITEMAP_URL.findall(body)
    newest = sorted(urls, key=lambda u: (m.group(1) if (m := _LASTMOD.search(u)) else b""), reverse=True)[:keep]
    head = body[: body.find(b"<url>")] if b"<url>" in body else body
    return head + b"\n".join(newest) + b"\n</urlset>\n"


def sanitize_html(body: bytes) -> bytes:
    """Keep only the title and the metadata tags fetchers read; drop the article."""
    parts = _TITLE.findall(body)[:1] + _HEAD_META.findall(body)
    return b"<html><head>\n" + b"\n".join(parts) + b"\n</head></html>\n"


def sanitize_feed(body: bytes, max_items: int = MAX_ITEMS) -> bytes:
    starts = list(_ITEM_START.finditer(body))
    ends = list(_ITEM_END.finditer(body))
    if len(starts) > max_items and len(ends) >= max_items:
        body = body[: ends[max_items - 1].end()] + body[ends[-1].end() :]
    body = _CONTENT_ENCODED.sub(b"", body)
    body = _ATOM_CONTENT.sub(b"", body)
    body = _LONG_CATEGORY.sub(b"", body)
    return _DESC.sub(_short_desc, body)


def _trim_json(obj: Any, max_items: int, depth: int = 0) -> Any:
    if isinstance(obj, list):
        limit = max_items if depth <= 1 else max_items * 4
        return [_trim_json(x, max_items, depth + 1) for x in obj[:limit]]
    if isinstance(obj, dict):
        return {
            k: _trim_json(v, max_items, depth + 1)
            for k, v in obj.items()
            if k not in _DROP_KEYS and not (k.endswith("_url") and k != "html_url")
        }
    if isinstance(obj, str) and len(obj) > MAX_TEXT + 100:
        return obj[:MAX_TEXT] + "…"
    return obj


def sanitize(body: bytes, content_type: str, max_items: int = MAX_ITEMS) -> bytes:
    ct = content_type.lower()
    stripped = body.lstrip()
    if "json" in ct or stripped[:1] in (b"{", b"["):
        try:
            obj = json.loads(body)
        except ValueError:
            return body
        return json.dumps(_trim_json(obj, max_items), ensure_ascii=False, indent=1).encode("utf-8")
    if b"<urlset" in body[:1000]:
        return sanitize_sitemap(body)
    if "xml" in ct or "rss" in ct or "atom" in ct or stripped[:5] == b"<?xml" or b"<rss" in body[:500]:
        return sanitize_feed(body, max_items)
    if "html" in ct:
        return sanitize_html(body)
    return body


class FixtureStore:
    """index.json maps key -> {file, url, status, content_type}."""

    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self._lock = threading.Lock()
        index = self.dir / "index.json"
        self.index: dict[str, dict] = json.loads(index.read_text()) if index.exists() else {}

    def get(self, key: str) -> tuple[dict, bytes] | None:
        meta = self.index.get(key)
        if not meta:
            return None
        return meta, (self.dir / meta["file"]).read_bytes()

    def put(self, key: str, url: str, status: int, content_type: str, body: bytes) -> None:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", key).strip("_")
        ext = ".json" if "json" in content_type else ".xml" if any(t in content_type for t in ("xml", "rss", "atom")) else ".txt"
        name = f"{safe}{ext}"
        with self._lock:
            self.dir.mkdir(parents=True, exist_ok=True)
            (self.dir / name).write_bytes(sanitize(body, content_type))
            self.index[key] = {"file": name, "url": url, "status": status, "content_type": content_type}
            (self.dir / "index.json").write_text(json.dumps(self.index, indent=1, sort_keys=True) + "\n")
