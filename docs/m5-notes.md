# M5 notes: automation and deploy

Live at https://misterharrow.github.io/quiet-ai/ (GitHub Pages, deployed by Actions). Repo: https://github.com/MisterHarrow/quiet-ai (public).

## How it runs

**Schedule (changed the same day, at Benjamin's request): published once a day at 06:30 Stockholm, collected every 2 hours.**

- **Collect runs** (every 2 hours at :17 UTC): restore the database, fetch every source, save. No model calls and no deploy, so they cost nothing. They exist because about 10 high-volume feeds (Bloomberg, The Hill, Business Insider, SvD, Al Jazeera, France 24, Korea Herald, ABC, Dagens industri) list fewer items than they publish in a day; fetching once a day would miss part of their coverage.
- **Publish runs** (06:30 Stockholm): everything below. GitHub cron is UTC and can't follow daylight saving, so it fires at 04:30 and 05:30 UTC and `.github/scripts/plan.sh` keeps the one that is 06:xx in Stockholm. Manual runs from the Actions tab publish by default, or collect if chosen.
- **Editions:** each publish is that day's edition. The next morning's publish freezes it to `editions/<date>.json` and the archive.

A publish run does:

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

  Working around these blocks (proxies, browser-like user agents) is out of bounds by design. The blocks are intermittent: on the second run Marcus on AI, ChinAI and The Batch all worked, and only Breitbart and GDELT failed.

## Cost control

The first scheduled run cost $0.12, mostly 19 Sonnet summaries. At 12 runs a day that is about $40 a month, over the $30 cap. The cause: big stories gain a few items every run, and "3 new items or a new outlet" re-summarized them almost every time, in four views.

Now:
- **Summaries** refresh only when a story grows by about 30% (at least 3 items), gains about 20% more outlets (at least 1), or its stance mix moves by 20% (at least 3 labels).
- **Weather lines** refresh when a view's top 3 stories change, or at most every 6 hours otherwise.

Verified on the next run: **$0.019** (2 summaries, 3 weather lines, a few Haiku batches). With one publish a day (a full day of new items to label and more stories changed), expect roughly $0.05–0.15 a day, **about $2–5 a month**. The settings are `analysis.resummarize_growth` and `analysis.weather_min_hours`. `qa costs` shows the month's pace; the cap still stops all LLM steps at $30.

## Schedule fix (25 November)

The first scheduled morning never published. From the schedule change (24 Nov, 12:51 UTC) to the next morning, GitHub fired only 1 of 11 scheduled triggers (a collect run at 00:29 Stockholm) and dropped both publish slots, so the site still showed the afternoon's manual edition. GitHub says scheduled runs "may be delayed or dropped" under load; nothing in the pipeline failed.

Publishing no longer depends on one cron firing. `.github/scripts/plan.sh` now reads the live `edition.json` on every scheduled run. Once it is past 06:30 in Stockholm and the live front page was generated before today's 06:30, the run publishes. Otherwise a morning run skips and a collect run collects.

- The morning cron fires every 20 minutes from 04:10 to 09:50 UTC, which covers 06:30 local in winter and summer time. Skipped runs take a few seconds of runner time, which is free for a public repo.
- The 2-hourly collect run is the backstop: if every morning trigger is dropped, the first collect run after 06:30 publishes instead.
- If the live page can't be read, a scheduled run doesn't publish blind.
- The publish time is read from `config/settings.yaml` (`schedule.publish_at`).
- Concurrency queues overlapping runs; the queued run then sees today's edition and skips.
- `tests/test_plan.py` covers the cases.
