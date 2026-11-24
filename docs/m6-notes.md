# M6 notes: the gap, the sentiment index, checking the labels

## The gap

A front-page section in every view, under the story cards: two short lists (at most 5 each) of where builders and the press look at different things. `pipeline/gap.py`, settings under `gap:`.

- **Builders are talking, press isn't:** at most 1 outlet, a builder signal in the top 15% of the view (the strongest of Hacker News points, GitHub stars per day, Hugging Face trending), *and* real volume behind it (80+ points, 150+ stars a day or trending 60+). The volume floor matters: a percentile alone put tiny repos on the list on quiet days. Bluesky alone doesn't qualify; a single viral post came up as "builders" in the first try.
- **Press is talking, builders aren't:** 5+ outlets and a builder signal in the bottom 25%.

First real run (24 hours): Inkling-2-Mini, dsh-our-free-model, fast-anything, rust-anything on one side; Megaspeed (15 outlets), the Grok lawsuits (7), the Riemann proof (5) and the OpenAI recordings (5) on the other.

## Sentiment index

`pipeline/sentiment.py`, table `sentiment_daily` (schema v5), computed after labeling in every publish run (last 3 days recomputed, so late labels count).

- Per Stockholm day and track (all / technical / political / economic).
- **Outlet-balanced:** each outlet's labels are averaged first, then outlets, so a site with 30 AI stories a day is one voice.
- **Confidence-weighted:** high 1.0, medium 0.7, low (shown as "unclear") left out.
- A value needs 3+ outlets that day.
- Days before collection started are excluded: the first feeds' backlog covered 22 and 23 November only partially (a handful of outlets each) and made the line start with a misleading dip.

Shown in the masthead of each view (average over the view's days, with the words critical / leaning critical / neutral / leaning positive / positive at ±0.15 and ±0.5) and on a new page, `/sentiment/`:

- a quotable headline value and sentence;
- one small line chart per track (fixed −1..+1 scale shared by all four, zero line, values on hover, last value labeled);
- a table of every day.

Built as plain inline SVG, no chart library, no requests to other sites. "Index" is in the navigation on every page.

## Checking the labels

`src/quiet_ai/evaluate.py`, `qa eval`.

- `qa eval sample` wrote `tests/gold/labels.yaml`: 50 articles, stratified across track × stance direction (so rare cells like positive political coverage appear), one per outlet per cell, no publisher that opts out of AI processing. Blind: the model's labels are not in the file.
- `qa eval score` reports agreement per field: track, frame (where the tracks match), stance exact and within one step, mean absolute error, and stance agreement by the model's confidence.
- `qa eval audit --by group|type|country` shows mean stance, share critical / positive and share unclear per outlet group.

**To do (Benjamin):** fill in `track`, `frame` and `stance` for the 50 items in `tests/gold/labels.yaml`, from the headline and summary alone, then `uv run qa pull` and `uv run qa eval score`. Once the file is committed, the /about page shows the agreement numbers in place of the "being labeled" note.

### Cross-check with Claude Opus 5.5

`qa eval crosscheck` has Claude Opus 5.5 label the same 50 articles through the site's own prompt (`news_label_v3`) and the same input the Haiku labeler sees (headline, English translation, summary). Opus 5.5 always thinks; effort is medium. Low-confidence Opus stances count as blank, the way a person would leave them. The labels are in `tests/gold/labels-claude-opus-5-5.yaml`. Cost: 5 calls, $0.16.

| Field | Site agrees with Opus | n |
|---|---|---|
| Angle | 90% | 50 |
| Frame (same angle) | 64% | 45 |
| Stance, exact | 65% | 48 |
| Stance, within one step | 96% | 48 |

- **Mean absolute stance difference** is 0.40. **Net bias** is +0.02: the site's labels are neither more critical nor more positive than Opus's overall. By group, no direction stands out (all within ±0.17 except one US left-leaning article).
- **Two big stance disagreements:**
  - DN, "Ökända hackare hotar läcka Nvidias hemligheter": the site says −2, Opus 0 (plain reporting). Opus is right.
  - Vox, "The US helped the world rein in nuclear weapons. Could it do the same for AI?": the site says +1, Opus −1 (argues for constraints). Opus reads the stance definition more closely. This one is the "US left-leaning +2.00" in the per-group line, so if anything the site read the left-leaning outlet as more positive, not less.
- **Angle disagreements** are borderline cases: data-center emissions (technical vs economic), Jensen Huang's exit and China's supply chain (economic vs political).
- **Frame** is the weakest field. The frames are fine distinctions, and the cards show them only on hover.

What this says: Haiku's labels hold up against a much larger model, and there is no lean *between* them. What it can't say: whether both share a lean (same family, same prompt). Only the hand labels in `labels.yaml` can answer that, and they are still blank. /about shows the cross-check and says so.

### Bias audit, first look (989 labels)

| Group | Mean stance | Critical | Positive |
|---|---|---|---|
| US left-leaning and opinion | −1.04 | 77% | 8% |
| UK and Europe | −0.43 | 50% | 18% |
| Tech trade press | −0.42 | 44% | 18% |
| US mainstream and business | −0.28 | 40% | 19% |
| US right-leaning | −0.19 | 46% | 32% |
| Nordics | −0.07 | 33% | 29% |
| Asia and the Middle East | +0.05 | 24% | 28% |

By type: opinion −1.00, public broadcasters −0.46, mainstream −0.27, business −0.21, trade −0.18.

The ordering is plausible (opinion sections are the most critical, Asian and Middle Eastern outlets the most neutral), so nothing here looks like classifier skew yet. Only the hand labels can separate real editorial differences from the model's own lean; the /about page says so next to the table. US left-leaning has only 31 labels so far.

## Also

- `qa pull` downloads the live database from the release, so local work starts from production data.
- /about has new sections: Checking the labels (with the audit table), The gap and Sentiment index, plus their entries in the contents.
