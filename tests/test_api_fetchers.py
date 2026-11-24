"""Edge cases of the API fetchers, with small inline payloads served through MockTransport."""

from __future__ import annotations

import json
from datetime import timedelta

import httpx

from quiet_ai.config import Account, GdeltOutlet, SourcesConfig
from quiet_ai.fetchers import bluesky, gdelt, github, huggingface, openrouter
from quiet_ai.http import Http
from tests.conftest import NOW, make_ctx


def mock_http(settings, routes: dict[str, object]) -> Http:
    """routes: substring of URL -> JSON-able body (or bytes). robots.txt is always 404."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/robots.txt"):
            return httpx.Response(404)
        for frag, body in routes.items():
            if frag in url:
                if isinstance(body, bytes):
                    return httpx.Response(200, content=body, headers={"content-type": "text/plain"})
                return httpx.Response(200, json=body)
        return httpx.Response(404)

    return Http(settings.http, transport=httpx.MockTransport(handler), sleep=lambda s: None)


def post(rkey, text, reason=None, facets=None, embed=None):
    entry = {
        "post": {
            "uri": f"at://did:plc:abc/app.bsky.feed.post/{rkey}",
            "author": {"handle": "someone.bsky.social"},
            "record": {"text": text, "createdAt": "2026-11-24T07:00:00.000Z", "facets": facets or [], "langs": ["en"]},
            "embed": embed or {},
            "likeCount": 3, "repostCount": 1, "quoteCount": 1, "replyCount": 2,
        }
    }
    if reason:
        entry["reason"] = reason
    return entry


def test_bluesky_skips_reposts_and_extracts_links(settings):
    feed = {"feed": [
        post("1", "Read this https://ex.com/a", facets=[{"features": [{"$type": "app.bsky.richtext.facet#link", "uri": "https://ex.com/a?utm_source=x"}]}],
             embed={"$type": "app.bsky.embed.external#view", "external": {"uri": "https://github.com/o/r"}}),
        post("2", "someone else's post", reason={"$type": "app.bsky.feed.defs#reasonRepost"}),
    ]}
    http = mock_http(settings, {"getAuthorFeed": feed})
    acct = Account(name="Someone", category="builder", bluesky="someone.bsky.social", bluesky_active=True)
    items = bluesky.fetch_account(make_ctx(settings, http, accounts=[acct]), acct)
    assert len(items) == 1
    it = items[0]
    assert it.id == "bsky:did:plc:abc/1"
    assert it.url == "https://bsky.app/profile/someone.bsky.social/post/1"
    assert it.extra["links"] == ["https://ex.com/a", "https://github.com/o/r"]
    assert it.metrics.reposts == 2 and it.metrics.comments == 2


def test_bluesky_only_polls_active_accounts(settings):
    accts = [Account(name="A", category="x", bluesky="a.b", bluesky_active=True),
             Account(name="B", category="x", bluesky="b.b", bluesky_active=False),
             Account(name="C", category="x")]
    ctx = make_ctx(settings, mock_http(settings, {}), accounts=accts)
    assert [t.source for t in bluesky.tasks(ctx)] == ["bluesky:a.b"]


def test_openrouter_keeps_recent_base_models(settings):
    ts = lambda days: int((NOW - timedelta(days=days)).timestamp())
    data = {"data": [
        {"id": "lab/new-model", "name": "New", "created": ts(2), "pricing": {"prompt": "0.000001"}},
        {"id": "lab/new-model:free", "name": "New (free)", "created": ts(2)},
        {"id": "lab/old-model", "name": "Old", "created": ts(60)},
    ]}
    items = openrouter.fetch(make_ctx(settings, mock_http(settings, {"openrouter.ai/api": data})))
    assert [i.id for i in items] == ["openrouter:lab/new-model"]
    assert items[0].author == "lab"


def test_github_dedupes_across_queries_and_records_stars(settings, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    repo = {"full_name": "Org/Repo", "html_url": "https://github.com/Org/Repo", "created_at": "2026-11-20T00:00:00Z",
            "owner": {"login": "Org"}, "description": "An <b>agent</b> framework", "stargazers_count": 1234, "topics": ["llm"]}
    items = github.fetch(make_ctx(settings, mock_http(settings, {"search/repositories": {"items": [repo]}})))
    assert len(items) == 1
    it = items[0]
    assert it.id == "github:org/repo" and it.metrics.stars == 1234 and it.summary == "An agent framework"
    assert len(it.extra["queries"]) == len(github.queries(make_ctx(settings, None)))


def test_hf_posts_language_object(settings):
    posts = {"socialPosts": [{"slug": "1", "url": "/posts/dan/1", "author": {"name": "dan"}, "rawContent": "We made it faster\nmore",
                              "identifiedLanguage": {"language": "en", "probability": 0.9},
                              "reactions": [{"count": 4}, {"count": 1}], "numComments": 2, "publishedAt": "2026-11-23T00:00:00Z"}]}
    items = huggingface.fetch_posts(make_ctx(settings, mock_http(settings, {"api/posts": posts})))
    assert items[0].lang == "en" and items[0].metrics.likes == 5 and items[0].title == "We made it faster"


def test_gdelt_queries_stay_short():
    outlets = [GdeltOutlet(id=f"o{i}", name="O", country="CN", type="state-aligned", domains=[f"domain{i}.example.com"]) for i in range(10)]
    queries = gdelt.build_queries(['"artificial intelligence"', "OpenAI"], outlets, 150)
    assert len(queries) > 1 and all(len(q) <= 150 for q in queries)
    assert sum(q.count("domain:") for q in queries) == 10


def test_gdelt_maps_domains_and_surfaces_text_errors(settings):
    outlets = [GdeltOutlet(id="xinhua", name="Xinhua", country="CN", type="state-aligned", domains=["xinhuanet.com", "news.cn"])]
    sources = SourcesConfig(feeds=[], gdelt_outlets=outlets)
    arts = {"articles": [
        {"url": "http://english.news.cn/a.html", "title": "AI story", "seendate": "20261124T061500Z", "domain": "english.news.cn", "language": "English"},
        {"url": "http://other.com/b", "title": "Unrelated", "seendate": "20261124T061500Z", "domain": "other.com", "language": "English"},
    ]}
    items = gdelt.fetch(make_ctx(settings, mock_http(settings, {"gdeltproject": arts}), sources=sources))
    assert [(i.source, i.lang) for i in items] == [("xinhua", "en")]
    assert items[0].published_at.isoformat() == "2026-11-24T06:15:00+00:00"

    http = mock_http(settings, {"gdeltproject": b"Your query was too short or too long."})
    try:
        gdelt.fetch(make_ctx(settings, http, sources=sources))
    except ValueError as e:
        assert "too short" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_github_drops_clone_spam(settings, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    mk = lambda owner, name, stars=300: {"full_name": f"{owner}/{name}", "html_url": f"https://github.com/{owner}/{name}",  # noqa: E731
                                         "owner": {"login": owner}, "stargazers_count": stars}
    repos = [mk("a", "manus--ai"), mk("b", "ai--manus"), mk("c", "manus-ai2.0"), mk("d", "vllm"), mk("e", "vllm-router")]
    items = github.fetch(make_ctx(settings, mock_http(settings, {"search/repositories": {"items": repos}})))
    assert sorted(i.title for i in items) == ["d/vllm", "e/vllm-router"]
