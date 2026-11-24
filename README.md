# quiet-ai

A calm, text-first page that answers once a day: what happened in AI, how is it being framed, and what are builders actually making?

Status: **M2 (stories)**. Sources are fetched into SQLite, filtered for AI relevance and grouped into stories. Labels, ranking and the site come in later milestones. Plan and source verification: [docs/m0-report.md](docs/m0-report.md). Relevance and clustering decisions: [docs/m2-notes.md](docs/m2-notes.md).

## Setup

```sh
uv sync
cp .env.example .env   # ANTHROPIC_API_KEY (relevance of ambiguous items, translations), optional GITHUB_TOKEN
```

## Commands

```sh
uv run qa ingest                 # fetch every source, store new items in data/quiet-ai.db
uv run qa ingest -s github -s nyt  # only some sources or fetchers
uv run qa ingest --dry-run       # replay recorded fixtures: no network, nothing written
uv run qa cluster                # relevance filter, embeddings, stories; prints the current stories
uv run qa cluster --dry-run      # same on fixtures, no network, no LLM
uv run qa sources check          # fetch every source once and report health (writes nothing)
uv run qa sources check --dry-run --strict
uv run qa sources list
uv run pytest
```

## Sources

All free, no accounts. Configured in `config/`:

| File | What |
|---|---|
| `sources.yaml` | News outlets, aggregators (Techmeme, Memeorandum), newsletters (digests and commentary), lab blogs, Product Hunt, and outlets read through GDELT (wires, Chinese state media). |
| `accounts.yaml` | Curated Bluesky accounts. Only `bluesky_active: true` ones are polled. |
| `settings.yaml` | User agent, rate limits, per-fetcher options, later the LLM budget. |

Fetchers (`src/quiet_ai/fetchers/`): `news_rss`, `sitemap` (sites with no feed, e.g. The Batch), `gdelt`, `github`, `huggingface` (trending models/datasets/spaces, daily papers, posts), `hackernews`, `bluesky`, `openrouter`.

Courtesy rules, enforced in `src/quiet_ai/http.py`:

- One identifiable user agent. Requests to the same host are serialized and spaced (`http.min_interval_s`, per-host overrides).
- robots.txt is checked for every URL (RFC 9309: unreachable robots.txt means disallow). Sources whose robots.txt forbids us are dropped, not worked around.
- Conditional GET (ETag / Last-Modified) for feeds. Retries with backoff on 429/5xx, honouring `Retry-After`.
- We store only headline, a short summary (500 chars), URL, dates and our own analysis. No full text, no images.
- `llm: false` on a source (set where robots.txt says `Content-Signal: ai-input=no`) means its text is never sent to an LLM. `qa sources check` flags a mismatch.

## Data

SQLite at `data/quiet-ai.db` (git-ignored). Tables: `items` (one row per item, upserted, so runs are idempotent; plus relevance, English title and story), `metric_snapshots` (stars/points/likes per run, for velocity), `embeddings` (last 7 days), `stories` (stable IDs, centroids), `llm_cache` and `llm_calls` (per-item results, tokens and cost), `fetch_state` (ETags), `runs` and `source_runs` (per-source health for every run).

The embedding model (~220 MB) downloads to `.cache/fastembed` on first use.

## Fixtures

`tests/fixtures/http/` holds one recorded response per request key, trimmed to a few items with long text cut, so fixtures contain no more than the site would show. Refresh them with:

```sh
uv run qa ingest --record        # live fetch, writes fixtures, stores nothing
```
