# CLAUDE.md

Guidance for coding agents working in this repository.

## What this is

Qaiet Times (formerly "quiet ai"): a calm, text-first daily overview of AI, with desks for energy, biotech & health tech, space, and agriculture & food supply (2026-11-26, `docs/desks.md`). It shows how about 60 news outlets frame AI (each article labeled with an angle, a frame and a stance from −2 to +2), what builders are making (GitHub, Hugging Face, Hacker News, Bluesky), stories clustered across sources, "Rising", "The gap", narratives (stories covered several days in a row, told day by day), a sentiment index, an archive and an About page.

- Live: https://news.b3njamin.ai/ (Vercel). The old https://misterharrow.github.io/qaiet/ forwards there; https://misterharrow.github.io/quiet-ai/ stopped working when the repo was renamed on 2026-11-25.
- Repo: `MisterHarrow/qaiet` (renamed from `quiet-ai`), **public**. Everything pushed is public.
- Owner: Benjamin. History and the reasons behind decisions are in `docs/m0-report.md` … `docs/m6-notes.md` and `docs/desks.md`; the plan for covering more of the world, step by step, is `docs/global-coverage-plan.md`; commands are in `README.md`.

## Run it

```sh
uv sync
uv run qa pull         # replace data/quiet-ai.db with the live database (needed before build/serve)
uv run qa build        # render site/ from the database; no model calls
uv run qa serve        # build and preview at http://localhost:8765 (also the "quiet-ai" entry in .claude/launch.json)
uv run qa bulletin     # today's spoken bulletin by hand (the publish makes it daily); about $0.05, ask Benjamin first
uv run pytest          # must pass before every push; no network, no model calls
```

- `.env` holds `ANTHROPIC_API_KEY` and `SPEECHIFY_API_KEY` (the bulletin's voice), plus `ELEVENLABS_API_KEY` and `GEMINI_API_KEY` from the voice tests. Benjamin set them. **Never read, print or commit `.env`**, and never enter keys or tokens yourself.
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

- **Money:** agents never make budget or financial decisions; they only advise (Benjamin, 2026-11-27). Never set, raise or lower a spending cap or price (`llm.monthly_budget_usd`, `bulletin.monthly_budget_usd` and the like), never turn on a paid step or make one run more often, and never pick a paid plan or model for its cost, without Benjamin's explicit yes for that exact change. Propose the figure and the reason; Benjamin decides. A cap an agent changed without that yes is reverted.
- **Sources:** free only. No X/Twitter and nothing that needs payment from Benjamin. The Anthropic API is the only cost.
  - Never fetch x.com or reddit.com (robots.txt blocks us; Reddit API access was requested 2026-11-25 and is pending). X posts and Reddit threads appear only second-hand, from the AINews recap (`mentions: true` on a source, `pipeline/mentions.py`):
    - Links a recap bullet puts next to a story's or project's URL: only the links, account, subreddit, thread title and activity count are kept.
    - Each X bullet also becomes a `recap` item (AINews's bold lead as title, at most 500 characters of its text, the posts and other URLs in `extra`). Recap items join a story by link or similarity but never start one (`cluster.join_only_kinds`), count toward the `social` signal by number of X posts, are never labeled by a model, and don't count as items for re-summarizing.
- **Courtesy to publishers:**
  - Respect robots.txt (RFC 9309; unreachable means disallow).
  - Never work around a block (403/429): no proxies, no browser user agents.
  - Use the generic user agent only. Never put Benjamin's name, email or other personal details in requests.
  - Store only a headline and a summary of at most 500 characters.
  - `llm: false` on a source (publishers with `Content-Signal: ai-input=no`) means its text never goes to a model. Other content signals (such as `use=reference`) don't change that (Benjamin, 2026-11-26).
  - Desks (`desks:` in `settings.yaml`): an item and its story belong to one desk (`items.desk`, `stories.desk`). AI is decided by keywords first; with more than one desk, press items without an AI keyword go to Haiku (`relevance_v3` returns a desk or none). A source with `desk:` sends every item to that desk without a call; `llm: false` sources are sorted by `DESK_KEYWORDS`. Each desk has its own label prompt (stance toward that desk's subject), editions (`editions/<desk>/<date>.json`; AI stays at `editions/<date>.json`), sentiment index and narratives; desks are never averaged together. Builders (Rising, The gap) are AI only.
  - A new language needs its AI terms in the keyword lists in `pipeline/relevance.py` first (`LANGUAGES` there; non-Latin scripts go in `_STRONG_SCRIPT`), or its AI headlines are dropped before a model sees them. `index_from` on a source keeps its labels out of the sentiment index until that day; Benjamin chose no wait for new languages (2026-11-26), so no source sets it.
  - Headlines in a non-Latin script (`text.NON_LATIN`) are clustered only once they have an English title. The relevance call sometimes leaves `title_en` empty, so `relevance.translate_missing` asks for the missing ones with `translate_v1` (Haiku), every run until they have one.
  - State media and outlets close to a government get `type: state-aligned`; the About page marks them.
- **The page loads nothing from other sites:**
  - System fonts only: no web fonts, no CDNs.
  - No images, analytics, cookies or third-party scripts (inline `data:` SVGs only: the favicon and the seal's paper grain).
  - Favicons are inline `data:` SVGs.
  - `tests/test_site.py` checks this.
- **The page works without JavaScript.** `app.js` only adds the filters, the light/dark switch (hidden without JS, so the page stays light), the tabbed window that gathers open cards' sources (without JS each card's sources open under its own row), the greeting's count-up, and, on a narrative's page, the narrative seal writing out its days and then turning slowly, and the spoken bulletin's speed buttons. localStorage holds the theme choice and the bulletin's speed, sessionStorage a flag that the greeting played this visit. No cookies.
- **Model costs:**
  - The monthly cap is $30 (`llm.monthly_budget_usd`). A daily publish costs about $0.05–0.15.
  - Models: Haiku 5.5 for items, Sonnet 5.5 for story summaries, the daily line and the bulletin's script. Opus 5.5 is only for `qa eval crosscheck`; thinking can't be turned off on Opus 5.5.
  - The spoken bulletin (`pipeline/bulletin.py`, `bulletin:` in `settings.yaml`) is made once a day by the publish (`qa run`): Sonnet writes the script (about $0.04), Speechify Simba 3.5 voices it in one fixed voice, Wyatt (about $0.05, list price; Benjamin's choice on 2026-11-27 after testing ElevenLabs, Ming, Speechify and Gemini). Speech is logged in `llm_calls` as `tts_bulletin` with its own cap (`bulletin.monthly_budget_usd`), outside the LLM cap. It is never made from the page, and a failed bulletin never stops the publish. Lesson from the tests: a voice stays the same only on models with a fixed speaker (Speechify, Gemini, ElevenLabs, Kokoro); Ming-3.0-tts makes each sentence separately and changes voice between them. `tts_engine: elevenlabs` and `ming` (on the Mac, `deploy/mac/`) are still supported; switching is Benjamin's decision.
- **Prompts are versioned:**
  - To change one, add a new file (`<task>_vN.md`) and point `settings.yaml` at it; never edit a version in place.
  - A new version relabels on the next run, which costs money. Say so before doing it.
- **Hand labels:** `tests/gold/labels.yaml` (AI only so far) is for Benjamin to fill in by hand. Never fill it in with a model: it is the independent check on the model's labels. `labels-claude-opus-5-5.yaml` is generated by `qa eval crosscheck`.

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
  - A card's coverage is a list of framings (`frames` from `story_summary_v4`: a verb phrase and the outlets that frame it that way), each followed by its outlet count and country codes (at most six, then "+N", so a row never overflows at 380px); hovering, focusing or tapping the count shows those outlets' headlines (CSS only, `build.frame_rows`). Summaries written before v4 keep their prose.
  - The rule under the masthead on the front page is the stance mix of every article in that view.
  - Desks (Benjamin, 2026-11-26, draft A of two): a row of desks under the nameplate (`brand.desks`, the headline serif), each with its sentiment in its first view; AI stays the front page at `/`, the others live at `/<key>/` with their own periods, narratives, index and archive (`base` in the templates is the desk's folder). Pages and the About page say which desk; the About page lists them.
  - Masthead (Benjamin, 2026-11-26, option A of two drafts): two bands. The sentiment and the views sit beside the "Outlets and sentiment by region" box, about the same height; the day's line (`.weather`) runs across the page under both, so its length never leaves a hole. The box's legend has two columns (five regions, then four); each row ends with that region's sentiment in the view (the place filter's figure, umber or sage by sign, "–" under 3 outlets). The dot map is as tall as the legend (`--legend-h`, `build.legend_height`, which must mirror the legend's CSS). Narrower than 85rem the box gets its own row; phones keep one legend column and the small map, without the figures.
  - Every page must work at 380px wide without horizontal scrolling.
  - On phones (under 38rem) the light/dark switch sits beside the wordmark and the sentiment's three tracks sit under its figure; under 85rem the coverage box moves between the views and the day's line, and on phones the map stays small beside the legend. Small controls get an invisible `::after` pad ("Hit areas" in `style.css`) so taps reach about 44px without moving anything; give new small controls one too.
- **Charts** on `/sentiment/` and the narrative pages are hand-written inline SVG (`build.sparkline`, `build.narrative_chart`), colored from the CSS tokens. There is no chart library.
- **Narratives** (`pipeline/narratives.py`, `narratives:` in `settings.yaml`):
  - A narrative is one story ID with news or commentary (not digests) on `min_days` (4) or more Stockholm days in a row. It is "ongoing" while covered today or yesterday.
  - No model calls: each day comes from the items and labels, plus that morning's front-page line from the `editions` table. A model-written "how it evolved" summary was costed at about $0.01 per narrative per day; ask Benjamin before adding it.
  - Days before collection began (from the feeds' backlog) count, marked partial.
  - Pages: a front-page section after the story cards, `/narratives/`, and `/narratives/<story id>/`. Editions carry `narratives` (compact rows) and each story's `narrative` ({id, day, since}).
  - **The seal** (`build.seal`; Benjamin chose the engraved string circle on 2026-11-25 over ink stamps, a foil strip and a chronograph, then this "Lattice" version over a ripple and a hoop of strings): a guilloché lattice generated from the narrative. Two petals per day; the day count in the system serif in the middle of the small seals. No ring (Benjamin removed it on 2026-11-25): the lattice itself is tinted from the inside out by the stance of all the narrative's articles (`stance` in the compact narrative; `seal_bands`, `seal_stops`): critical (umber) in the middle to positive (sage) at the petal tips, unclear and unlabeled left out, each stance getting its share of the line's length (a sine lattice spends its length unevenly, so band edges sit at R0 + AMP·sin(π(c − ½))), shares under 4% raised so they show, short blends between bands like iris printing. It is one SVG radial gradient per seal (stop colors from the stance tokens), so turning the lattice never moves the colors. Older frozen editions without counts get one tint from the average. The seal has no outline, shadow, disc or hover lift of its own: on light paper it is drawn into the page like colored pencil (Benjamin: "as a pencil draws on a paper as opposed to putting a sticker on top"): `mix-blend-mode: multiply`, the stance colors deepened a quarter toward ink (`--seal-2` … `--seal2`, mirrored by `tone()` in `app.js`), and a fine paper-tooth grain as a CSS mask (an inline `data:` SVG of feTurbulence, like the favicon; nothing fetched). Dark mode keeps plain lines. Every line is a hairline (`vector-effect: non-scaling-stroke`, half a CSS pixel on high-density screens) so it stays crisp at card size.
    - It sits on the top-right corner of a front-page card in a narrative (the stripe ends where it begins, the globe steps left), in each narrative row, and large beside the headline on the narrative's page.
    - It rests still; on hover its two lattices turn a little against each other. The lattice curve is defined once per page (`seal_defs`).
    - On a narrative's page the seal rests without its count, and `app.js` plays it once (and again on hover or click) on a canvas inside the seal: the lattice (cut into 72 threads) twists into a three-strand cord, and the cord pays its thread out to a pen that writes the day count, "day", "narrative" and last a "Q" (the wordmark's Q, then the end-spin) in `--display` (Baskerville, like the wordmark; Benjamin's choice, the one place besides the wordmark that uses it). The letters are the font itself, upright (Benjamin chose it over italic and hairline-only versions), filled with the stance bands from left (critical) to right (positive) like a card's stripe (`data-bands`): each word is set on a hidden canvas at the seal's resolution; its distance field gives the outline the ink lifts into on its way back to the cord; a hand-made pen path per letter (`DUCTUS` in `app.js`, fitted to the letter and pulled onto the middle of its strokes) sets when each pixel of the fill is written (nearest point of the pen's path), with a hand's minimum-jerk pacing and pen lifts. Behind the pen the outline threads trace the letter, the letter appears as a fine diagonal hatch (one screen pixel wide), then the color fuses in between the lines, leaving the hatch as a faint grain (`FUSED`); Benjamin found a plain pen-wipe fill with dark wet ink "too 90's". Benjamin: "as if a machine was the best in the world at fine calligraphy and yet managed to make it human". Everything runs at `TS` (1/1.5: Benjamin asked twice for faster), about 8.7 s in all. The cord sits at radius 40 and every word is sized to stay inside it, so no letter touches a thread. After each word the threads wind back into the cord; after the Q the lattice spins down and locks, then keeps turning slowly (90 s a turn) via `lat-turning` in `style.css`. In the lattice and the cord the canvas threads wear the same tint (a canvas radial gradient from `data-stops`). Without JS or under `prefers-reduced-motion` it simply rests.
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
  - The Vercel project is connected to the GitHub repo (`vercel link --yes` does that), so the root `vercel.json` turns off Git deploys (`git.deploymentEnabled: false`). **Never remove it**: without it every push to `main` deploys the repo root as production and the site returns 404 (it happened on 2026-11-25).
  - A failed Vercel deploy fails the run. Fix it quickly: until today's edition is live, every scheduled run publishes again (and spends model money).
  - `qa build` writes `site/vercel.json` with `trailingSlash: true`; the relative links break without it.
  - DNS is at Namecheap: a CNAME for `news` points to Vercel. The apex b3njamin.ai is a separate Vercel project.
  - GitHub Pages only serves `deploy/pages-redirect/` (a forward to news.b3njamin.ai, keeping the path), so old links keep working.
  - `.vercel/` and `.env.local` (from `vercel link`) are git-ignored; never commit them.
- **The spoken bulletin**: the publish keeps `bulletin-<date>.mp3/.txt/.json` as `audio` release assets (30 days); every publish and deploy restores them, so the players stay and a second publish the same day doesn't voice it again. Secret: `SPEECHIFY_API_KEY`, only in the publish step. Audio never goes into git. `deploy/mac/` (a launchd job that voices the script on the Mac and starts a deploy) is only for `tts_engine: ming`.
- **Changes to the page go live on the next publish**, or right away with `gh workflow run run.yml --repo MisterHarrow/qaiet -f mode=deploy`: it rebuilds the site from the saved database with no model calls. Run it only after the morning publish (the rebuilt page carries the current time, so earlier it would stop that day's publish). Both update the public site, so ask Benjamin first; `-f mode=publish` also costs model money.
- The workflow commits `editions/*.json` to `main`. Run `git pull --rebase` before pushing.
