"""Load config/*.yaml into typed models."""

from __future__ import annotations

from datetime import date
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
    ai_focused: bool = False  # an AI-only feed: every item counts as relevant
    mentions: bool = False  # a recap of X/Reddit: keep the posts and threads it links (pipeline/mentions.py)
    index_from: date | None = None  # its labels count in the sentiment index from this local day (a new language waits two weeks)
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
    clone_spam_min: int = 3


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
    source_lang: str | None = "english"
    terms: list[str] = Field(default_factory=lambda: ['"artificial intelligence"'])


class RelevanceSettings(_Model):
    always_kinds: list[str] = Field(default_factory=lambda: ["repo", "model", "dataset", "space", "paper", "launch"])
    always_sources: list[str] = Field(default_factory=lambda: ["hf_posts"])
    llm_batch_size: int = 25
    prompt: str = "relevance_v2"
    translate_prompt: str = "translate_v1"  # English titles the relevance call left empty


class EmbedSettings(_Model):
    model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    cache_dir: str = ".cache/fastembed"
    summary_chars: int = 300
    keep_days: int = 7


class ClusterSettings(_Model):
    window_hours: int = 72
    join_threshold: float = 0.62
    confident_threshold: float = 0.72
    strict_join_threshold: float = 0.8
    strict_kinds: list[str] = Field(default_factory=lambda: ["repo", "model", "dataset", "space", "paper", "launch"])
    join_only_kinds: list[str] = Field(default_factory=lambda: ["recap"])  # join a story, never start one
    merge_threshold: float = 0.76
    entity_boost: float = 0.03


class MomentumSettings(_Model):
    half_life_hours: float = 36
    weights: dict[str, float] = Field(default_factory=lambda: {
        "outlets": 0.25, "countries": 0.10, "hn_points": 0.15, "star_velocity": 0.10,
        "hf_trending": 0.10, "social": 0.10, "aggregators": 0.10, "digests": 0.10,
    })


class RisingSettings(_Model):
    window_hours: int = 48
    quota: dict[str, int] = Field(default_factory=lambda: {"repo": 10, "model": 5, "space": 3, "dataset": 3, "paper": 5})


class AnalysisSettings(_Model):
    label_batch_size: int = 20
    news_prompt: str = "news_label_v3"
    builder_prompt: str = "builder_label_v1"
    summary_prompt: str = "story_summary_v4"
    weather_prompt: str = "weather_v3"
    summarize_top: int = 12
    resummarize_new_items: int = 3   # re-summarize after at least this many new items...
    resummarize_growth: float = 0.3  # ...and the story grew by this share (outlets: two thirds of it)
    weather_min_hours: float = 6     # weather lines refresh at most this often, unless the top 3 change
    builder_label_top: int = 30      # label this many Rising candidates (plus builders in top stories)
    stance_kinds: list[str] = Field(default_factory=lambda: ["news", "newsletter"])
    top_stories: int = 12            # stories on the page


class PeriodSettings(_Model):
    key: str
    label: str
    hours: int
    half_life_hours: float           # momentum decay within this view
    merge: bool = False              # merge stories that recur within the period (longer views)


def _default_periods() -> list[PeriodSettings]:
    return [
        PeriodSettings(key="day", label="24 hours", hours=24, half_life_hours=36),
        PeriodSettings(key="week", label="7 days", hours=168, half_life_hours=96, merge=True),
        PeriodSettings(key="month", label="30 days", hours=720, half_life_hours=360, merge=True),
        PeriodSettings(key="year", label="1 year", hours=8760, half_life_hours=2160, merge=True),
    ]


class GapSettings(_Model):
    max_items: int = 5
    quiet_max_outlets: int = 1          # "builders are talking, press isn't": at most this many outlets...
    builder_min_rank: float = 0.85      # ...and a builder signal in the top 15% of stories in view...
    builder_floors: dict[str, float] = Field(default_factory=lambda: {   # ...that is also big in absolute terms
        "hn_points": 80, "star_velocity": 150, "hf_trending": 60})
    loud_min_outlets: int = 5           # "press is talking, builders aren't": at least this many outlets...
    builder_max_rank_quiet: float = 0.25  # ...and builder signals in the bottom quarter (usually none)


class SentimentSettings(_Model):
    confidence_weights: dict[str, float] = Field(default_factory=lambda: {"high": 1.0, "medium": 0.7})
    min_outlets: int = 3                # a track needs labels from this many outlets on a day to get a value
    recompute_days: int = 3             # late labels can still change the last few days


class NarrativeSettings(_Model):
    min_days: int = 4                   # press coverage on this many local days in a row makes a story a narrative
    ongoing_days: int = 1               # still "ongoing" when last covered today or up to this many days ago
    front_max: int = 6                  # ongoing narratives listed on the front page
    headlines_per_day: int = 3          # headlines shown per day on a narrative's page


class SiteSettings(_Model):
    out_dir: str = "site"
    editions_dir: str = "editions"
    timezone: str = "Europe/Stockholm"
    periods: list[PeriodSettings] = Field(default_factory=_default_periods)  # first one is the front page
    period_merge_threshold: float = 0.72
    period_merge_candidates: int = 300
    terms_count: int = 16
    term_aliases: dict[str, str] = Field(default_factory=dict)
    term_stopwords: list[str] = Field(default_factory=lambda: ["ai", "artificial intelligence"])


class ScheduleSettings(_Model):
    """Documents the workflow's timing for the site's text; .github/workflows/run.yml is what runs it."""
    collect_every_hours: int = 2
    publish_at: str = "06:30"
    timezone: str = "Europe/Stockholm"


class ModelPrice(_Model):
    input: float
    output: float
    cache_read: float = 0.0
    cache_write: float = 0.0


class LLMSettings(_Model):
    item_model: str = "claude-haiku-5-5"
    story_model: str = "claude-sonnet-5-5"
    monthly_budget_usd: float = 30
    prices: dict[str, ModelPrice] = Field(default_factory=dict)  # USD per million tokens


class Settings(_Model):
    db_path: str = "data/quiet-ai.db"
    db_release_url: str = ""  # public URL of the gzipped database the workflow saves (qa pull)
    http: HttpSettings = Field(default_factory=HttpSettings)
    ingest: IngestSettings = Field(default_factory=IngestSettings)
    github: GithubSettings = Field(default_factory=GithubSettings)
    huggingface: HuggingFaceSettings = Field(default_factory=HuggingFaceSettings)
    hackernews: HackerNewsSettings = Field(default_factory=HackerNewsSettings)
    bluesky: BlueskySettings = Field(default_factory=BlueskySettings)
    openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)
    gdelt: GdeltSettings = Field(default_factory=GdeltSettings)
    relevance: RelevanceSettings = Field(default_factory=RelevanceSettings)
    embed: EmbedSettings = Field(default_factory=EmbedSettings)
    cluster: ClusterSettings = Field(default_factory=ClusterSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    momentum: MomentumSettings = Field(default_factory=MomentumSettings)
    rising: RisingSettings = Field(default_factory=RisingSettings)
    analysis: AnalysisSettings = Field(default_factory=AnalysisSettings)
    site: SiteSettings = Field(default_factory=SiteSettings)
    schedule: ScheduleSettings = Field(default_factory=ScheduleSettings)
    gap: GapSettings = Field(default_factory=GapSettings)
    sentiment: SentimentSettings = Field(default_factory=SentimentSettings)
    narratives: NarrativeSettings = Field(default_factory=NarrativeSettings)


def _yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Minimal .env support: KEY=value lines; never overrides the real environment."""
    import os

    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value and key.strip() not in os.environ:
            os.environ[key.strip()] = value


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
