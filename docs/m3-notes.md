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

## First live run (2026-11-24)

Three passes over the same backlog, about 1,000 news items, 380 ambiguous relevance checks and 10 story summaries. Total: **$0.33**, of which about $0.13 was the first pass and the rest was re-labeling after prompt changes.

| | v1 | v2 | v3 (current) |
|---|---|---|---|
| Low-confidence labels | 27% | 35% | **10%** |
| Evidence phrases rejected | 142 | 295 | **23** |

What changed:
- **v2**:
  - Technical items have no neutral frame in the brief, so the model's "neutral" failed the check (all 78 frame failures were technical). The prompt now says plain technical reporting is "grounded", and a leftover technical "neutral" is mapped to grounded (recorded as `frame_repaired`).
  - Evidence matching now ignores punctuation (curly quotes, ellipses).
  - Rejected phrases are stored for auditing.
  - Relevance v2: "AI companies (including Nvidia), their leaders and staff". v1 had called "Huang had contact with Chinese intelligence" not AI.
  - Summary v2: headlines at most 18 words; coverage is null when no outlet covered the story.
- **v3**: v2's "never shorten inside the phrase" made the model copy whole clauses, and 282 of 295 rejections were real quotes over 12 words. The prompt now asks for 3 to 12 consecutive words. As a backstop, a real quote that is too long is cut to its first 12 words with "…" (127 cut) instead of discarded.
- Summaries sent to the model are cut at a word boundary. Half-words like "tigh" were being quoted and then failing the match.

Label mix (v3): track economic 511, political 330, technical 186. Stance −2: 114, −1: 304, 0: 394, +1: 189, +2: 26. The day is dominated by the Nvidia scandal and a market sell-off, so negative stances lead.

Bias-audit preview (mean stance of confident labels, by seed-list group): US left −1.04, UK/EU −0.43, tech trade −0.44, US mainstream −0.26, US right −0.22, Nordics −0.11, Asia/Middle East +0.06. The low-confidence share is now similar across groups (6–18%; US right was 48% under v1). This is one day of data and not yet checked against a hand-labeled gold set (M6).

Cost check: the monthly pace shown by `qa costs` ($9.81) is inflated by the three re-label passes; steady state should stay near the M0 estimate (~$20/month at 12 runs a day).
