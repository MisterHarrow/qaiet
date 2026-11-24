"""Bluesky: recent posts (no replies, no reposts) from the curated account list."""

from __future__ import annotations

from quiet_ai.config import Account
from quiet_ai.fetchers.base import Context, Task
from quiet_ai.store.models import Item, Metrics
from quiet_ai.text import canonical_url, clean_text, first_line, parse_iso

NAME = "bluesky"
API = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"


def tasks(ctx: Context) -> list[Task]:
    accounts = [a for a in ctx.accounts if a.bluesky and (a.bluesky_active or not ctx.settings.bluesky.only_active)]
    return [Task(f"bluesky:{a.bluesky}", NAME, lambda a=a: fetch_account(ctx, a)) for a in accounts]


def fetch_account(ctx: Context, account: Account) -> list[Item]:
    r = ctx.http.get(
        API,
        key=f"bsky:{account.bluesky}",
        params={"actor": account.bluesky, "limit": ctx.settings.bluesky.posts_per_account, "filter": "posts_no_replies"},
    )
    items = []
    for entry in r.json().get("feed", []):
        if entry.get("reason"):  # a repost of someone else's post
            continue
        post = entry["post"]
        author = post.get("author") or {}
        record = post.get("record") or {}
        text = record.get("text") or ""
        did, rkey = post["uri"].removeprefix("at://").split("/app.bsky.feed.post/")
        links = extract_links(post)
        title = first_line(text) or (links[0] if links else None)
        if not title:
            continue
        items.append(
            Item(
                id=f"bsky:{did}/{rkey}",
                source="bluesky",
                kind="social",
                url=f"https://bsky.app/profile/{author.get('handle', account.bluesky)}/post/{rkey}",
                title=title,
                lang=(record.get("langs") or [None])[0],
                published_at=parse_iso(record.get("createdAt")),
                author=author.get("handle", account.bluesky),
                summary=clean_text(text, ctx.settings.ingest.summary_max_chars),
                metrics=Metrics(
                    likes=post.get("likeCount"),
                    reposts=(post.get("repostCount") or 0) + (post.get("quoteCount") or 0),
                    comments=post.get("replyCount"),
                ),
                extra={"platform": "bluesky", "links": links, "account": account.name, "category": account.category},
                fetched_at=ctx.now,
            )
        )
    return items


def extract_links(post: dict) -> list[str]:
    """Links in the text (facets) and the link card (external embed), canonicalized."""
    out: list[str] = []
    for facet in (post.get("record") or {}).get("facets") or []:
        for feat in facet.get("features") or []:
            if feat.get("$type") == "app.bsky.richtext.facet#link" and feat.get("uri"):
                out.append(feat["uri"])
    embed = post.get("embed") or {}
    for e in (embed, embed.get("media") or {}):
        ext = e.get("external") or {}
        if ext.get("uri"):
            out.append(ext["uri"])
    seen, links = set(), []
    for u in out:
        if u.startswith("http"):
            c = canonical_url(u)
            if c not in seen:
                seen.add(c)
                links.append(c)
    return links
