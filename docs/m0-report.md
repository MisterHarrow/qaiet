# quiet-ai: Milestone 0 report

Verified 2026-11-24 in two rounds. Round 2 dropped X and anything paid, and widened the search to aggregators, newsletters, lab blogs and more builder sources. No product code yet. Draft configs: `config/sources.yaml`, `config/accounts.yaml`.

## Summary

- **Everything in the plan is free to fetch.** No source needs an account or payment. The only running cost is the Anthropic API (about $20/month, §6).
- **X is out.** Bluesky is the only social network. To make up for that, the plan adds the AINews daily recap (it summarizes AI X, Reddit and Discord) and Hugging Face Posts, where builders announce releases.
- **111 feeds verified**, all fetched, parsed and allowed by robots.txt today:
  - 62 news outlets (52 from round 1, 10 added);
  - 2 aggregators (Techmeme, Memeorandum);
  - 28 newsletters and blogs (8 digests, 20 commentary). The Batch has no feed and is read from its sitemap;
  - 11 lab blogs;
  - Product Hunt AI.
- **Builder sources:** GitHub search, Hugging Face (trending, daily papers, Posts), Hacker News, Bluesky, and OpenRouter's model list all work without keys.
- **Dropped: 19.** Some have no working feed, some block bots in robots.txt. Google News RSS would have filled the Reuters/AP/CNN gap but disallows all bots.
- **The state-aligned category is still empty.** GDELT (free, global, includes Xinhua and China Daily) would fill it but rate-limited every request from this machine. It gets retested from GitHub Actions in M1.
- **New finding:** The Atlantic sets `Content-Signal: ai-input=no`. The plan lists its headlines but never sends them to the LLM.

## 1. Builder sources

| Source | Endpoint | Result | Notes |
|---|---|---|---|
| GitHub search | `api.github.com/search/repositories?q=...created:>DATE&sort=stars` | Works, no auth | 10 search req/min without a token, 30/min with `GITHUB_TOKEN` (free in Actions). Star velocity comes from our own snapshots. |
| GitHub trending page | `github.com/trending` | **Skip** | robots.txt allows it, but GitHub's Acceptable Use Policy only allows scraping for research or archiving. The unofficial "trending APIs" all scrape this page. |
| OSS Insight trending | `api.ossinsight.io/v1/trends/repos` | **Dead** | Its own API says the ranking has been unavailable since 2026-03-01 (event capture fell to ~0.3%). |
| HF trending models / datasets / spaces | `huggingface.co/api/{models,datasets,spaces}?sort=trendingScore` | Works, no auth | Use this. |
| HF daily papers | `huggingface.co/api/daily_papers?date=YYYY-MM-DD` | Works | Includes upvotes and linked GitHub repo. Papers with Code now redirects here. |
| **HF Posts** (new) | `huggingface.co/api/posts?sort=trending` | Works, no auth | Builders announcing releases (e.g. Unsloth, model authors) with reaction counts. Closest free equivalent to builder X. |
| **OpenRouter models** (new) | `openrouter.ai/api/v1/models` | Works, no key | 473 models with creation dates. A new entry means "this model is now usable via API". OpenRouter's usage rankings have no API, so skip them. |
| **Product Hunt AI** (new) | `producthunt.com/feed?category=artificial-intelligence` | Works | Consumer and indie launches. Lower signal; one item per launch. |
| HN Algolia | `hn.algolia.com/api/v1/search?tags=story&numericFilters=...` | Works | URL-encode `numericFilters`. `tags=show_hn` gives Show HN launches. |
| Bluesky author feeds | `public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed` | Works, no auth | The curated list (§3). |
| Bluesky search | `api.bsky.app/xrpc/app.bsky.feed.searchPosts` | Works, no auth (today) | 403 on `public.api.bsky.app`. Fragile; optional. |
| Bluesky starter packs (new) | `app.bsky.graph.searchStarterPacks`, `getList` | Works, no auth | For finding accounts, not for polling. See §3. |
| npm / PyPI download stats (new) | `api.npmjs.org/downloads`, `pypistats.org/api` | Works, no key | Weekly adoption of SDKs and frameworks. Nice for later, not v1. |
| arXiv | `rss.arxiv.org/rss/cs.AI` | Works | Leave out of v1; HF daily papers covers it. |

Tried and rejected: sigmoid.social and other Mastodon timelines (work without auth, but mostly noise) and Lobsters (robots.txt blocks bots and sets `ai-input=no`).

## 2. News outlets: 62

Items/24h counts everything in the feed over the last 24 hours, not only AI. AI share is the fraction of the current feed matching a simple AI keyword list. Measured on a heavy AI news day (Jensen Huang's return to Nvidia), so AI shares run high.

### Round 1: 52 outlets from the brief's seed list

| Outlet | Country | Lang | Type | Feeds | Items/24h | AI share |
|---|---|---|---|---|---|---|
| The New York Times | US | en | mainstream | `rss.nytimes.com/services/xml/rss/nyt/Technology.xml` | 13 | 80% |
| The Washington Post | US | en | mainstream | `feeds.washingtonpost.com/rss/business/technology` | 4 | 62% |
| The Wall Street Journal | US | en | business | `feeds.content.dowjones.io/public/rss/RSSWSJD` | 21 | 68% |
| Bloomberg | US | en | business | `feeds.bloomberg.com/technology/news.rss` | 20 | 90% |
| CNBC | US | en | business | `www.cnbc.com/id/19854910/device/rss/rss.html` | 23 | 67% |
| NPR | US | en | public-broadcaster | `feeds.npr.org/1019/rss.xml` | 1 | 100% |
| Politico | US | en | mainstream | `rss.politico.com/technology.xml` | 4 | 83% |
| Semafor | US | en | mainstream | `www.semafor.com/rss.xml` | 31 | 39% |
| The Hill | US | en | mainstream | `thehill.com/policy/technology/feed/` | 15 | 73% |
| Fortune | US | en | business | `fortune.com/feed/` | 10 | 100% |
| Business Insider | US | en | business | `feeds.businessinsider.com/custom/all` | 20 | 55% |
| The Atlantic | US | en | opinion | `www.theatlantic.com/feed/channel/technology/` | 2 | 36% |
| Vox | US | en | opinion | `www.vox.com/rss/technology/index.xml` | 1 | 70% |
| Slate | US | en | opinion | `slate.com/feeds/technology.rss` | 1 | 24% |
| The New Republic | US | en | opinion | `newrepublic.com/rss.xml` | 22 | 15% |
| The Nation | US | en | opinion | `www.thenation.com/subject/technology/feed/` | 1 | 62% |
| Fox News | US | en | mainstream | `moxie.foxnews.com/google-publisher/tech.xml` | 2 | 44% |
| New York Post | US | en | mainstream | `nypost.com/tech/feed/` | 3 | 70% |
| Washington Examiner | US | en | mainstream | `www.washingtonexaminer.com/tag/technology/feed/` | 4 | 80% |
| National Review | US | en | opinion | `www.nationalreview.com/feed/` | 7 | 5% |
| The Free Press | US | en | opinion | `www.thefp.com/feed` | 8 | 35% |
| Reason | US | en | opinion | `reason.com/feed/` | 25 | 2% |
| Breitbart | US | en | mainstream | `www.breitbart.com/tech/feed/` | 49 | 28% |
| Daily Caller | US | en | mainstream | `dailycaller.com/feed/` | 24 | 20% |
| The Verge | US | en | trade | `www.theverge.com/rss/ai-artificial-intelligence/index.xml` | 10 | 90% |
| TechCrunch | US | en | trade | `techcrunch.com/category/artificial-intelligence/feed/` | 13 | 90% |
| Wired | US | en | trade | `www.wired.com/feed/tag/ai/latest/rss` | 6 | 80% |
| Ars Technica | US | en | trade | `arstechnica.com/ai/feed/` | 3 | 90% |
| MIT Technology Review | US | en | trade | `www.technologyreview.com/topic/artificial-intelligence/feed` | 1 | 90% |
| IEEE Spectrum | US | en | trade | `spectrum.ieee.org/feeds/topic/artificial-intelligence.rss` | n/a | 63% |
| 404 Media | US | en | trade | `www.404media.co/rss/` | 4 | 47% |
| BBC News | GB | en | public-broadcaster | `feeds.bbci.co.uk/news/technology/rss.xml` | 5 | 52% |
| The Guardian | GB | en | mainstream | `www.theguardian.com/technology/artificialintelligenceai/rss`<br>`www.theguardian.com/us/technology/rss` | 21 | 90% |
| Financial Times | GB | en | business | `www.ft.com/artificial-intelligence?format=rss` | 9 | 84% |
| The Economist | GB | en | business | `www.economist.com/business/rss.xml`<br>`www.economist.com/science-and-technology/rss.xml` | 3 | 26% |
| The Telegraph | GB | en | mainstream | `www.telegraph.co.uk/business/rss.xml` | 1 | 7% |
| Politico Europe | BE | en | mainstream | `www.politico.eu/section/technology/feed/` | n/a | 26% |
| Le Monde | FR | fr | mainstream | `www.lemonde.fr/intelligence-artificielle/rss_full.xml` | 3 | 95% |
| Der Spiegel | DE | de | mainstream | `www.spiegel.de/thema/kuenstliche_intelligenz/index.rss` | 1 | 90% |
| Handelsblatt | DE | de | business | `www.handelsblatt.com/contentexport/feed/technologie` | 17 | 80% |
| El País | ES | es | mainstream | `feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/tecnologia/portada` | 1 | 23% |
| Dagens Nyheter | SE | sv | mainstream | `www.dn.se/rss/`<br>`www.dn.se/rss/ekonomi/` | 70 | 34% |
| Svenska Dagbladet | SE | sv | mainstream | `www.svd.se/feed/articles.rss` | 42 | 12% |
| SVT Nyheter | SE | sv | public-broadcaster | `www.svt.se/nyheter/rss.xml`<br>`www.svt.se/nyheter/ekonomi/rss.xml` | 36 | 19% |
| Breakit | SE | sv | trade | `www.breakit.se/feed/artiklar` | 10 | 50% |
| Ny Teknik | SE | sv | trade | `www.nyteknik.se/digitalisering?lab_viewport=rss` | 1 | 64% |
| South China Morning Post | HK | en | mainstream | `www.scmp.com/rss/320663/feed` | 5 | 92% |
| Nikkei Asia | JP | en | business | `asia.nikkei.com/rss/feed/nar` | n/a | 22% |
| The Straits Times | SG | en | mainstream | `www.straitstimes.com/news/business/rss.xml` | 24 | 24% |
| The Economic Times | IN | en | business | `economictimes.indiatimes.com/tech/rssfeeds/13357270.cms` | 8 | 72% |
| The Korea Herald | KR | en | mainstream | `www.koreaherald.com/rss/newsAll` | 50 | 16% |
| Al Jazeera | QA | en | mainstream | `www.aljazeera.com/xml/rss/all.xml` | 25 | 16% |

### Round 2: 10 outlets added

They fill gaps in country coverage (Canada, Australia, China tech, global south) and add public broadcasters.

| Outlet | Country | Lang | Type | Feed | Why |
|---|---|---|---|---|---|
| Rest of World | US | en | trade | `restofworld.org/feed/latest/` | Tech outside the US and Europe. 92% AI share. |
| Sifted | GB | en | trade | `sifted.eu/feed` | European startups and funding (Economic track). |
| Deutsche Welle | DE | en | public-broadcaster | `rss.dw.com/rdf/rss-en-all` | German public broadcaster, English. |
| France 24 | FR | en | public-broadcaster | `www.france24.com/en/rss` | French public broadcaster, English. |
| heise online | DE | de | trade | `www.heise.de/rss/heise-atom.xml` | Largest German tech outlet. |
| Dagens industri | SE | sv | business | `www.di.se/rss` | Swedish business daily. |
| TechNode | CN | en | trade | `technode.com/feed/` | China tech, privately owned. Feed returns ~2000 items, so conditional GET matters. |
| Pandaily | CN | en | trade | `pandaily.com/feed/` | China tech, privately owned. |
| CBC | CA | en | public-broadcaster | `www.cbc.ca/webfeed/rss/rss-technology` | Canada. |
| ABC News (Australia) | AU | en | public-broadcaster | `www.abc.net.au/news/feed/51120/rss.xml` | Australia. All-news feed. |

Notes:
- About 20 outlets have no tech/AI-specific feed, so we read an all-news or business feed and the keyword prefilter does the work.
- **Guardian US merged into The Guardian.** Same newsroom; counting it twice would double its weight.
- **The Atlantic** sets `Content-Signal: ai-input=no` in robots.txt (Cloudflare's content-signal standard). Classifying a headline with an LLM is "AI input", so it is marked `llm: false`: its headlines count as coverage and are listed, but get no stance label. Five other sources set content signals, all allowing AI input.
- Nikkei Asia items carry no dates. Use first-seen time.
- `type` and `group` are for the bias audit only, never displayed.
- Volume: ~900 items/day across all news feeds, roughly 300 AI-relevant after the prefilter.

## 3. Aggregators, newsletters, lab blogs (new in round 2)

These are three new source kinds, each used differently. None is counted as "an outlet covering the story".

**Aggregators: momentum signal.** Techmeme (tech) and Memeorandum (US politics) are human-edited and pick the lead story and lead outlet. "Techmeme led with this" is a strong ranking feature. Their feeds carry only the lead headline. The "More:" lists of other outlets are on the web page, which we don't scrape.

**Newsletters: two roles.**
- *Digests* (8): AINews, TLDR AI, The Rundown AI, Last Week in AI, Ben's Bites, Import AI, MarkTechPost, The Batch (added at your request; it has no RSS, so new article URLs come from deeplearning.ai's sitemap and the title and summary from each page's metadata). "Picked up by N digests" is a momentum signal; no stance labels. **AINews** matters most: it is a daily recap of AI X, Reddit and Discord, so it carries some of the X signal we no longer fetch. It now lives in the Latent Space feed; keep items titled `[AINews]`.
- *Commentary* (20): Simon Willison, Interconnects, Ahead of AI, One Useful Thing, Understanding AI, AI as Normal Technology, Transformer, Hyperdimensional, Zvi, Marcus on AI, Where's Your Ed At, Blood in the Machine, Platformer, Exponential View, SemiAnalysis, ChinAI, ChinaTalk, Pragmatic Engineer, Dwarkesh, Epoch AI. These have strong framing, so they get the same labels as news. They are shown as a separate "Commentary" row under a story, not mixed into press coverage. The list spans boosters, skeptics, safety, policy (both directions), China and economics.

**Lab blogs: primary source.** OpenAI, Google DeepMind, Google AI, Google Research, Microsoft Research, NVIDIA, Hugging Face, Ai2, AWS ML, Apple ML, Mistral. Attached to a story as "official announcement". No stance labels; it's PR. Anthropic and Meta AI have no RSS; their news arrives through press and HN.

## 4. Dropped: 19

| Source | Reason |
|---|---|
| CNN | Every CNN RSS feed is frozen (newest items 2018/2019). |
| VentureBeat | Returns 429 to any non-browser client (Vercel bot protection). |
| Caixin Global | Feed endpoint returns 406. |
| China Daily | All documented RSS URLs return 404. |
| Global Times | Only feed found stopped updating ~45 days ago. |
| Xinhua | Official English RSS feeds stopped in 2017/2018. |
| Axios | robots.txt on the feed host disallows all generic bots. |
| Fox Business | robots.txt disallows the working feeds; allowed ones return 400. |
| The Register | robots.txt disallows the whole site for generic bots. |
| Euractiv | robots.txt disallows `/feed/`. |
| Computer Sweden | robots.txt disallows `/feed/`. |
| Google News RSS | robots.txt disallows everything. Would have covered Reuters, AP and CNN. |
| The Decoder | robots.txt disallows `*/feed/`. |
| Lobsters | robots.txt disallows generic bots; `ai-input=no`. |
| CBC | Worked in round 1; since 2026-11-24 cbc.ca drops connections from our client. Disabled. |
| Anthropic, Meta AI blogs | No RSS. |
| Qwen blog | Feed stopped in 2025. |
| KrASIA | Feed returns 404. |
| Tech Policy Press | Feed returns no items. |

**Retest in M1: GDELT DOC API** (`api.gdeltproject.org/api/v2/doc/doc`). It's free, keyless, and indexes world news in 65 languages with source country and language. It includes Reuters, AP, CNN, Xinhua, China Daily and Global Times, so it would close both gaps above (headline + URL + date only). Every request from this machine got 429, even one per minute; their limit is one request per 5 seconds. If it works from GitHub Actions at one query per run, it goes in. If not, the state-aligned category stays empty and the methodology page says so.

## 5. Social accounts (Bluesky only)

`config/accounts.yaml` has 94 Bluesky accounts, each resolved through the AppView with name and bio checked by hand. **51 are active** (posted in the last 90 days), and only those are polled. 16 search hits were rejected as wrong people, mirror bots or empty profiles.

The active set leans toward critics and policy people: 14 skeptics, 14 policy, 8 researchers, 5 journalists, 4 labs, 4 economists, **2 builders**. Labs and open-source builders mostly post on X. That's acceptable because builder signal comes mainly from GitHub, HF (now including Posts), HN and AINews, but the Bluesky lens should be read as "commentary", not "builders".

**Expanding the list:** Bluesky starter packs are public lists. 97 AI/ML starter packs contain 3,301 accounts. Of those, 203 appear in at least two packs, have 1,000+ followers and posted in the last 30 days. That pool has more builders (e.g. Armin Ronacher, Vicki Boykis, Peter Wang) but also outlets and general-politics accounts. I can turn it into a reviewed shortlist in M1 if you want.

## 6. Stack and persistence

Brief defaults kept: Python 3.12, uv, Typer, httpx, feedparser, pydantic, SQLite, scikit-learn, Jinja2, pytest, Anthropic API with model names in config.

Proposed changes:

1. **Own repository, `MisterHarrow/quiet-ai`, public.** The b3njamin monorepo holds hand-written static pages with no build step (Speedread moved out for the same reason). Public means unlimited free Actions minutes (a private repo gets 2,000 min/month; 12 runs/day × ~4 min ≈ 1,450) and free Pages.
2. **`fastembed` instead of `sentence-transformers`.** Same model (`BAAI/bge-small-en-v1.5`) on ONNX Runtime, no PyTorch. Tens of MB instead of ~1 GB on a cold CI runner every 2h.
3. **Translate before embedding.** bge-small is English-only. Non-English headlines (about a quarter of fetched items) get their English translation in the relevance pass, which display needs anyway. The English text is what gets embedded.
4. **Structured outputs instead of forced tool use.** `claude-sonnet-5-5` rejects forced `tool_choice` with a 400. Use `output_config.format` (`client.messages.parse()` with pydantic) on both models.
5. **Persistence: SQLite as a GitHub Release asset, daily editions committed as JSON.**
   - Each run downloads `quiet-ai.db` from a fixed `db` release and uploads it back with `--clobber`. A `concurrency` group stops runs overlapping. A dated snapshot is kept daily, 14 retained.
   - At the daily freeze, the edition is written to `editions/YYYY-MM-DD.json` and committed, so the archive is readable text in git. The daily commit also keeps the scheduled workflow alive: GitHub disables schedules in public repos after 60 days without activity.
   - Rejected: the DB on a `data` branch (a binary blob 12×/day bloats the repo) and Actions cache (evicted after 7 days, not guaranteed).
   - Embeddings are kept only for the 72h window plus story centroids, so the DB stays small.
   - The DB is public as a release asset. It holds only what the site shows.
6. **Hosting: GitHub Pages** via `actions/deploy-pages`. Free, no second account.

## 7. LLM cost estimate

Prices: Haiku 5.5 $0.10 in / $0.50 out per MTok. Sonnet 5.5 $2 / $10. Shared system prompts cached. Items are cached by content hash, so each is classified once however often its feed is polled.

| Step | Model | Volume/day | Tokens/day (in / out) | $/day |
|---|---|---|---|---|
| Relevance + translation | Haiku | ~450 items | 54k / 18k | 0.01 |
| News + commentary labels | Haiku | ~300 items | 60k / 75k | 0.04 |
| Builder what/why/kind | Haiku | ~200 items | 30k / 20k | 0.01 |
| Story summaries (re-run only when a story gains ≥3 items or a new outlet) | Sonnet | ~30 | 150k / 24k | 0.54 |
| Weather report | Sonnet | 12 | 24k / 4k | 0.09 |
| **Total** | | | | **≈0.70/day ≈ $21/month** |

Round 2 adds almost nothing: the new sources mostly go through cheap Haiku calls. Worst case, re-summarizing all 10 top stories every 2h, is ~$70/month. **Proposed cap: $30/month.** When it's hit, LLM steps are skipped, the site renders with existing labels, and the page says so.

This is the one paid part of the system. A zero-cost alternative would be a local model, which a free GitHub runner can't run well. I'd keep the API.

## 8. Corrections to the brief

- GitHub trending: no API, and scraping it isn't allowed for this use. Skipped; OSS Insight's alternative is dead.
- Bluesky `searchPosts` is 403 on `public.api.bsky.app`; works on `api.bsky.app` for now.
- Forced tool use → structured outputs (§6.4). `sentence-transformers` → `fastembed` (§6.2).
- X removed entirely (your call, round 2).
- Not verified (out of scope): the Reddit dates in §3.3, and Reuters/AP (left out without testing, per the brief).

## 9. Decisions needed

| # | Decision | Recommendation |
|---|---|---|
| 1 | Name and domain | Keep `quiet-ai` as the repo name. A b3njamin.ai subdomain such as `quiet.b3njamin.ai`, set up in M5. Your call on the public name. |
| 2 | Repo | New public repo `MisterHarrow/quiet-ai`. |
| 3 | Hosting | GitHub Pages. |
| 4 | Monthly LLM budget cap | $30 (expected ~$21). |
| 5 | Update frequency, edition cutoff | Every 2h. Freeze at 00:00 Europe/Stockholm. |
| 6 | robots.txt and content signals | Strict: drop what robots.txt disallows, honor `ai-input=no` with `llm: false`. |
| 7 | State-aligned outlets | Retest GDELT in M1; if it doesn't work, accept the gap and say so on the methodology page. |
| 8 | Sources | Approve `sources.yaml`: 62 outlets (CBC disabled), 2 aggregators, 28 newsletters, 11 lab blogs, Product Hunt. |
| 9 | Accounts | Approve the 51 active Bluesky accounts. Say if you want the starter-pack shortlist in M1. |
