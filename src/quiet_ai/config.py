"""Load config/*.yaml into typed models."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"

# sources.yaml section -> item kind for every feed in that section
FEED_SECTIONS = {
    "sources": "news",
    "aggregators": "aggregator",
    "newsletters": "newsletter",
    "labs": "lab",
    "builder_feeds": "launch",
}


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class FeedSource(_Model):
    id: str
    name: str
    kind: str
    feeds: list[str] = Field(default_factory=list)
    country: str | None = None
    language: str = "en"
    type: str | None = None
    group: str | None = None
    role: str | None = None  # newsletters: digest | commentary
    llm: bool = True  # False: never send this source's text to the LLM
    include_title: str | None = None  # regex; keep only matching titles
    sitemap: str | None = None  # for sites with no feed: read new URLs from the sitemap
    sitemap_include: str | None = None  # regex the URL must match
    sitemap_max_pages: int = 15  # pages read per run (only URLs not seen before)
    enabled: bool = True


class GdeltOutlet(_Model):
    id: str
    name: str
    country: str
    language: str = "en"
    type: str
    domains: list[str]
    enabled: bool = True


class SourcesConfig(_Model):
    feeds: list[FeedSource]
    gdelt_outlets: list[GdeltOutlet] = Field(default_factory=list)

    def by_id(self) -> dict[str, FeedSource | GdeltOutlet]:
        out: dict[str, FeedSource | GdeltOutlet] = {f.id: f for f in self.feeds}
        out.update({g.id: g for g in self.gdelt_outlets})
        return out


class Account(_Model):
    name: str
    category: str
    bluesky: str | None = None
    bluesky_active: bool = False


class HttpSettings(_Model):
    user_agent: str = "quiet-ai/0.1 (daily AI news digest; respects robots.txt)"
    robots_token: str = "quiet-ai"
    respect_robots: bool = True
    timeout_s: float = 20
    max_retries: int = 2
    backoff_base_s: float = 2
    max_retry_wait_s: float = 30
    min_interval_s: float = 1.0
    host_min_interval_s: dict[str, float] = Field(default_factory=dict)
    workers: int = 8


class IngestSettings(_Model):
    title_max_chars: int = 300
    summary_max_chars: int = 500
    max_age_days: int = 14


class GithubSettings(_Model):
    min_interval_s_unauthenticated: float = 6.5
    min_interval_s_token: float = 2.2
    per_page: int = 50
    created_within_days: int = 14
    topics: list[str] = Field(default_factory=lambda: ["llm"])
    established_topics: list[str] = Field(default_factory=list)
    established_min_stars: int = 1000
    established_pushed_within_days: int = 2


class HuggingFaceSettings(_Model):
    trending_limit: int = 50
    papers_days: int = 2
    posts_limit: int = 50


class HackerNewsSettings(_Model):
    window_hours: int = 48
    min_points: int = 20
    max_hits: int = 500


class BlueskySettings(_Model):
    posts_per_account: int = 30
    only_active: bool = True


class OpenRouterSettings(_Model):
    max_age_days: int = 14


class GdeltSettings(_Model):
    enabled: bool = True
    timespan: str = "1d"
    max_records: int = 250
    max_query_chars: int = 180
    terms: list[str] = Field(default_factory=lambda: ['"artificial intelligence"'])


class Settings(_Model):
    db_path: str = "data/quiet-ai.db"
    http: HttpSettings = Field(default_factory=HttpSettings)
    ingest: IngestSettings = Field(default_factory=IngestSettings)
    github: GithubSettings = Field(default_factory=GithubSettings)
    huggingface: HuggingFaceSettings = Field(default_factory=HuggingFaceSettings)
    hackernews: HackerNewsSettings = Field(default_factory=HackerNewsSettings)
    bluesky: BlueskySettings = Field(default_factory=BlueskySettings)
    openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)
    gdelt: GdeltSettings = Field(default_factory=GdeltSettings)


def _yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_settings(config_dir: Path = CONFIG_DIR) -> Settings:
    return Settings.model_validate(_yaml(config_dir / "settings.yaml"))


def load_sources(config_dir: Path = CONFIG_DIR) -> SourcesConfig:
    raw = _yaml(config_dir / "sources.yaml")
    feeds = [
        FeedSource.model_validate({**entry, "kind": kind})
        for section, kind in FEED_SECTIONS.items()
        for entry in raw.get(section) or []
    ]
    ids = [f.id for f in feeds] + [g["id"] for g in raw.get("gdelt_outlets") or []]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate source ids in sources.yaml: {sorted(dupes)}")
    return SourcesConfig(feeds=feeds, gdelt_outlets=raw.get("gdelt_outlets") or [])


def load_accounts(config_dir: Path = CONFIG_DIR) -> list[Account]:
    return [Account.model_validate(a) for a in _yaml(config_dir / "accounts.yaml").get("accounts") or []]
