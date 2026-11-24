# M5 notes: automation and deploy

Live at https://misterharrow.github.io/quiet-ai/ (GitHub Pages, deployed by Actions). Repo: https://github.com/MisterHarrow/quiet-ai (public).

## How it runs

`.github/workflows/run.yml`, every 2 hours at :17 UTC, plus manual runs from the Actions tab:

1. Restore `data/quiet-ai.db` from the `db` release (`quiet-ai.db.gz`).
2. `uv run qa run`:
   - ingest, relevance, stories, labels, the four views, summaries, the site;
   - store today's front page in `editions`;
   - after midnight Stockholm, freeze the finished day to `editions/<date>.json`;
   - prune.
3. Upload the database back (`--clobber`), plus `quiet-ai-<date>.db.gz` (one per day, 14 kept).
4. Commit new frozen editions (`github-actions[bot]`). The daily commit also stops GitHub from pausing the schedule after 60 days without activity.
5. Upload `site/` and deploy it to Pages.

`concurrency: quiet-ai-run` means two runs never touch the database at once. `test.yml` runs the tests on every push.

Setup done on 2026-11-24:
- public repo;
- Pages source set to "GitHub Actions";
- `ANTHROPIC_API_KEY` secret, set by Benjamin;
- the dev database (collection since that morning) uploaded as the first release asset, so history continues.

## First runs

- **Run time:** about 4 minutes for the pipeline and 15 seconds to deploy. The embedding model is cached between runs.
- **`setup-uv`:** astral publishes no `v10` major tag, only full versions, so it is pinned to `v10.4.0`. The `actions/*` actions do have major tags.
- **Blocked from GitHub's servers:** sources that work from a home connection but refuse GitHub's cloud IPs.

  | Source | Answer | What we did |
  |---|---|---|
  | Import AI, Zvi (Substack) | 403 | Switched to their own WordPress feeds (jack-clark.net, thezvi.wordpress.com). |
  | Marcus on AI, ChinAI (Substack only) | 403 | Kept; they show as failing on /about under source health. |
  | The Batch (deeplearning.ai, Vercel) | 403 | Kept; same. |
  | GDELT | 429 | Kept; its rate limit seems to count GitHub's shared IPs. |

  Working around these blocks (proxies, browser-like user agents) is out of bounds by design.

## Cost control

The first scheduled run cost $0.12, mostly 19 Sonnet summaries. At 12 runs a day that is about $40 a month, over the $30 cap. The cause: big stories gain a few items every run, and "3 new items or a new outlet" re-summarized them almost every time, in four views.

Now:
- **Summaries** refresh only when a story grows by about 30% (at least 3 items), gains about 20% more outlets (at least 1), or its stance mix moves by 20% (at least 3 labels).
- **Weather lines** refresh when a view's top 3 stories change, or at most every 6 hours otherwise.

The settings are `analysis.resummarize_growth` and `analysis.weather_min_hours`. `qa costs` shows the month's pace; the cap still stops all LLM steps at $30.
