"""Small text and URL helpers shared by fetchers."""

from __future__ import annotations

import calendar
import hashlib
import html
import re
import time
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

# Query parameters that only track the click; everything else is kept because some
# sites use the query string to identify the article.
_TRACKING = re.compile(
    r"^(utm_[a-z_]+|fbclid|gclid|dclid|msclkid|mc_cid|mc_eid|_hsenc|_hsmi|mkt_tok|igshid|"
    r"ref|ref_src|ref_url|cmpid|cmp|smid|smtyp|partner|ocid|ito|guccounter|guce_[a-z_]+|"
    r"taid|ns_mchannel|ns_source|ns_campaign|ns_linkname|ns_fee|sr_share|soc_src|soc_trk|"
    r"rss|feed|xtor|at_medium|at_campaign|share|s_cid|src|sref|via|traffic_source|"
    r"__twitter_impression|campaign_id|link_id|source)$",
    re.IGNORECASE,
)


def clean_text(value: str | None, max_chars: int | None = None) -> str | None:
    """HTML to plain text, whitespace collapsed, optionally truncated at a word boundary."""
    if not value:
        return None
    text = html.unescape(_TAG.sub(" ", html.unescape(value)))
    text = _WS.sub(" ", text).strip()
    if not text:
        return None
    if max_chars and len(text) > max_chars:
        cut = text[: max_chars - 1]
        space = cut.rfind(" ")
        if space > max_chars * 0.6:
            cut = cut[:space]
        text = cut.rstrip(" ,;:.-") + "…"
    return text


def canonical_url(url: str) -> str:
    """Lowercase scheme and host, drop fragment, tracking params and trailing slash."""
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    if scheme == "http":
        scheme = "https"
    host = parts.netloc.lower()
    if host.endswith(":443") or host.endswith(":80"):
        host = host.rsplit(":", 1)[0]
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING.match(k)])
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit((scheme, host, path, query, ""))


def url_id(url: str) -> str:
    return "url:" + hashlib.sha1(canonical_url(url).encode("utf-8")).hexdigest()[:20]


def from_struct(st: time.struct_time | None) -> datetime | None:
    """feedparser's UTC struct_time -> aware datetime."""
    if not st:
        return None
    try:
        return datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc)
    except (OverflowError, ValueError):
        return None


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def first_line(text: str | None, max_chars: int = 140) -> str | None:
    if not text:
        return None
    line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return clean_text(line, max_chars)
