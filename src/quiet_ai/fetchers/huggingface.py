"""Hugging Face Hub (keyless): trending models/datasets/spaces, daily papers, posts."""

from __future__ import annotations

from datetime import timedelta

from quiet_ai.fetchers.base import Context, Task
from quiet_ai.store.models import Item, Metrics
from quiet_ai.text import clean_text, first_line, parse_iso

NAME = "huggingface"
HUB = "https://huggingface.co"
_REPO_KIND = {"models": "model", "datasets": "dataset", "spaces": "space"}
_URL_PREFIX = {"models": "", "datasets": "datasets/", "spaces": "spaces/"}


def tasks(ctx: Context) -> list[Task]:
    out = [Task(f"hf_{t}", NAME, lambda t=t: fetch_trending(ctx, t)) for t in _REPO_KIND]
    out.append(Task("hf_papers", NAME, lambda: fetch_papers(ctx)))
    out.append(Task("hf_posts", NAME, lambda: fetch_posts(ctx)))
    return out


def fetch_trending(ctx: Context, repo_type: str) -> list[Item]:
    limit = ctx.settings.huggingface.trending_limit
    r = ctx.http.get(f"{HUB}/api/{repo_type}", key=f"hf:{repo_type}", params={"sort": "trendingScore", "limit": limit})
    return [_repo_item(d, repo_type, ctx) for d in r.json()]


def _repo_item(d: dict, repo_type: str, ctx: Context) -> Item:
    rid = d["id"]
    tags = [t for t in d.get("tags", []) if ":" not in t][:8]
    if repo_type == "models":
        summary = ", ".join(x for x in [d.get("pipeline_tag"), d.get("library_name")] if x) or None
    elif repo_type == "datasets":
        summary = clean_text(d.get("description"), ctx.settings.ingest.summary_max_chars)
    else:
        summary = f"{d.get('sdk')} space" if d.get("sdk") else None
    return Item(
        id=f"hf:{_REPO_KIND[repo_type]}:{rid.lower()}",
        source=f"hf_{repo_type}",
        kind=_REPO_KIND[repo_type],
        url=f"{HUB}/{_URL_PREFIX[repo_type]}{rid}",
        title=rid,
        lang="en",
        published_at=parse_iso(d.get("createdAt")),
        author=rid.split("/")[0] if "/" in rid else None,
        summary=summary,
        metrics=Metrics(likes=d.get("likes"), downloads=d.get("downloads"), trending_score=d.get("trendingScore")),
        extra={"tags": tags, "pipeline_tag": d.get("pipeline_tag")} if repo_type == "models" else {"tags": tags},
        fetched_at=ctx.now,
    )


def fetch_papers(ctx: Context) -> list[Item]:
    items: dict[str, Item] = {}
    for back in range(ctx.settings.huggingface.papers_days):
        day = (ctx.now - timedelta(days=back)).date().isoformat()
        r = ctx.http.get(f"{HUB}/api/daily_papers", key=f"hf:papers:{back}", params={"date": day, "limit": 100})
        for d in r.json():
            p = d.get("paper") or {}
            if not p.get("id"):
                continue
            item = Item(
                id=f"paper:{p['id']}",
                source="hf_papers",
                kind="paper",
                url=f"{HUB}/papers/{p['id']}",
                title=clean_text(p.get("title") or d.get("title"), ctx.settings.ingest.title_max_chars) or p["id"],
                lang="en",
                published_at=parse_iso(p.get("publishedAt") or d.get("publishedAt")),
                author=", ".join(a.get("name", "") for a in (p.get("authors") or [])[:3]) or None,
                summary=clean_text(p.get("ai_summary") or p.get("summary"), ctx.settings.ingest.summary_max_chars),
                metrics=Metrics(likes=p.get("upvotes"), comments=d.get("numComments")),
                extra={
                    "arxiv_url": f"https://arxiv.org/abs/{p['id']}",
                    "github_repo": p.get("githubRepo"),
                    "keywords": (p.get("ai_keywords") or [])[:10],
                    "daily_date": day,
                },
                fetched_at=ctx.now,
            )
            items.setdefault(item.id, item)
    return list(items.values())


def fetch_posts(ctx: Context) -> list[Item]:
    r = ctx.http.get(
        f"{HUB}/api/posts", key="hf:posts", params={"sort": "trending", "limit": ctx.settings.huggingface.posts_limit}
    )
    items = []
    for p in r.json().get("socialPosts", []):
        author = (p.get("author") or {}).get("name")
        text = p.get("rawContent") or ""
        if not author or not text.strip():
            continue
        items.append(
            Item(
                id=f"hfpost:{author.lower()}/{p['slug']}",
                source="hf_posts",
                kind="social",
                url=f"{HUB}{p['url']}" if p.get("url", "").startswith("/") else f"{HUB}/posts/{author}/{p['slug']}",
                title=first_line(text) or text[:140],
                lang=_lang(p.get("identifiedLanguage")),
                published_at=parse_iso(p.get("publishedAt")),
                author=author,
                summary=clean_text(text, ctx.settings.ingest.summary_max_chars),
                metrics=Metrics(likes=sum(x.get("count", 0) for x in p.get("reactions", [])), comments=p.get("numComments")),
                extra={"platform": "huggingface"},
                fetched_at=ctx.now,
            )
        )
    return items


def _lang(value) -> str | None:
    """identifiedLanguage is either "en" or {"language": "en", "probability": 0.98}."""
    if isinstance(value, dict):
        value = value.get("language")
    return value if isinstance(value, str) and value else None
