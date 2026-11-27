from __future__ import annotations

import httpx
import pytest

from quiet_ai.fixtures import sanitize
from quiet_ai.http import FetchError, FixtureMissing, Http, RobotsBlocked


def make(settings, handler, **kw) -> tuple[Http, list[float]]:
    sleeps: list[float] = []
    http = Http(settings.http, transport=httpx.MockTransport(handler), sleep=sleeps.append, **kw)
    return http, sleeps


def test_sends_user_agent_and_conditional_headers(settings):
    seen = []

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        seen.append(req)
        if req.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(200, content=b"<rss/>", headers={"etag": '"v1"'})

    http, _ = make(settings, handler)
    r1 = http.get("https://ex.com/feed", key="k", conditional=True)
    assert r1.status == 200 and seen[0].headers["user-agent"] == settings.http.user_agent
    http.fetch_state = {u: s for u, s in http.state_updates.items()}
    r2 = http.get("https://ex.com/feed", key="k", conditional=True)
    assert r2.not_modified


def test_retries_429_honouring_retry_after(settings):
    calls = {"n": 0}

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        calls["n"] += 1
        return httpx.Response(429, headers={"retry-after": "7"}) if calls["n"] == 1 else httpx.Response(200, json={"ok": 1})

    http, sleeps = make(settings, handler)
    assert http.get("https://api.ex.com/x", key="k").json() == {"ok": 1}
    assert 7 in sleeps and calls["n"] == 2


def test_gives_up_after_max_retries(settings):
    http, _ = make(settings, lambda req: httpx.Response(404) if req.url.path == "/robots.txt" else httpx.Response(503))
    with pytest.raises(FetchError) as e:
        http.get("https://ex.com/x", key="k")
    assert e.value.status == 503


def test_robots_disallow_blocks(settings):
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /feed/\nContent-Signal: ai-input=no\n")
        return httpx.Response(200, content=b"ok")

    http, _ = make(settings, handler)
    with pytest.raises(RobotsBlocked):
        http.get("https://ex.com/feed/", key="k")
    assert http.get("https://ex.com/other", key="k2").status == 200
    assert http.robots("https://ex.com/").content_signals == ["ai-input=no"]


def test_robots_unreachable_means_disallow(settings):
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(503)
        return httpx.Response(200, content=b"ok")

    http, _ = make(settings, handler)
    with pytest.raises(RobotsBlocked, match="503"):
        http.get("https://ex.com/feed", key="k")


def test_record_then_replay(settings, tmp_path):
    items = b"".join(b"<item><title>t%d</title><link>https://e.com/%d</link></item>" % (i, i) for i in range(12))
    body = b'<?xml version="1.0"?><rss><channel><title>c</title>' + items + b"</channel></rss>"

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=body, headers={"content-type": "application/rss+xml"})

    rec, _ = make(settings, handler, mode="record", fixtures_dir=tmp_path)
    rec.get("https://e.com/feed", key="rss:e:0")
    rep = Http(settings.http, mode="replay", fixtures_dir=tmp_path)
    got = rep.get("https://anything", key="rss:e:0")
    assert got.content.count(b"<item>") == 5 and b"</channel></rss>" in got.content
    with pytest.raises(FixtureMissing):
        rep.get("https://anything", key="nope")


def test_sanitize_cuts_full_text_and_long_json_strings():
    long = "word " * 400
    feed = (
        b'<?xml version="1.0"?><rss xmlns:content="x"><channel><item><title>a</title>'
        b"<description><![CDATA[" + long.encode() + b"]]></description>"
        b"<content:encoded><![CDATA[" + long.encode() + b"]]></content:encoded></item></channel></rss>"
    )
    out = sanitize(feed, "application/rss+xml")
    assert b"content:encoded" not in out and len(out) < 900
    js = sanitize(('{"data": [' + ",".join(['{"d": "%s", "avatar": "x"}' % long] * 9) + "]}").encode(), "application/json")
    assert js.count(b'"d"') == 5 and b"avatar" not in js and len(js) < 4000


def test_sanitize_keeps_every_series_but_trims_each():
    import json

    types = [{"name": f"t{i}", "data": list(range(50))} for i in range(12)]
    body = json.dumps({"unix_seconds": list(range(50)), "production_types": types}).encode()
    out = json.loads(sanitize(body, "application/json"))
    assert len(out["production_types"]) == 12  # a list of series, not of articles: kept whole
    assert len(out["unix_seconds"]) == 5 and all(len(t["data"]) == 20 for t in out["production_types"])
