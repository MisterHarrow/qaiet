"""GitHub Search API: new AI repos and established ones still gaining stars.

Star velocity is computed later from metric_snapshots across runs; github.com/trending is
not used (no API, and GitHub's Acceptable Use Policy doesn't cover scraping it for this).
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from datetime import timedelta

from quiet_ai.fetchers.base import Context, Task
from quiet_ai.store.models import Item, Metrics
from quiet_ai.text import clean_text, parse_iso

NAME = "github"
API = "https://api.github.com/search/repositories"


def tasks(ctx: Context) -> list[Task]:
    return [Task("github", NAME, lambda: fetch(ctx))]


def queries(ctx: Context) -> list[tuple[str, str]]:
    g = ctx.settings.github
    created = (ctx.now - timedelta(days=g.created_within_days)).date().isoformat()
    pushed = (ctx.now - timedelta(days=g.established_pushed_within_days)).date().isoformat()
    out = [(f"github:new:{t}", f"topic:{t} created:>{created}") for t in g.topics]
    out += [
        (f"github:established:{t}", f"topic:{t} stars:>={g.established_min_stars} pushed:>{pushed}")
        for t in g.established_topics
    ]
    return out


def fetch(ctx: Context) -> list[Item]:
    g = ctx.settings.github
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    ctx.http.set_host_interval("api.github.com", g.min_interval_s_token if token else g.min_interval_s_unauthenticated)
    repos: dict[str, Item] = {}
    for key, q in queries(ctx):
        r = ctx.http.get(API, key=key, headers=headers, params={"q": q, "sort": "stars", "order": "desc", "per_page": g.per_page})
        for repo in r.json().get("items", []):
            item = to_item(repo, ctx)
            item.extra.setdefault("queries", []).append(key.split(":", 1)[1])
            if item.id in repos:
                repos[item.id].extra["queries"] += item.extra["queries"]
            else:
                repos[item.id] = item
    return drop_clone_spam(list(repos.values()), g.clone_spam_min)


def drop_clone_spam(items: list[Item], min_owners: int) -> list[Item]:
    """Star-farmed spam shows up as many owners publishing the same repo name
    ("manus--ai", "ai--manus2.0", ...). Drop every repo in such a group."""
    groups: dict[str, set[str]] = defaultdict(set)
    # Word order varies ("manus--ai" / "ai--manus2.0"): compare the set of words.
    key = lambda it: " ".join(sorted(set(re.findall(r"[a-z]+", it.title.split("/", 1)[-1].lower()))))  # noqa: E731
    for it in items:
        groups[key(it)].add(it.author or "")
    return [it for it in items if len(groups[key(it)]) < min_owners or not key(it)]


def to_item(repo: dict, ctx: Context) -> Item:
    return Item(
        id=f"github:{repo['full_name'].lower()}",
        source="github",
        kind="repo",
        url=repo["html_url"],
        title=repo["full_name"],
        lang="en",
        published_at=parse_iso(repo.get("created_at")),
        author=(repo.get("owner") or {}).get("login"),
        summary=clean_text(repo.get("description"), ctx.settings.ingest.summary_max_chars),
        metrics=Metrics(stars=repo.get("stargazers_count")),
        extra={
            "language": repo.get("language"),
            "topics": repo.get("topics", []),
            "forks": repo.get("forks_count"),
            "pushed_at": repo.get("pushed_at"),
            "homepage": repo.get("homepage") or None,
        },
        fetched_at=ctx.now,
    )
