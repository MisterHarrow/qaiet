# M4 notes: the site

`qa build` renders the edition to `site/` (git-ignored): `index.html`, `static/style.css`, `static/app.js` (20 lines) and `edition.json`, the same data the page was built from (M5 freezes this per day). `qa serve` builds and serves it at http://localhost:8765. `qa run` builds at the end.

## Design

- **One column**, about 41rem wide, generous line height. A serif for headlines and the weather line; a sans for everything else. Both are system fonts, so the page makes **no third-party requests**: no web fonts, CDN, analytics or images. The favicon is an inline SVG. A test checks the page loads nothing from another host.
- **Palette:** paper and ink, warm grays. Stance uses umber for critical and sage for positive, each in a strong and a soft tone, with neutral gray in the middle. No red or blue. Light and dark follow the system setting.
- **Per story:**
  - a rank and track kicker;
  - the neutral one-line headline;
  - outlets and countries;
  - a 7.5rem stance bar with a few words ("split", "leans critical", "mostly neutral");
  - the coverage sentence;
  - a "Builders" line.
- **"Headlines by stance"** is a `<details>` element: no JavaScript needed. It holds one headline per outlet, grouped by stance, each with outlet, country, frame and the evidence quote. The model's rationale shows on hover.
  - Translated headlines show the English, with the original on hover.
  - Publishers that opt out of AI processing are listed as "Not labeled".
- **Highlight Technical / Political / Economic**: off by default, an overlay that dims the other stories. Hidden without JavaScript, so the page is complete without it.
- **Rising:** kind, linked name, what, why, and the signal (stars per day, trending score, upvotes).
- **Footer:** the stance legend and how ranking and labels work: "labels are machine-generated; the phrase in quotes is the evidence".
- When the monthly LLM budget is used up, a notice says labels and summaries are paused.

Checked in the browser at desktop and 375px (no horizontal scroll), light and dark.

## Revision 1 (Benjamin's review)

- **Cards, four per row.** 12 stories (three rows) as cards: 4 per row on wide screens, then 3, 2 and 1 as the screen narrows. Cards are equal height while closed. Once one is opened, rows size to their content, so the neighbours don't stretch. Long coverage sentences are clipped to six lines in the card and shown in full when the card is opened.
- **"Most mentioned" in the header.** The 16 names the most outlets mentioned in the last 24 hours, taken from the Haiku labels' entities. Each name is counted once per outlet, so one outlet repeating a name doesn't inflate it. Sized in four steps by share of the top name. Variants are merged through `site.term_aliases` (Trump / Donald Trump / Trump administration; US / United States; ...), possessives and company suffixes are dropped, and generic words and outlet names are left out. Clicking a name filters the cards to stories that mention it.
- **Track selector filters instead of highlighting.** "All / Technical / Political / Economic" with counts; non-matching cards are hidden. A track and a name combine. A "Show all" reset appears when nothing matches.
- `analysis.top_stories` and `summarize_top` went from 7/10 to 12 to fill three rows. The brief said 5–7; this is the setting to change back.

## Revision 2: Rising by category

- Rising is grouped by what each project is, from its Haiku label: Models, Agents, Tools & libraries, Infrastructure, Datasets, Papers, Apps & demos. Groups flow in three columns (one on phones), each in ranking order. Chips with counts filter to one category. Without JavaScript all groups show.
- More candidates so categories aren't thin: up to 10 repos, 5 models, 3 spaces, 3 datasets and 5 papers (26 today). All of them get a what/why label, about $0.005 per run.
- An unlabeled item falls back to its listing: repo → tool, space → app, paper → paper.

## Revision 3: time periods

- **Switcher: Last 24 hours · 7 days · 30 days · 1 year.** Each is its own static page (`/`, `/week/`, `/month/`, `/year/`), so it works without JavaScript and can be linked. All are rebuilt every run. Periods are configured in `site.periods`.
- **Everything follows the period:**
  - which stories appear, ranked only by their items inside the period;
  - "Most mentioned";
  - the weather line, one per view (`weather:<period>` reports, prompt `weather_v3`);
  - Rising, with star velocity measured over the period.
- **Longer views rank by coverage, not just "now".** Decay half-life is 36 hours for the day view, 4 days for the week, 15 days for the month and 90 days for the year.
- **Stories that come back are merged.** A story ends after 72h of silence, so a topic that returns gets a new ID. In the week, month and year views such stories are shown as one, keyed `<first id>@<period>`, when their centroids are within 0.72 and they share one of their top names. Only the 300 most active stories of a period are considered, which keeps the year view fast. Merged stories get their own summary; single stories share one summary across all views.
- **Honest about missing data.** Collection started 24 Nov 2026, and feeds carry about a day of older items. A view reaching further back says "Collecting since …, so this view covers less than … so far", and its weather line is told so ("So far today: …") instead of claiming a whole month or year.
- `qa stories --period week` prints any view in the terminal.

Not yet done, for M5: trimming old data so a year of SQLite stays small (embeddings are already kept 7 days).

## Revision 4: /about

`/about/` explains the site in plain language:
- where the news comes from (with the full outlet list behind a disclosure);
- the seven steps of a run;
- what the angle, framing and stance labels mean;
- the ranking weights, the time periods and the limits;
- privacy and the LLM budget;
- source health from the latest collection.

Every number on it (outlet and country counts, weights, model names, prompt versions, this month's spend, failing sources) is read from the config and the database at build time (`site/about.py`), so the page can't drift from what the pipeline does. This also covers most of the brief's M6 methodology page; M6 adds the bias audit and the gold-set agreement.

## Fixes found while reviewing the page

- "split" now needs 20% on each side (was 25%). The top story had 31% critical and 22% positive and read "mostly neutral" while its coverage sentence described a split.
- A story's summary said its labels were "unclear for all three", but the labels below it were clear. The summary had been written before the v3 re-label. Summaries are now refreshed when the labels under them change: a new label prompt version, or stance counts moving by 3 or more. `story_summary_v3` also tells Sonnet never to talk about the labels themselves.

## Open for Benjamin

- The public name. "quiet ai" is a placeholder wordmark.
- Whether the look is right before M5 deploys it.
