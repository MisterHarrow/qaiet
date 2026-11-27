# Qaiet Times

Qaiet Times (repo `qaiet`; the Python package is still called `quiet_ai`) is a calm, text-first page that answers once a day: what happened in AI, how is it being framed, and what are builders actually making?

Status: **M5 (automation)**, live at https://news.b3njamin.ai/ (Vercel; the old GitHub Pages address forwards there). Sources are fetched, filtered for AI relevance, grouped into stories, labeled (track, frame, stance, evidence), ranked by momentum, summarized and rendered as a static page, published every morning at 06:30 Stockholm time by GitHub Actions (sources are collected every 2 hours). Notes per milestone: [M0 plan and sources](docs/m0-report.md), [M2 relevance and clustering](docs/m2-notes.md), [M3 labels, momentum, costs](docs/m3-notes.md), [M4 site](docs/m4-notes.md), [M5 automation](docs/m5-notes.md).

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
uv run qa run                    # everything: ingest, stories, labels, summaries, site
uv run qa build                  # render site/ from the database (no LLM calls)
uv run qa serve                  # build and preview at http://localhost:8765
uv run qa cluster                # relevance filter, embeddings, stories
uv run qa classify               # labels (Haiku), momentum, summaries and weather (Sonnet); prints the edition
uv run qa stories                # print the ranked stories from the database, no LLM calls
uv run qa stories -p week        # same for another view: day, week, month, year
uv run qa costs                  # LLM spend this month against the cap
uv run qa bulletin               # make today's spoken bulletin by hand (needs ffmpeg; Ming needs `uv sync --extra voice` on Apple Silicon)
uv run qa bulletin --reuse-script --force  # voice the day's existing script again (after editing data/audio/bulletin-<date>.txt)
uv run qa pull                   # replace data/quiet-ai.db with the live database (the `db` release asset)
uv run qa eval sample            # write a blind, stratified sample to tests/gold/labels.yaml for hand labeling
uv run qa eval crosscheck        # label the same sample with Claude Opus 5.5 and score the site against it
uv run qa eval score             # agreement between the model's labels and the hand labels
uv run qa eval audit --by group  # stance by outlet group (or --by type / country), to spot classifier skew
uv run qa classify --dry-run     # any of these with --dry-run: fixtures, no network, no LLM
uv run qa sources check          # fetch every source once and report health (writes nothing)
uv run qa sources check --dry-run --strict
uv run qa sources list
uv run pytest
```

## Sources

All free, no accounts. Configured in `config/`:

| File | What |
|---|---|
| `sources.yaml` | News outlets, aggregators (Techmeme, Memeorandum), newsletters (digests and commentary), lab blogs, Product Hunt, and outlets read through GDELT (wires, Chinese state media). `mentions: true` (AINews) keeps the X posts and Reddit threads a recap links next to an article or project, and turns each X bullet into a small `recap` item that can join a story; X and Reddit themselves are never fetched. |
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

## Deploy (GitHub Actions + Vercel)

`.github/workflows/run.yml` has three kinds of run (`.github/scripts/plan.sh` decides which):

- **collect**, every 2 hours: restore the database, `uv run qa ingest`, save it. No model calls, no deploy.
- **publish**, every morning from 06:30 Stockholm; manual runs publish by default. GitHub drops scheduled runs under load, so no single cron is trusted: any scheduled run publishes once it is past 06:30 local and the live `edition.json` is older than that. A morning cron (every 20 minutes, 04:10–09:50 UTC, covering winter and summer time) retries, and the 2-hourly collect run is the backstop. A publish run does:

1. Restores `data/quiet-ai.db` from the `db` release (gzipped asset).
2. `uv run qa run`: ingest, stories, labels, summaries, the site, plus:
   - stores today's front page as the day's edition;
   - freezes earlier days' editions to `editions/<date>.json`;
   - prunes old data (items not about AI after 15 days, everything after 400 days; snapshots thinned after 7 days);
   - writes today's spoken bulletin script (`pipeline/bulletin.py`): Sonnet writes it for the ear (`bulletin_v1`), kept as an `audio` release asset. The voice, Ming-3.0-tts (MIT), runs only on Apple Silicon, so a Mac voices it: `deploy/mac/bulletin.sh`, run by launchd each morning (`deploy/mac/install.sh`), downloads the script, voices it paragraph by paragraph offline (`qa bulletin --reuse-script`), ffmpeg joins, levels and encodes one MP3, uploads it and starts a `deploy` run. The page's player (native `<audio>`, speed buttons from `app.js`) replays the stored file. The `audio` release keeps 30 days; every publish and deploy restores it. If anything fails, the site goes on without the player. `bulletin.tts_engine: elevenlabs` voices it in the publish instead (paid; needs the `ELEVENLABS_API_KEY` secret).
3. Uploads the database back to the release, plus a dated daily snapshot (14 kept).
4. Commits new frozen editions. The daily commit also keeps GitHub from pausing the schedule after 60 days of inactivity.
5. Deploys `site/` to Vercel (news.b3njamin.ai) with the Vercel CLI; Vercel never builds (the root `vercel.json` turns off its Git deploys, which `vercel link` connects; with them on, every push to `main` would replace the site with the repo root). GitHub Pages only serves a forward from the old address (`deploy/pages-redirect/`).

- **deploy**, manual only (`gh workflow run run.yml -f mode=deploy`): rebuilds the site from the saved database with no model calls and deploys it. For page changes; run it after the morning publish.

One-time setup:

```sh
gh secret set ANTHROPIC_API_KEY --repo <owner>/qaiet   # paste the key when asked
gh api -X POST repos/<owner>/qaiet/pages -f build_type=workflow
npx vercel login && npx vercel project add qaiet && npx vercel link --yes --project qaiet
gh secret set VERCEL_TOKEN --repo <owner>/qaiet        # an account token from vercel.com/account/settings/tokens
gh secret set VERCEL_ORG_ID --repo <owner>/qaiet       # orgId from .vercel/project.json
gh secret set VERCEL_PROJECT_ID --repo <owner>/qaiet   # projectId from .vercel/project.json
gh secret set ELEVENLABS_API_KEY --repo <owner>/qaiet  # only if bulletin.tts_engine is elevenlabs
```

On the Mac that voices the bulletin: `uv sync --extra voice`, the Ming weights in the Hugging Face cache, `gh` signed in, ffmpeg, then `deploy/mac/install.sh` (`--remove` to undo).

The domain: add it to the Vercel project (`npx vercel domains add news.b3njamin.ai qaiet`) and create the CNAME record it names at the DNS host (Namecheap).

Without the secret the pipeline still runs and deploys, with no labels or summaries.

`.github/workflows/test.yml` runs the tests on every push.

Other commands: `qa freeze` (write finished days now), `qa prune [--vacuum]`.
