"""Fetcher registry. Each module exposes NAME and tasks(ctx) -> list[Task]."""

from quiet_ai.fetchers import bluesky, gdelt, github, hackernews, huggingface, news_rss, openrouter, sitemap

FETCHERS = {m.NAME: m for m in (news_rss, sitemap, gdelt, github, huggingface, hackernews, bluesky, openrouter)}
