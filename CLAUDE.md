# CLAUDE.md

Guidance for coding agents working in this repository.

## What this is

Qaiet Times (formerly "quiet ai"): a calm, text-first daily overview of AI. It shows how about 60 news outlets frame AI (each article labeled with an angle, a frame and a stance from −2 to +2), what builders are making (GitHub, Hugging Face, Hacker News, Bluesky), stories clustered across sources, "Rising", "The gap", narratives (stories covered several days in a row, told day by day), a sentiment index, an archive and an About page.

- Live: https://news.b3njamin.ai/ (Vercel). The old https://misterharrow.github.io/qaiet/ forwards there; https://misterharrow.github.io/quiet-ai/ stopped working when the repo was renamed on 2026-11-25.
- Repo: `MisterHarrow/qaiet` (renamed from `quiet-ai`), **public**. Everything pushed is public.
- Owner: Benjamin. History and the reasons behind decisions are in `docs/m0-report.md` … `docs/m6-notes.md`; commands are in `README.md`.

## Run it

```sh
uv sync
uv run qa pull         # replace data/quiet-ai.db with the live database (needed before build/serve)
uv run qa build        # render site/ from the database; no model calls
uv run qa serve        # build and preview at http://localhost:8765 (also the "quiet-ai" entry in .claude/launch.json)
uv run pytest          # must pass before every push; no network, no model calls
```

- `.env` holds `ANTHROPIC_API_KEY`. Benjamin set it. **Never read, print or commit `.env`**, and never enter keys or tokens yourself.
- `--dry-run` on `ingest`, `cluster` and `classify` replays recorded fixtures: no network, no model calls.
- `qa run` is the full pipeline. It **calls the API and costs money**, so don't run it casually; `qa build` is enough for anything on the page.

## Layout

- `config/`
  - `settings.yaml`: every tunable, read by `src/quiet_ai/config.py`.
  - `sources.yaml`: outlets, aggregators, newsletters, labs.
  - `accounts.yaml`: Bluesky accounts.
- `src/quiet_ai/`
  - `fetchers/`: one module per source type.
  - `http.py`: the only HTTP client (robots.txt, rate limits, retries).
  - `pipeline/`: ingest, relevance, embed, cluster, classify, momentum, summarize, edition, gap, sentiment, narratives, archive. `process.py` wires them together.
  - `llm/client.py`: the Anthropic wrapper (structured outputs, cost log, budget cap). Prompts live in `llm/prompts/`.
  - `store/db.py`: SQLite with schema migrations.
  - `site/`: `build.py` renders the Jinja2 templates in `site/templates/`; `about.py` holds the About page's facts. `static/style.css` and `static/app.js` are the only assets.
  - `evaluate.py`: `qa eval`.
  - `cli.py`: the `qa` command.
- `site/`: build output, git-ignored.
- `data/`: the local database, git-ignored. The live database is the `db` release asset.
- `editions/<date>.json`: frozen daily editions, committed by the workflow.
- `tests/`: pytest. `tests/fixtures/` holds recorded HTTP; `tests/gold/` holds the label checks.

## Rules that don't bend

- **Sources:** free only. No X/Twitter and nothing that needs payment from Benjamin. The Anthropic API is the only cost.
  - Never fetch x.com or reddit.com (robots.txt blocks us; Reddit API access was requested 2026-11-25 and is pending). X posts and Reddit threads appear only second-hand, from the AINews recap (`mentions: true` on a source, `pipeline/mentions.py`):
    - Links a recap bullet puts next to a story's or project's URL: only the links, account, subreddit, thread title and activity count are kept.
    - Each X bullet also becomes a `recap` item (AINews's bold lead as title, at most 500 characters of its text, the posts and other URLs in `extra`). Recap items join a story by link or similarity but never start one (`cluster.join_only_kinds`), count toward the `social` signal by number of X posts, are never labeled by a model, and don't count as items for re-summarizing.
- **Courtesy to publishers:**
  - Respect robots.txt (RFC 9309; unreachable means disallow).
  - Never work around a block (403/429): no proxies, no browser user agents.
  - Use the generic user agent only. Never put Benjamin's name, email or other personal details in requests.
  - Store only a headline and a summary of at most 500 characters.
  - `llm: false` on a source (publishers with `Content-Signal: ai-input=no`) means its text never goes to a model.
- **The page loads nothing from other sites:**
  - System fonts only: no web fonts, no CDNs.
  - No images, analytics, cookies or third-party scripts.
  - Favicons are inline `data:` SVGs.
  - `tests/test_site.py` checks this.
- **The page works without JavaScript.** `app.js` only adds the filters, the light/dark switch (hidden without JS, so the page stays light), the tabbed window that gathers open cards' sources (without JS each card's sources open under its own row), the greeting's count-up, and, on a narrative's page, the narrative seal writing out its days and then turning slowly. localStorage holds the theme choice and sessionStorage a flag that the greeting played this visit. No cookies.
- **Model costs:**
  - The monthly cap is $30 (`llm.monthly_budget_usd`). A daily publish costs about $0.05–0.15.
  - Models: Haiku 5.5 for items, Sonnet 5.5 for story summaries and the daily line. Opus 5.5 is only for `qa eval crosscheck`; thinking can't be turned off on Opus 5.5.
- **Prompts are versioned:**
  - To change one, add a new file (`<task>_vN.md`) and point `settings.yaml` at it; never edit a version in place.
  - A new version relabels on the next run, which costs money. Say so before doing it.
- **Hand labels:** `tests/gold/labels.yaml` is for Benjamin to fill in by hand. Never fill it in with a model: it is the independent check on the model's labels. `labels-claude-opus-5-5.yaml` is generated by `qa eval crosscheck`.

## Design

- **Direction:** "a cyberpunk Financial Times that's still clean" (Benjamin, 2026-11-25). Light mode is salmon newsprint; dark mode is a soft warm graphite with the same beige undertone (not black).
- **Tokens** are CSS custom properties on `:root` in `src/quiet_ai/site/static/style.css`.
  - Light is the default, whatever the OS prefers. Dark is a second set under `:root[data-theme="dark"]`, switched by the button in the navigation (`app.js`; the choice is kept in localStorage, and an inline script in `<head>` applies it before paint). Design and check both.
  - Reuse the tokens rather than hardcoding colors.
  - Text colors (`--muted`, `--faint`) must reach 4.5:1 on `--paper` and `--card`.
- **Type:** an elegant installed serif (`--display`) for the wordmark (and the words the narrative seal writes), system serif (`--serif`) for headlines, system sans (`--sans`) for reading text, system mono (`--mono`) for data, labels, navigation.
- **Colors:**
  - Stance colors are umber (critical) and sage (positive), never red/blue: stance has nothing to do with left and right.
  - `--signal` (magenta) is the one brand color: active navigation, focus, section markers. It never encodes data.
- **Layout:**
  - Story cards are a grid of 4, then 3, 2 and 1 per row as the screen narrows. A card's top edge is its stance mix.
  - The rule under the masthead on the front page is the stance mix of every article in that view.
  - Every page must work at 380px wide without horizontal scrolling.
- **Charts** on `/sentiment/` and the narrative pages are hand-written inline SVG (`build.sparkline`, `build.narrative_chart`), colored from the CSS tokens. There is no chart library.
- **Narratives** (`pipeline/narratives.py`, `narratives:` in `settings.yaml`):
  - A narrative is one story ID with news or commentary (not digests) on `min_days` (4) or more Stockholm days in a row. It is "ongoing" while covered today or yesterday.
  - No model calls: each day comes from the items and labels, plus that morning's front-page line from the `editions` table. A model-written "how it evolved" summary was costed at about $0.01 per narrative per day; ask Benjamin before adding it.
  - Days before collection began (from the feeds' backlog) count, marked partial.
  - Pages: a front-page section after the story cards, `/narratives/`, and `/narratives/<story id>/`. Editions carry `narratives` (compact rows) and each story's `narrative` ({id, day, since}).
  - **The seal** (`build.seal`; Benjamin chose the engraved string circle on 2026-11-25 over ink stamps, a foil strip and a chronograph, then this "Lattice" version over a ripple and a hoop of strings): a guilloché lattice generated from the narrative. Two petals per day; the day count in the system serif in the middle of the small seals. No ring (Benjamin removed it on 2026-11-25): the lattice itself is tinted from the inside out by the stance of all the narrative's articles (`stance` in the compact narrative; `seal_bands`, `seal_stops`): critical (umber) in the middle to positive (sage) at the petal tips, unclear and unlabeled left out, each stance getting its share of the line's length (a sine lattice spends its length unevenly, so band edges sit at R0 + AMP·sin(π(c − ½))), shares under 4% raised so they show, short blends between bands like iris printing. It is one SVG radial gradient per seal (stop colors from the stance tokens), so turning the lattice never moves the colors. Older frozen editions without counts get one tint from the average. The seal has no outline or shadow of its own. Every line is a hairline (`vector-effect: non-scaling-stroke`, half a CSS pixel on high-density screens) so it stays crisp at card size.
    - It sits on the top-right corner of a front-page card in a narrative (the stripe ends where it begins, the globe steps left), in each narrative row, and large beside the headline on the narrative's page.
    - It rests still; on hover its two lattices turn a little against each other. The lattice curve is defined once per page (`seal_defs`).
    - On a narrative's page the seal rests without its count, and `app.js` plays it once (and again on hover or click) on a canvas inside the seal: the lattice (cut into 72 threads) twists into a three-strand cord, and the cord pays its thread out to a pen that writes the day count, "day", "narrative" and last a "Q" (the wordmark's Q, then the end-spin) in `--display` (Baskerville, like the wordmark; Benjamin's choice, the one place besides the wordmark that uses it). The letters are the font itself: each word is set on a hidden canvas, its distance field gives the outline and inlines, and a hand-made pen path per letter (`DUCTUS` in `app.js`, fitted to the letter and pulled onto the middle of its strokes) sets when each part is written, with a hand's minimum-jerk pacing, pen lifts and slightly darker wet ink. Benjamin: "as if a machine was the best in the world at fine calligraphy and yet managed to make it human". Writing is brisk (about 0.2 s a letter; Benjamin asked for faster). After each word the threads wind back into the cord; after the Q the lattice spins down and locks, then keeps turning slowly (90 s a turn) via `lat-turning` in `style.css`. In the lattice and the cord the canvas threads wear the same tint (a canvas radial gradient from `data-stops`); as letters they are ink. Without JS or under `prefers-reduced-motion` it simply rests.
- **Name, favicon and wordmark:**
  - The public name is **Qaiet Times** (no ".ai"). The repo is `qaiet`; the Python package (`quiet_ai`), the database files (`quiet-ai.db`, the `db` release assets) and the crawler's user agent keep the old name.
  - The favicon, wordmark and site navigation live once in `site/templates/_brand.html.j2`; every page imports them.
  - The mark is the stance scale as five bars, umber to sage. The wordmark is "Qaiet Times" in `--display` (Baskerville, then Baskerville Old Face on Windows, then the system serif), plain ink with no highlight.
- **Copy:** plain, specific, short sentences; calm, no hype.
- **Check changes in the browser:** run `qa serve`, then look at light and dark mode (the switch, or `document.documentElement.dataset.theme = "dark"`), a desktop width and 380px.

## Deploy

- `test.yml` runs the tests on every push.
- `run.yml` runs on a schedule:
  - **collect** every 2 hours: fetch only, no model calls.
  - **publish** from 06:30 Stockholm: the full pipeline, deploy, and committing the frozen editions.
  - GitHub drops scheduled runs, so `.github/scripts/plan.sh` publishes from any scheduled run once today's edition isn't live yet (see `docs/m5-notes.md`). It reads the live `edition.json` at `SITE_URL` in `run.yml` (news.b3njamin.ai).
- **Hosting:**
  - Vercel serves the site at news.b3njamin.ai: each publish uploads `site/` to the Vercel project `energaized/qaiet` with a pinned `vercel` CLI. Vercel never builds. Secrets: `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`.
  - A failed Vercel deploy fails the run. Fix it quickly: until today's edition is live, every scheduled run publishes again (and spends model money).
  - `qa build` writes `site/vercel.json` with `trailingSlash: true`; the relative links break without it.
  - DNS is at Namecheap: a CNAME for `news` points to Vercel. The apex b3njamin.ai is a separate Vercel project.
  - GitHub Pages only serves `deploy/pages-redirect/` (a forward to news.b3njamin.ai, keeping the path), so old links keep working.
  - `.vercel/` and `.env.local` (from `vercel link`) are git-ignored; never commit them.
- **Changes to the page go live on the next publish**, or right away with `gh workflow run run.yml --repo MisterHarrow/qaiet -f mode=deploy`: it rebuilds the site from the saved database with no model calls. Run it only after the morning publish (the rebuilt page carries the current time, so earlier it would stop that day's publish). Both update the public site, so ask Benjamin first; `-f mode=publish` also costs model money.
- The workflow commits `editions/*.json` to `main`. Run `git pull --rebase` before pushing.
