"""Polite HTTP: one identified client, per-host spacing, robots.txt, conditional GET,
retries with backoff, and a replay/record mode for fixtures."""

from __future__ import annotations

import contextlib
import email.utils
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
from protego import Protego

from quiet_ai.config import HttpSettings
from quiet_ai.fixtures import FixtureStore

Mode = Literal["live", "record", "replay"]
RETRY_STATUS = {429, 500, 502, 503, 504}


class FetchError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class RobotsBlocked(FetchError):
    pass


class FixtureMissing(FetchError):
    pass


@dataclass
class Response:
    url: str
    status: int
    content: bytes
    content_type: str = ""
    not_modified: bool = False

    def json(self):
        import json

        return json.loads(self.content)


@dataclass
class _Robots:
    parser: Protego | None  # None = no restrictions
    blocked_all: bool = False  # robots.txt unreachable (5xx/network): RFC 9309 says assume disallow
    reason: str = ""
    content_signals: list[str] = field(default_factory=list)


class Http:
    def __init__(
        self,
        settings: HttpSettings,
        mode: Mode = "live",
        fixtures_dir: Path | None = None,
        fetch_state: dict[str, dict] | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.s = settings
        self.mode = mode
        self.fixtures = FixtureStore(fixtures_dir) if fixtures_dir else None
        if mode in ("record", "replay") and not self.fixtures:
            raise ValueError(f"{mode} mode needs fixtures_dir")
        self.client = httpx.Client(
            headers={"User-Agent": settings.user_agent},
            timeout=settings.timeout_s,
            follow_redirects=True,
            transport=transport,
        )
        self.sleep = sleep
        self.fetch_state = dict(fetch_state or {})  # url -> {etag, last_modified}
        self.state_updates: dict[str, dict] = {}
        self._host_interval = dict(settings.host_min_interval_s)
        self._host_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._host_last: dict[str, float] = {}
        self._robots: dict[str, _Robots] = {}
        self._robots_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._meta_lock = threading.Lock()

    def close(self) -> None:
        self.client.close()

    def set_host_interval(self, host: str, seconds: float) -> None:
        self._host_interval[host] = seconds

    # -- spacing -------------------------------------------------------------------------

    @contextlib.contextmanager
    def _host_slot(self, host: str) -> Iterator[None]:
        """Serialize requests per host and keep min_interval between them."""
        with self._meta_lock:
            lock = self._host_locks[host]
        with lock:
            wait = self._host_last.get(host, 0) + self._host_interval.get(host, self.s.min_interval_s) - time.monotonic()
            if wait > 0:
                self.sleep(wait)
            try:
                yield
            finally:
                self._host_last[host] = time.monotonic()

    # -- robots.txt ----------------------------------------------------------------------

    def robots(self, url: str) -> _Robots:
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        with self._meta_lock:
            lock = self._robots_locks[base]
        with lock:
            if base not in self._robots:
                self._robots[base] = self._load_robots(base, parts.netloc)
            return self._robots[base]

    def _load_robots(self, base: str, host: str) -> _Robots:
        try:
            with self._host_slot(host):
                r = self.client.get(base + "/robots.txt")
        except httpx.HTTPError as e:
            return _Robots(parser=None, blocked_all=True, reason=f"robots.txt unreachable ({type(e).__name__})")
        if r.status_code >= 500:
            return _Robots(parser=None, blocked_all=True, reason=f"robots.txt returned HTTP {r.status_code}")
        if r.status_code != 200:
            return _Robots(parser=None)  # 4xx: no restrictions (RFC 9309)
        text = r.text
        signals = [ln.split(":", 1)[1].strip() for ln in text.splitlines() if ln.lower().startswith("content-signal:")]
        return _Robots(parser=Protego.parse(text), content_signals=signals)

    def allowed(self, url: str) -> bool:
        rb = self.robots(url)
        if rb.blocked_all:
            return False
        return rb.parser is None or rb.parser.can_fetch(url, self.s.robots_token)

    # -- GET -----------------------------------------------------------------------------

    def get(
        self,
        url: str,
        *,
        key: str,
        params: dict | None = None,
        headers: dict | None = None,
        conditional: bool = False,
    ) -> Response:
        if self.mode == "replay":
            return self._replay(key)
        full_url = str(httpx.URL(url, params=params)) if params else url
        if self.s.respect_robots and not self.allowed(full_url):
            raise RobotsBlocked(self.robots(full_url).reason or "disallowed by robots.txt")
        hdrs = dict(headers or {})
        use_conditional = conditional and self.mode == "live"
        if use_conditional and (st := self.fetch_state.get(full_url)):
            if st.get("etag"):
                hdrs["If-None-Match"] = st["etag"]
            if st.get("last_modified"):
                hdrs["If-Modified-Since"] = st["last_modified"]
        host = urlsplit(full_url).netloc
        last_error: FetchError | None = None
        for attempt in range(self.s.max_retries + 1):
            try:
                with self._host_slot(host):
                    r = self.client.get(full_url, headers=hdrs)
            except httpx.HTTPError as e:
                last_error = FetchError(f"{type(e).__name__}: {e}"[:200])
                if attempt < self.s.max_retries:
                    self.sleep(self.s.backoff_base_s * 2**attempt)
                    continue
                raise last_error from e
            if r.status_code == 304:
                return Response(full_url, 304, b"", r.headers.get("content-type", ""), not_modified=True)
            if r.status_code in RETRY_STATUS and attempt < self.s.max_retries:
                self.sleep(self._retry_wait(r, attempt))
                continue
            if r.status_code >= 400:
                raise FetchError(f"HTTP {r.status_code}", status=r.status_code)
            if use_conditional:
                self.state_updates[full_url] = {
                    "etag": r.headers.get("etag"),
                    "last_modified": r.headers.get("last-modified"),
                    "key": key,
                }
            resp = Response(str(r.url), r.status_code, r.content, r.headers.get("content-type", ""))
            if self.mode == "record":
                self.fixtures.put(key, full_url, resp.status, resp.content_type, resp.content)
            return resp
        raise last_error or FetchError("retries exhausted")

    def _retry_wait(self, r: httpx.Response, attempt: int) -> float:
        wait = self.s.backoff_base_s * 2**attempt
        ra = r.headers.get("retry-after")
        if ra:
            if ra.isdigit():
                wait = float(ra)
            else:
                with contextlib.suppress(TypeError, ValueError):
                    wait = max(0.0, email.utils.parsedate_to_datetime(ra).timestamp() - time.time())
        return min(wait, self.s.max_retry_wait_s)

    def _replay(self, key: str) -> Response:
        found = self.fixtures.get(key)
        if not found:
            raise FixtureMissing(f"no fixture for {key}")
        meta, body = found
        return Response(meta["url"], meta["status"], body, meta.get("content_type", ""))
