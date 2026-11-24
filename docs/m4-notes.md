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

## Fixes found while reviewing the page

- "split" now needs 20% on each side (was 25%). The top story had 31% critical and 22% positive and read "mostly neutral" while its coverage sentence described a split.
- A story's summary said its labels were "unclear for all three", but the labels below it were clear. The summary had been written before the v3 re-label. Summaries are now refreshed when the labels under them change: a new label prompt version, or stance counts moving by 3 or more. `story_summary_v3` also tells Sonnet never to talk about the labels themselves.

## Open for Benjamin

- The public name. "quiet ai" is a placeholder wordmark.
- Whether the look is right before M5 deploys it.
