# M3 notes: labels, momentum, summaries, costs

## Item labels (Haiku 5.5, `pipeline/classify.py`)

**News and commentary** (`news_label_v1`): track, optional second track, frame (from that track's list), stance −2…+2, one or two evidence phrases, a one-sentence rationale, confidence, entities. Labeled: relevant news items, plus commentary newsletters. Digests are skipped: they summarize others, so a stance label would mean little.

- **No outlet names in the prompt.** The model sees headline and summary only, so its label is about the words, not the publisher's reputation. This also keeps the bias audit honest (M6).
- **Evidence is checked in code.** A phrase survives only if it appears in the item's own headline or summary (normalized for case, curly quotes and dashes) and is at most 12 words. If none survive, or the frame doesn't belong to the track, the label drops to low confidence, which the site shows as "unclear", never as a confident tag.
- **Publishers that opted out of AI input** (`llm: false`, currently The Atlantic) are never sent. Their headlines appear in coverage as "not labeled".
- Cached by content hash and prompt version, and stored with the prompt version that produced it. Changing a prompt file means saving it under a new version name.
- Thinking is off and effort is low. Batches of 20.

**Builder items** (`builder_label_v1`): what it is, why it matters, kind (model, tool/library, agent, infra, dataset, research paper, demo/app). Only for the Rising list and builder items attached to the top stories, not for every trending repo.

## Momentum (`pipeline/momentum.py`)

Per story, over the 72h window:

| Feature | Weight | Scaling |
|---|---|---|
| distinct news outlets | 0.25 | log share of the window's maximum |
| distinct outlet countries | 0.10 | log share |
| led on Techmeme / Memeorandum | 0.10 | log share |
| picked up by AI digests | 0.10 | log share |
| Hacker News points | 0.15 | percentile rank |
| GitHub star velocity | 0.10 | percentile rank |
| HF trending score + paper upvotes | 0.10 | percentile rank |
| Bluesky / HF posts + likes and reposts | 0.10 | percentile rank |

Then halved every 36 hours since the story's latest item.

Why two scalings: first try was percentile ranks for everything. That flattened outlet counts (2 outlets ranked 0.8, 14 outlets 0.99), and a 2-outlet story beat the 14-outlet Megaspeed story. Counts are now log-scaled. Percentile ranks stay for platform volumes, so 4,000 HN points can't drown everything else. Half-life went from 24 h to 36 h for the same reason: yesterday afternoon's big story should still beat this morning's small one.

**Star velocity** comes from metric snapshots across runs, once there are 6+ hours of them in the last 48h. Before that it's the lifetime average (stars ÷ days since creation). Shorter spans extrapolated noise.

**Rising**: builder items seen in a listing in the last 48h, scored within their kind (stars/day, HF trending, paper upvotes), with a quota per kind (4 repos, 2 models, 1 space, 1 dataset, 2 papers).

## Clustering change: a name gate

Looking at the first ranked list showed a 12-item "story" mixing "The Outages Are Just Getting Started", "AI adoption grows in Asia" and a Guardian column. Generic AI headlines sit around 0.6 similarity to each other. Joins between 0.62 and 0.72 now also need a shared name: a company, person or place from a fixed list, a versioned model name, a capitalized word in a sentence-case headline, or an entity from the item's Haiku label. Re-clustering the live data removed that blob and a 36-item "AI economy" blob, and left the real stories unchanged.

## Story summaries and weather (Sonnet 5.5, `pipeline/summarize.py`)

- Top 10 stories only. A story is summarized again only after 3+ new items or a new outlet.
- Output: a neutral one-line headline (replaces the representative headline), track, a 1–2 sentence coverage split, a builder sentence.
- Sonnet sees outlet names, countries and labels here: the point is to describe who frames it how.
- Weather report: one sentence, regenerated only when the set of top 7 stories changes.
- Server-side refusal fallback is on (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`). If Sonnet declines a request (deepfake and abuse stories are in the mix), the API retries it on a fallback model in the same call instead of failing.

## Costs and the cap

Every call is logged in `llm_calls` with tokens and cost, priced with the model actually served. Before each call, month-to-date spend is checked against `llm.monthly_budget_usd` ($30). Once it's reached, every LLM step is skipped and the run still finishes with existing labels; the edition carries `budget_reached`. `qa costs` shows spend by task and model and the month's pace.

Expected first run on today's backlog: about $0.30 (1,000 news labels about $0.12, 10 summaries about $0.12, the rest pennies). After that, about $0.70 a day.

## Not verified live

No `ANTHROPIC_API_KEY` on the dev machine, so labels, summaries and weather have only run against a fake client in the tests. They check that the right items are sent (opted-out publishers and digests aren't), the request shape (no thinking on Haiku, fallbacks on Sonnet, cached system prompt), the evidence check, caching (a second run makes no calls) and the budget stop. Prompt quality is unknown until the first real run. That's also when to label the ~50-item gold set for `qa eval` (M6).
