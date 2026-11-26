# Global coverage plan

Drafted 2026-11-26 for Benjamin to approve step by step. **Step 1 is approved and implemented** (24 outlets, the region split, Portuguese keywords, the `index_from` wait, the per-outlet stripe and the About page's limits); steps 2–8 are not started.

## Summary

- **Today about half of what the site reads comes from the US.** On a full day, 24–27 of the 51–54 outlets with a confident label are American. They hold 48–55% of the outlet slots in the 12 top stories. There are no outlets at all in Latin America or Africa. The Middle East and Oceania have one outlet each, so they never get a sentiment figure.
- **I checked 321 candidate feeds** in 69 countries with the project's own HTTP client and its generic user agent. 225 have a working feed that robots.txt allows. 17 are disallowed by robots.txt, 29 refuse our client (HTTP 403, left alone), 48 have no working or current feed, and 2 set `Content-Signal: ai-input=no` (Corriere della Sera, New Straits Times).
- **The pipeline is ready for Latin-script languages, not for the others.** The keyword filter marks AI headlines in Japanese, Korean, Chinese, Arabic and Hindi as "not AI" before a model ever sees them, and Portuguese, Turkish or Indonesian ones too when they spell the term out. "生成AI", "인공지능" and "inteligência artificial" all fail today. Clustering also needs the English title for non-Latin scripts: untranslated, a Japanese headline scores 0.46 against its English twin, below the 0.62 join threshold.
- **Cost is not the constraint.** Haiku costs about $0.00003 per item for relevance plus translation and $0.00008 per label (measured from `llm_calls`). All six source steps together add about $0.08 a day, or $2.30 a month. Sonnet summaries are capped by the number of top stories, not by sources: at most about $0.45 a day even in the worst case. The month would stay under $15 against the $30 cap.
- **The plan has eight steps**, each a separate yes or no. The first adds 24 outlets in Latin America and Africa in languages the pipeline already reads (Spanish, Portuguese, English). It gives both continents a daily index and cuts the US share of labeled outlets from about 49% to about 36%. Benjamin's decisions of 26 November are in section 6 and folded into the steps.

## 1. Baseline

**Data.** Live database pulled 2026-11-26 09:08 Stockholm: 7,224 items. Collection began 2026-11-24 08:23 UTC, so only 24 and 25 November are complete days (26 November runs to 08:00 UTC). The 7- and 30-day windows below are by publication date, so before 24 November they hold only the feeds' backlog (`ingest.max_age_days` is 14; most feeds carry 10–100 items). The 30-day column therefore covers 16 days and undercounts busy feeds. "Confident" means a news label with high or medium confidence, the ones the sentiment index uses. Regions are today's `REGIONS`.

### By region

| Region | Outlets configured (enabled) | Active, 7 d | Relevant AI articles, 7 d | Confident labels, 7 d | Confident labels, all (16 d) | Outlets with a confident label on 24 / 25 / 26 Nov | Share of outlet slots in the top 12 on 24 / 25 / 26 Nov |
|---|---|---|---|---|---|---|---|
| Americas | 35 (34) | 32 | 610 | 550 | 677 | 27 / 24 / 6 | 50% / 55% / 48% |
| Europe | 21 (21) | 20 | 397 | 357 | 436 | 16 / 17 / 11 | 37% / 33% / 30% |
| Middle East | 1 (1) | 1 | 11 | 10 | 10 | 1 / 1 / 1 | 2% / 2% / 4% |
| Asia | 11 (11) | 9 | 177 | 161 | 216 | 9 / 8 / 6 | 11% / 9% / 16% |
| Oceania | 1 (1) | 1 | 8 | 8 | 8 | 1 / 1 / 1 | 0% / 1% / 2% |
| **All** | 69 (68) | 63 | 1203 | 1086 | 1347 | 54 / 51 / 25 | 100% |

### By country

| Country | Region | Outlets (enabled) | Active, 7 d | Relevant, 7 d | Confident, 7 d | Confident, all | Outlets with a confident label on 24 / 25 / 26 Nov | Top-12 stories with an outlet from here, 24 / 25 / 26 Nov |
|---|---|---|---|---|---|---|---|---|
| US | Americas | 34 (34) | 32 | 610 | 550 | 677 | 27 / 24 / 6 | 10 / 12 / 11 |
| CA | Americas | 1 (0) | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| GB | Europe | 7 (7) | 6 | 135 | 122 | 138 | 4 / 5 / 2 | 7 / 10 / 5 |
| SE | Europe | 6 (6) | 6 | 88 | 75 | 109 | 5 / 6 / 2 | 5 / 5 / 4 |
| DE | Europe | 4 (4) | 4 | 116 | 109 | 132 | 4 / 4 / 4 | 5 / 5 / 7 |
| FR | Europe | 2 (2) | 2 | 49 | 44 | 44 | 2 / 2 / 2 | 3 / 3 / 3 |
| BE | Europe | 1 (1) | 1 | 5 | 3 | 8 | 1 / 0 / 0 | 0 / 0 / 0 |
| ES | Europe | 1 (1) | 1 | 4 | 4 | 5 | 0 / 0 / 1 | 0 / 0 / 0 |
| QA | Middle East | 1 (1) | 1 | 11 | 10 | 10 | 1 / 1 / 1 | 2 / 3 / 5 |
| CN | Asia | 6 (6) | 4 | 37 | 35 | 63 | 4 / 3 / 2 | 1 / 1 / 2 |
| HK | Asia | 1 (1) | 1 | 23 | 20 | 45 | 1 / 1 / 0 | 2 / 2 / 4 |
| IN | Asia | 1 (1) | 1 | 54 | 51 | 53 | 1 / 1 / 1 | 4 / 2 / 6 |
| JP | Asia | 1 (1) | 1 | 21 | 17 | 17 | 1 / 1 / 1 | 2 / 2 / 4 |
| KR | Asia | 1 (1) | 1 | 22 | 19 | 19 | 1 / 1 / 1 | 1 / 1 / 1 |
| SG | Asia | 1 (1) | 1 | 20 | 19 | 19 | 1 / 1 / 1 | 1 / 4 / 5 |
| AU | Oceania | 1 (1) | 1 | 8 | 8 | 8 | 1 / 1 / 1 | 0 / 1 / 3 |

The sentiment index per place needs 3 outlets with confident labels that day. On the complete days that holds for the Americas (that is, the US), Europe, Asia, the UK, Sweden, Germany and, on 24 and 25 November, China. It never holds for the Middle East, Oceania, France, Spain, Belgium, Canada or any single Asian country besides China.

### Configured outlets per country

`rss` = own feed, `gdelt` = headlines through the GDELT DOC API. Every outlet sends its text to a model unless marked `llm: false`.

| Country | Outlets (feed type; `llm: false` marked) |
|---|---|
| US | The New York Times (rss); The Washington Post (rss); The Wall Street Journal (rss); Bloomberg (rss); CNBC (rss); NPR (rss); Politico (rss); Semafor (rss); The Hill (rss); Fortune (rss); Business Insider (rss); The Atlantic (rss, **llm: false**); Vox (rss); Slate (rss); The New Republic (rss); The Nation (rss); Fox News (rss); New York Post (rss); Washington Examiner (rss); National Review (rss); The Free Press (rss); Reason (rss); Breitbart (rss); Daily Caller (rss); The Verge (rss, AI feed); TechCrunch (rss, AI feed); Wired (rss, AI feed); Ars Technica (rss, AI feed); MIT Technology Review (rss, AI feed); IEEE Spectrum (rss, AI feed); 404 Media (rss); Rest of World (rss); Associated Press (gdelt); CNN (gdelt) |
| CA | CBC (rss, disabled) |
| GB | BBC News (rss); The Guardian (rss); Financial Times (rss, AI feed); The Economist (rss); The Telegraph (rss); Sifted (rss); Reuters (gdelt) |
| SE | Dagens Nyheter (rss, sv); Svenska Dagbladet (rss, sv); SVT Nyheter (rss, sv); Breakit (rss, sv); Ny Teknik (rss, sv); Dagens industri (rss, sv) |
| DE | Der Spiegel (rss, AI feed, de); Handelsblatt (rss, de); Deutsche Welle (rss); heise online (rss, de) |
| FR | Le Monde (rss, AI feed, fr); France 24 (rss) |
| BE | Politico Europe (rss) |
| ES | El País (rss, es) |
| QA | Al Jazeera (rss) |
| CN | TechNode (rss); Pandaily (rss); Xinhua (gdelt); China Daily (gdelt); Global Times (gdelt); CGTN (gdelt) |
| HK | South China Morning Post (rss) |
| IN | The Economic Times (rss) |
| JP | Nikkei Asia (rss) |
| KR | The Korea Herald (rss) |
| SG | The Straits Times (rss) |
| AU | ABC News (Australia) (rss) |

Outside the news outlets, the site also reads 2 aggregators, 28 newsletters, 11 lab blogs and Product Hunt; none of them carry a country.

### Outlets that produced nothing

From `source_runs` (17 live runs since 24 November) and the items table:

- **CBC** (CA): disabled since 24 November; robots.txt times out (unreachable, so disallowed).
- **Reuters, AP, CNN, China Daily, CGTN** (GDELT): zero items. GDELT answered HTTP 429 on 11 of the 17 runs, and when it answered, only Xinhua (11 items) and Global Times (2) appeared. GDELT is not a working path to these outlets.
- **The Atlantic**: fetched and counted, but `llm: false`, so no labels (7 relevant headlines).
- Non-outlet sources failing from GitHub's servers with HTTP 403: Marcus on AI and ChinAI (Substack), The Batch (deeplearning.ai), Import AI and Zvi occasionally. Breitbart answered 403 once.

## 2. Gaps

- **Missing regions.** Latin America (0 outlets), Africa (0), Canada (0 active), Central Asia and the Pacific islands.
- **Too thin to count.** Middle East: Al Jazeera's all-news feed alone, 2–6 AI articles a day. Oceania: ABC's all-news feed alone, 2–4 a day. South Asia: The Economic Times only. Southeast Asia: The Straits Times' business feed only. Japan and Korea: one English outlet each, both all-news feeds. Taiwan, the centre of the chip story, has none.
- **Europe is five countries deep.** UK, Sweden, Germany, France, Spain, plus Politico Europe. Nothing from Italy, the Netherlands, Poland, Norway, Denmark, Finland, Switzerland, Austria, Ireland, Portugal, Central and Eastern Europe or Ukraine.
- **Languages.** Only English, Swedish, German, French and Spanish. Of the world's large news languages, Portuguese, Japanese, Korean, Chinese, Arabic, Hindi, Indonesian, Turkish, Russian, Italian, Dutch and Polish are absent.
- **Types.** No working wire service (Reuters and AP only through GDELT, which returns nothing). Chinese state media appear only as a trickle through GDELT.
- **Structural.** The keyword filter knows five languages and fails on scripts without spaces (section 4.2). Even a Portuguese all-news feed would lose most AI stories written out in full.

## 3. Candidate sources

### How they were checked

- One script ran each candidate through `quiet_ai.http.Http` with `config/settings.yaml`: the generic user agent `quiet-ai/0.1 (daily AI news digest; respects robots.txt)`, robots.txt per RFC 9309 (unreachable means disallowed), at least 1 second between requests to one host, and the same retry rules as the pipeline. Never more than one request to a site at a time; different sites in parallel (8 workers). No proxies, no other user agent.
- **robots.txt:** checked for the feed URL by the client itself before any fetch; disallowed feeds were never fetched.
- **Content-Signal:** read from robots.txt on the feed host and on the homepage host.
- **Feed:** fetched and parsed with feedparser. "Works" means entries dated within the last 14 days. When the guessed URL failed, the script read the homepage once for `<link rel="alternate">` feeds and tried up to two. A second pass tried alternative URLs for failures.
- **AI items/day** is an estimate: entries from the last 7 days whose title or summary matches a multilingual AI keyword list, divided by the days the feed spans (at least 1). Measured on 26 November. It counts matches, not Haiku's verdicts; for all-news feeds expect the real figure to be up to a third lower.
- Checked from Benjamin's Mac. Some sites answer GitHub's servers differently (Substack and deeplearning.ai do), so every source needs one more check from a scheduled run after it is added.

### Results

| Region | Checked | Working feed, allowed | robots.txt disallows | HTTP 403 | No current feed | `ai-input=no` |
|---|---|---|---|---|---|---|
| Latin America | 35 | 27 | 3 | 0 | 5 | 0 |
| Africa | 42 | 25 | 1 | 10 | 6 | 0 |
| Middle East | 34 | 22 | 2 | 6 | 4 | 0 |
| South Asia | 24 | 15 | 1 | 4 | 4 | 0 |
| East Asia | 43 | 27 | 1 | 1 | 14 | 0 |
| Southeast Asia | 30 | 18 | 1 | 3 | 7 | 1 |
| Oceania | 18 | 13 | 1 | 1 | 3 | 0 |
| North America | 9 | 8 | 1 | 0 | 0 | 0 |
| Europe | 86 | 70 | 6 | 4 | 5 | 1 |
| **All** | **321** | **225** | **17** | **29** | **48** | **2** |

Notes:

- **robots.txt blocks:** Times of Israel, Canaltech, El Universal, Webrazzi, MediaNama, NHK, news.com.au, CTV, RTVE, L'Usine Digitale, Die Zeit, netzpolitik.org, Tech.eu, TheJournal.ie, El Universo; robots.txt unreachable (so disallowed): News24, detikInet.
- **403 to our client** (bot protection, not worked around): many large sites in Africa, the Gulf and South Asia, among them Arab News, Al Arabiya, Haaretz, Moneycontrol, Business Standard, MyBroadband, BusinessTech, Techpoint Africa, Tech in Asia, Les Echos, Il Post, Silicon Republic, Kathimerini. This is the main reason the list leans toward some countries within each region.
- **Content signals:** only Corriere della Sera and the New Straits Times say `ai-input=no`; they are left out (Corriere's feed is also frozen). Inc42, Focus Taiwan, iThome and ShiftDelete say `ai-input=yes` outright. Thirteen sites (several on the same CDN) send `search=yes,ai-train=no,use=reference`; `use=reference` is not part of Cloudflare's signals and nothing says `ai-input=no`, so under today's rule they are usable. Two planned outlets carry it: Techeconomy (step 1) and Newsroom (step 2). Decided 26 November: treat it as allowed, like any signal that doesn't say `ai-input=no`.
- **Aggregators.** allAfrica's feed works and robots.txt allows it; it republishes many African outlets and could later count like Techmeme (a signal, not an outlet). Google News stays out (robots.txt). GDELT could find outlets per country (`sourcecountry:`), but with 429 on 65% of runs it should only be used by hand for discovery, not as a feed.
- **Regional newsletters.** Most regional AI newsletters are on Substack, which answers GitHub's servers with 403 (ChinAI and Marcus already fail). I'd add none until that changes.
- **Bluesky.** The public AppView's actor search works without a key. Active accounts found that come from or cover places outside the US and UK: Rest of World (41k followers), AlgorithmWatch (DE), netzpolitik.org (DE), La Quadrature du Net (FR), Audrey Tang (TW), Ronaldo Lemos (BR), R3D (MX), Coding Rights (BR), Jathan Sadowski and Toby Walsh (AU). Several searches found the wrong person (for "Paola Ricaurte", "Nikhil Pahwa", "Mutale Nkonde"), so each needs the same hand check as `accounts.yaml`. Bluesky feeds the social signal only; it doesn't change any outlet count.

The full table, with every check, is in the appendix.

## 4. Pipeline and page changes

### 4.1 Regions, countries and the map

Proposed `REGIONS` (step 1 adds the Americas split and Africa; step 3 splits Asia; each step adds only the countries it brings):

```python
REGIONS = [
    ("North America", ["US", "CA"]),
    ("Latin America", ["MX", "CO", "PE", "CL", "AR", "BR"]),
    ("Europe", ["GB", "IE", "FR", "BE", "NL", "DE", "CH", "AT", "ES", "PT", "IT", "SE", "NO", "DK", "FI", "EE", "PL", "CZ", "HU", "UA", "RU"]),
    ("Middle East", ["TR", "IL", "SA", "AE", "QA"]),
    ("Africa", ["EG", "NG", "GH", "ZA"]),
    ("East Asia", ["CN", "HK", "TW", "JP", "KR"]),
    ("South Asia", ["IN", "PK", "BD"]),
    ("Southeast Asia", ["SG", "MY", "TH", "VN", "ID", "PH"]),
    ("Oceania", ["AU", "NZ"]),
]
```

- Egypt goes in Africa (UN M49; Benjamin, 26 November).
- `COUNTRY_NAMES` and `COUNTRY_POS` in `site/build.py` need each new code. Rough centres (lat, lon): MX 23,−102 · CO 4,−73 · PE −10,−76 · CL −33,−71 · AR −34,−64 · BR −10,−52 · NG 9,8 · GH 8,−1 · EG 26,30 · ZA −29,24 · TR 39,35 · IL 31.5,35 · SA 24,45 · AE 24,54 · NZ −41,174 · TW 23.7,121 · PK 30,70 · BD 24,90 · MY 4,102 · TH 15,101 · VN 16,107 · ID −2,118 · PH 12,122 · IE 53,−8 · NL 52,5 · CH 47,8 · AT 47.5,14.5 · PT 39.5,−8 · IT 42.5,12.5 · NO 61,9 · DK 56,10 · FI 63,26 · EE 59,25 · PL 52,19 · CZ 49.8,15.5 · HU 47,19.5 · UA 49,32 · RU 55.8,37.6 (Moscow, where the outlet is; the country's centre is far east).
- The map's continent outlines already include South America and Africa, so the dots light up without new map data. Several European dots will merge on the 5-degree grid; that is fine for a dot map.
- The place filter and the sentiment index per place read `REGIONS`, so they follow. Nine regions plus up to 60 countries make the filter long; on phones it may need the countries folded under their region (check at 380px).
- Frozen editions don't store region names, so the archive is unaffected.
- `GROUP_NAMES` on the About page needs groups for the new outlets (`latam`, `africa`, `middle-east`, `south-asia`, `east-asia`, `southeast-asia`, `oceania`, and `americas` becomes Canada's).

### 4.2 Relevance filtering in other languages

The keyword pass decides most items for free (3,823 of 4,473 news items); only ambiguous ones go to Haiku. It has two problems for new languages, both confirmed on test headlines:

1. **Missing terms.** It knows the spelled-out phrase in English, German, French, Spanish and Swedish. Needed: Portuguese `inteligência artificial`, Italian `intelligenza artificiale`, Dutch `kunstmatige intelligentie`, Polish `sztuczna inteligencja`, Norwegian and Danish `kunstig intelligens`, Finnish `tekoäly`, Czech `umělá inteligence`, Hungarian `mesterséges intelligencia`, Turkish `yapay zeka`, Indonesian `kecerdasan buatan`, Vietnamese `trí tuệ nhân tạo`, Ukrainian `штучний інтелект` and `ШІ`, Japanese `人工知能` and `生成AI`, Korean `인공지능` and `생성형`, Chinese `人工智能`, `人工智慧`, `大模型` and `智能体`, Arabic `الذكاء الاصطناعي`, Hindi `एआई` and `आर्टिफिशियल इंटेलिजेंस`, Thai `ปัญญาประดิษฐ์`. Plus local spellings of "data centre" and "language model".
2. **Word boundaries.** `\b(AI|OpenAI|Nvidia…)\b` never matches inside Japanese or Chinese text, because CJK characters count as word characters: "生成AIが変える仕事", "OpenAI发布新模型" and "Nvidia顶住压力" are all marked "not AI" by keyword, so Haiku never sees them. Fix: match the Latin acronyms and names with `(?<![A-Za-z])…(?![A-Za-z])` instead of `\b`.

Also: `norm_title` keeps only Latin letters, so duplicate titles in non-Latin scripts are never caught (harmless, but they can double-count an outlet's item). And the About page says "five languages" in fixed text.

The cost of this is zero: it is regex. Tests should pin each language with one AI and one non-AI headline.

### 4.3 Translation and its cost

- **Headlines** are already translated: the relevance call returns `title_en` for every relevant non-English item, in the same Haiku request. Measured: 1,191 relevance results cost $0.032, about **$0.000027 per item**. 79–100% of relevant German, French, Spanish and Swedish items have one.
- **Labels** cost $0.274 for 3,620 (three prompt versions), about **$0.000076 per item**. Haiku reads the original headline and summary, with the English title alongside, and copies its evidence in the original language.
- **Summaries are not translated, and needn't be.** The page shows headlines, not summaries; the labeler and the story summarizer read the originals. Translating summaries too would add roughly $0.0001 per item (about $0.02 a day after all steps) for nothing a reader sees.
- **Scripts cost more tokens.** Japanese, Chinese, Korean, Arabic and Hindi take roughly twice the tokens of English for the same headline. The cost figures for step 4 double them.
- **The budget cap.** If the $30 cap is reached, relevance and translation stop with the rest. Latin-script items still cluster without translation; non-Latin ones would form their own stories (4.4). At the expected spend this is far away.

### 4.4 Clustering in other languages

The embedder (`paraphrase-multilingual-MiniLM-L12-v2`) embeds `title_en` when there is one, else the original. A local test, one event in eleven languages against the English headline (join threshold 0.62):

| Language | sv | pt | es | tr | id | zh | ar | ja | hi | ko |
|---|---|---|---|---|---|---|---|---|---|---|
| Similarity to English | 0.83 | 0.95 | 0.88 | 0.92 | 0.91 | 0.56 | 0.51 | 0.46 | 0.46 | 0.41 |

Unrelated pairs stayed at −0.05 to 0.15. So Latin-script languages cluster with English even untranslated, and non-Latin scripts only through their English title. Today that holds: collect runs only fetch, and at publish the relevance step (with translation) runs before embedding. Two weak spots:

- An item whose translation fails or is skipped (API error, budget cap) is embedded in its own script and starts a story of its own. Fix in step 4: hold back non-Latin items without `title_en` from clustering until the next run.
- `entity_boost` and "Most mentioned" use the entity names in the labels, which the prompt asks for "as written". "엔비디아" and "英伟达" won't match "Nvidia". A `news_label_v4` asking for entities in their usual English form would fix it, but a new prompt version relabels the window on the next run (about $0.05–0.10). Not needed before step 4.

### 4.5 Labels in other languages

The labels have never been checked outside English, Swedish and German: the 50 items in `tests/gold/labels.yaml` (for Benjamin's hand labels) and the Opus cross-check are 40 English, 6 Swedish and 4 German. Two cheap safeguards:

- Extend `qa eval crosscheck` with about 10 items per new language after each step. The last run, 50 items, cost $0.16.
- **Decided 26 November: a new language's outlets stay out of the sentiment index for their first two weeks.** Each gets `index_from: <date two weeks after it is added>` in `sources.yaml`; the index (overall and per place) skips its labels before that date. A date lifts itself, so no second change is needed. Its articles are still labeled, shown on cards and counted in ranking. In those two weeks, run the cross-check on about 10 of its items per language (Opus costs money, so only with Benjamin's OK each time). Outlets in languages the site already reads (English, Spanish, French, German, Swedish) skip this.

### 4.6 Ranking: should regions be weighed?

Momentum gives 0.25 to the number of distinct outlets and 0.10 to the number of distinct countries, both log-scaled. A story only US outlets cover can reach 20–30 outlets; the same story in Kenya can't, because there are no Kenyan outlets to count.

Options:

- **A. Leave the formula; fix the inputs.** Adding outlets elsewhere lowers the US share of what is counted from about half to under a fifth (table in section 5). The `countries` term already rewards spread, and will mean more once there are 40+ countries instead of 16.
- **B. Diminishing returns per country**, for example counting √n outlets per country. 16 US outlets would count as 4. Honest trade-off: it demotes stories that are big *because* they are American (US policy, US lawsuits), and Sweden's six outlets would count as 2.4; it changes what "most covered" means.
- **C. A `regions` term** (distinct regions covering the story) taken from the `outlets` weight. It rewards stories the whole world covers without demoting anything outright; it also lifts global stories that are thin in each place.

**Recommendation:** A now. After steps 1–3 and two weeks of data, compute B and C offline (momentum needs no model calls) and compare the top 12s side by side before deciding. Whatever is chosen, the About page should say it in one sentence.

### 4.7 The sentiment index

The index averages outlets, so each outlet is one voice and the region with most outlets weighs most. Today about half the voices are American. Taken together they read more critical than the outlets outside the US, though Europe was more critical still on 24 and 25 November and Asia close to neutral (23 November is backlog only):

| Day | All news outlets | US only | Outside the US | Europe | Asia | Region-balanced (mean of regions with ≥3 outlets) |
|---|---|---|---|---|---|---|
| 23 Nov | −0.30 (49 outlets) | −0.55 | −0.02 | −0.07 | +0.15 (5) | −0.16 |
| 24 Nov | −0.41 (54) | −0.53 | −0.29 | −0.59 | +0.21 (9) | −0.30 |
| 25 Nov | −0.51 (51) | −0.56 | −0.47 | −0.72 | −0.05 (8) | −0.44 |

(The site's headline figure also counts commentary newsletters as voices: −0.37 on 24 November, −0.44 on 25 November.)

Trade-offs of a region-balanced index: it would answer "how does the world's press read AI" instead of "how does the press we read read AI", but each region's voice would rest on very different numbers of outlets (3 in one, 30 in another), and the figure would jump on days a thin region crosses the 3-outlet threshold (23 November: Asia's five outlets move it from −0.30 to −0.16). It also changes the meaning of the history.

**Recommendation:** keep the headline index as it is, add a small table of the regional figures on `/sentiment/` (region, outlets labeled, value), and say on the page what share of labeled outlets are American that day. Reconsider a region-balanced figure, shown beside the main one, once every region reaches 3 outlets on most days (expected after step 2).

### 4.8 Story cards

A card's stance stripe counts articles, not outlets. Infobae (about 24 AI articles a day) or AI Times Korea (about 40) could tip a story's stripe on their own. Counting each outlet once in the stripe, like the index does, would prevent it. Small change in `pipeline/edition.py`; best done with step 1.

### 4.9 The About page

Today's Limits section says the list "leans toward English-language and Western outlets". After step 1 it should say, with numbers filled in at build time:

> The outlet list decides what you see. It has {n} outlets in {countries} countries and {languages} languages: {North America n}, {Latin America n}, {Europe n}, {Middle East n}, {Africa n}, {Asia n}, {Oceania n}. It includes only outlets with a free feed that allow automated readers; many large outlets in Africa, the Gulf and South Asia block them, so each region leans toward the outlets that don't. Headlines in other languages are translated by a small language model for display and grouping; the labels are made from the original words. A region or country gets an index figure only on days when at least 3 of its outlets were labeled. The overall index counts each outlet once, so the region with the most outlets weighs most: on {date}, {pct}% of labeled outlets were in the United States. State-aligned outlets are marked as such in the list of sources.

Also replace "checked for AI terms in five languages" with the real count, and group the source list by the new regions.

## 5. The plan

Expected outlets with a confident label on a typical day, by region (sum over outlets of the chance of at least one AI article that day, times 0.9 for the confident share). The baseline is the average of 24 and 25 November.

| | North America | Latin America | Europe | Middle East | Africa | Asia | Oceania | US share | Added cost/month |
|---|---|---|---|---|---|---|---|---|---|
| Today | 25.5 | 0 | 16.5 | 1 | 0 | 8.5 | 1 | 49% | – |
| After step 1 | 25.5 | **10.7** | 16.5 | 1 | **6.9** | 8.5 | 1 | 36% | $0.29 |
| After step 2 | **28.8** | 10.7 | 16.5 | **5.6** | 6.9 | 8.5 | **5.1** | 31% | $0.10 |
| After step 3 | 28.8 | 10.7 | 16.5 | 5.6 | 6.9 | **27.5** | 5.1 | 25% | $0.34 |
| After step 4 | 28.8 | 10.7 | 16.5 | **8.9** | **7.8** | **40.8** | 5.1 | 22% | $1.24 |
| After step 5 | 28.8 | 10.7 | **33.9** | 8.9 | 7.8 | 40.8 | 5.1 | 19% | $0.24 |
| After step 6 | 28.8 | 10.7 | **43.2** | 8.9 | 7.8 | 40.8 | 5.1 | 18% | $0.12 |

Within Asia after step 3: East Asia 11.9, South Asia 7.9, Southeast Asia 7.8; after step 4: 21.6, 9.7, 9.6.

Costs are Haiku only (relevance on the ~9% of fetched items the keywords can't decide, translation, labels), from the measured per-item prices. Each step also has a one-time backlog of at most 100 items per new feed (under $0.10). Sonnet: today $0.10–0.20 a day for story summaries. The number of summaries is capped by the views (4 × 12 top stories), so more outlets can raise it only toward that ceiling, about $0.30–0.45 a day if every top story grew every day. **Worst case after all steps: about $15 a month.** Expected: $8–10.

Every step also needs, on the day it lands: one scheduled collect run to confirm each feed from GitHub's servers (disable any that fail there), `uv run pytest`, and a look at the page in light and dark mode at desktop width and 380px.

### Step 1: Latin America and Africa (24 outlets, start here)

The two empty continents, in languages the pipeline already reads.

| Outlet | Country | Lang | Type | Feed | AI items/day |
|---|---|---|---|---|---|
| Infobae | AR | es | mainstream | `www.infobae.com/arc/outboundfeeds/rss/category/tecno/` | 24.1 |
| La Nación | AR | es | mainstream | `www.lanacion.com.ar/arc/outboundfeeds/rss/?outputType=xml` | 2.0 |
| Exame | BR | pt | business | `exame.com/feed/` | 4.0 |
| Folha de S.Paulo | BR | pt | mainstream | `feeds.folha.uol.com.br/tec/rss091.xml` | 4.9 |
| g1 (Globo) | BR | pt | mainstream | `g1.globo.com/rss/g1/tecnologia/` | 5.6 |
| Núcleo Jornalismo | BR | pt | trade | `nucleo.jor.br/feed/` | 1.6 |
| Tecnoblog | BR | pt | trade | `tecnoblog.net/feed/` | 4.6 |
| La Tercera | CL | es | mainstream | `www.latercera.com/arc/outboundfeeds/rss/?outputType=xml` | 5.0 |
| El Tiempo | CO | es | mainstream | `www.eltiempo.com/rss/tecnosfera.xml` | 4.5 |
| Semana | CO | es | mainstream | `www.semana.com/arc/outboundfeeds/rss/?outputType=xml` | 2.0 |
| Egypt Independent | EG | en | mainstream | `egyptindependent.com/feed/` | 2.0 |
| MyJoyOnline | GH | en | mainstream | `www.myjoyonline.com/feed/` | 1.0 |
| El Financiero | MX | es | business | `www.elfinanciero.com.mx/arc/outboundfeeds/rss/?outputType=xml` | 4.0 |
| Expansión | MX | es | business | `expansion.mx/rss/tecnologia` | 1.3 |
| BusinessDay | NG | en | business | `businessday.ng/feed/` | 1.0 |
| Nairametrics | NG | en | business | `nairametrics.com/feed/` | 1.0 |
| Premium Times | NG | en | mainstream | `www.premiumtimesng.com/feed` | 1.0 |
| TechCabal | NG | en | trade | `techcabal.com/feed/` | 0.9 |
| Techeconomy | NG | en | trade | `techeconomy.ng/feed.xml` | 2.6 |
| El Comercio | PE | es | mainstream | `elcomercio.pe/arc/outboundfeeds/rss/category/tecnologia/?outputType=xml` | 1.1 |
| Daily Maverick | ZA | en | mainstream | `www.dailymaverick.co.za/dmrss/` | 0.7 |
| IOL | ZA | en | mainstream | `www.iol.co.za/rss` | 1.0 |
| ITWeb | ZA | en | trade | `www.itweb.co.za/rss` | 1.4 |
| TechCentral | ZA | en | trade | `techcentral.co.za/feed/` | 2.3 |

Code in the same step: `REGIONS` split into North America and Latin America, Africa added; names and map positions for BR, MX, AR, CL, CO, PE, NG, ZA, GH, EG; Portuguese terms in the keyword list (with tests); About page groups and the new Limits text (4.9); stance stripe counted per outlet (4.8); `index_from` for the two-week index wait (4.5), set on the five Portuguese outlets.

- **Effect:** Latin America 0 → about 11 outlets labeled a day, Africa 0 → about 7. Both get a daily index. For the first two weeks Latin America's index comes from its eight Spanish-language outlets (about 6 labeled a day), still above the threshold. The US share of labeled outlets falls from 49% to about 36%.
- **Cost:** about $0.01 a day, $0.29 a month.
- **Risks:**
  - Spanish and Portuguese all-news feeds (La Tercera, Semana, La Nación: about 100 items a day each) mean more keyword work and some extra Haiku calls (in the cost).
  - Africa will be mostly Nigeria and South Africa. Kenya's outlets returned 403 or carried almost no AI news; francophone African outlets had no AI items. Egypt is the only North African country.
  - Labels in Spanish and Portuguese haven't been cross-checked yet; add them to the next crosscheck.
  - Infobae alone writes about 24 AI articles a day (hence 4.8).
  - Techeconomy sends the unrecognised `use=reference` signal (treated as allowed).

### Step 2: Middle East, Oceania and Canada (19 outlets)

Regions that exist but are too thin to count, all in English or French.

| Outlet | Country | Lang | Type | Feed | AI items/day |
|---|---|---|---|---|---|
| Gulf News | AE | en | mainstream | `gulfnews.com/feed` | 0.4 |
| The National | AE | en | mainstream | `www.thenationalnews.com/arc/outboundfeeds/rss/?outputType=xml` | 6.5 |
| Crikey | AU | en | opinion | `www.crikey.com.au/feed/` | 0.8 |
| iTnews | AU | en | trade | `www.itnews.com.au/RSS/rss.ashx` | 1.1 |
| Startup Daily | AU | en | trade | `www.startupdaily.net/feed/` | 0.9 |
| The Sydney Morning Herald | AU | en | mainstream | `www.smh.com.au/rss/technology.xml` | 0.6 |
| BetaKit | CA | en | trade | `betakit.com/feed/` | 1.6 |
| Global News | CA | en | mainstream | `globalnews.ca/tech/feed/` | 1.0 |
| La Presse | CA | fr | mainstream | `www.lapresse.ca/affaires/techno/rss` | 0.9 |
| Radio-Canada | CA | fr | public-broadcaster | `ici.radio-canada.ca/rss/5717` | 3.3 |
| The Globe and Mail | CA | en | mainstream | `www.theglobeandmail.com/arc/outboundfeeds/rss/category/business/technology/` | 1.0 |
| Globes | IL | en | business | `en.globes.co.il/WebService/Rss/RssFeeder.asmx/FeederNode?iID=1725` | 0.9 |
| 1News (TVNZ) | NZ | en | public-broadcaster | `www.1news.co.nz/arc/outboundfeeds/rss/?outputType=xml` | 1.2 |
| Newsroom | NZ | en | mainstream | `newsroom.co.nz/feed/` | 4.0 |
| RNZ | NZ | en | public-broadcaster | `www.rnz.co.nz/rss/business.xml` | 1.0 |
| Asharq Al-Awsat (English) | SA | en | state-aligned | `english.aawsat.com/feed/` | 3.0 |
| Saudi Gazette | SA | en | state-aligned | `saudigazette.com.sa/rssFeed/74` | 0.8 |
| Anadolu Agency | TR | en | state-aligned (wire) | `www.aa.com.tr/en/rss/default?cat=science-technology` | 1.3 |
| Daily Sabah | TR | en | state-aligned | `www.dailysabah.com/rss/business/tech` | 2.6 |

- **Effect:** Middle East 1 → about 6 labeled a day, Oceania 1 → about 5, Canada 0 → about 3. Both regions get a daily index. US share about 31%.
- **Cost:** about $0.003 a day, $0.10 a month.
- **Risks:**
  - The Middle East would lean Gulf and Turkish state-aligned: Asharq Al-Awsat and Saudi Gazette are close to the Saudi state, Daily Sabah is pro-government, Anadolu is the Turkish state agency. All four carry `type: state-aligned` (decided 26 November), so the About page lists them as such. Israel has only Globes: Times of Israel is blocked by robots.txt and Haaretz returns 403. Iran has nothing usable.
  - CBC stays disabled; Canada is four commercial outlets and Radio-Canada.
  - Newsroom (NZ) sends `use=reference` (treated as allowed).

### Step 3: Asia in English (23 outlets)

South and Southeast Asia, Korea and Taiwan, without any language work.

| Outlet | Country | Lang | Type | Feed | AI items/day |
|---|---|---|---|---|---|
| The Daily Star | BD | en | mainstream | `www.thedailystar.net/tech-startup/rss.xml` | 3.6 |
| Sixth Tone | CN | en | state-aligned | `www.sixthtone.com/rss` | 6.0 |
| Antara (English) | ID | en | wire | `en.antaranews.com/rss/news.xml` | 4.0 |
| Analytics India Magazine | IN | en | trade | `analyticsindiamag.com/feed/` | 6.3 |
| Inc42 | IN | en | trade | `inc42.com/feed/` | 5.0 |
| Mint | IN | en | business | `www.livemint.com/rss/technology` | 3.9 |
| Scroll.in | IN | en | mainstream | `feeds.feedburner.com/ScrollinArticles.rss` | 0.6 |
| The Hindu | IN | en | mainstream | `www.thehindu.com/sci-tech/technology/feeder/default.rss` | 6.0 |
| The Indian Express | IN | en | mainstream | `indianexpress.com/section/technology/feed/` | 3.4 |
| The Elec | KR | en | trade | `www.thelec.net/rss/allArticle.xml` | 10.0 |
| The Korea Times | KR | en | mainstream | `www.koreatimes.co.kr/www/rss/rss.xml` | 20.0 |
| Yonhap News Agency | KR | en | wire | `en.yna.co.kr/RSS/news.xml` | 11.0 |
| Free Malaysia Today | MY | en | mainstream | `www.freemalaysiatoday.com/feed/` | 3.0 |
| BusinessWorld | PH | en | business | `www.bworldonline.com/feed/` | 2.0 |
| Rappler | PH | en | mainstream | `www.rappler.com/technology/feed/` | 3.0 |
| Dawn | PK | en | mainstream | `www.dawn.com/feeds/home` | 2.0 |
| The Express Tribune | PK | en | mainstream | `tribune.com.pk/feed/technology` | 0.6 |
| CNA | SG | en | public-broadcaster | `www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6936` | 7.0 |
| e27 | SG | en | trade | `e27.co/feed/` | 4.0 |
| Bangkok Post | TH | en | mainstream | `www.bangkokpost.com/rss/data/business.xml` | 3.0 |
| DigiTimes Asia | TW | en | trade | `www.digitimes.com/rss/daily.xml` | 18.0 |
| Taipei Times | TW | en | mainstream | `www.taipeitimes.com/xml/index.rss` | 3.0 |
| VietnamPlus (English) | VN | en | state-aligned | `en.vietnamplus.vn/rss/home.rss` | 2.0 |

Code: split Asia into East, South and Southeast Asia; names and positions for the new countries.

- **Effect:** Asia 8.5 → about 27 labeled a day (East 12, South 8, Southeast 8). Every region is now expected to reach the 3-outlet threshold on most days. US share about 25%.
- **Cost:** about $0.01 a day, $0.34 a month.
- **Risks:**
  - Asia would have about as many labeled outlets as North America. That is the point, but the overall index would move toward Asia's reading, which on 24–25 November was close to neutral where the US was critical.
  - Indian startup and AI trade outlets (Inc42, Analytics India Magazine) publish a lot of announcement-style copy; expect more "boom" labels.
  - Sixth Tone (Shanghai United Media Group), Antara and VietnamPlus are state-owned: mark them state-aligned.
  - DigiTimes Asia is partly paywalled; headline and summary only, as with the FT.
  - Japan in English stays thin: the Kyodo, NHK World, Yomiuri and Mainichi feeds are gone or blocked.

### Step 4: Asian languages and Arabic (20 outlets)

| Outlet | Country | Lang | Type | Feed | AI items/day |
|---|---|---|---|---|---|
| Sky News Arabia (tech) | AE | ar | mainstream | `www.skynewsarabia.com/rss/technology.xml` | 1.3 |
| IT之家 (ITHome) | CN | zh | trade | `www.ithome.com/rss/` | 17.0 |
| 量子位 (QbitAI) | CN | zh | trade | `www.qbitai.com/feed` | 8.0 |
| Youm7 (tech) | EG | ar | mainstream | `www.youm7.com/rss/SectionRss?SectionID=328` | 5.0 |
| CNN Indonesia | ID | id | mainstream | `www.cnnindonesia.com/teknologi/rss` | 4.1 |
| Amar Ujala (tech) | IN | hi | mainstream | `www.amarujala.com/rss/technology.xml` | 3.2 |
| NDTV India (Hindi) | IN | hi | mainstream | `feeds.feedburner.com/ndtvkhabar-latest` | 5.0 |
| GIGAZINE | JP | ja | trade | `gigazine.net/news/rss_2.0/` | 15.0 |
| Impress Watch | JP | ja | trade | `www.watch.impress.co.jp/data/rss/1.0/ipw/feed.rdf` | 1.9 |
| ITmedia AI+ | JP | ja | trade | `rss.itmedia.co.jp/rss/2.0/aiplus.xml` | 13.3 |
| Nikkei xTECH | JP | ja | trade | `xtech.nikkei.com/rss/index.rdf` | 13.9 |
| AI Times (Korea) | KR | ko | trade | `www.aitimes.com/rss/allArticle.xml` | 42.0 |
| Chosun Ilbo | KR | ko | mainstream | `www.chosun.com/arc/outboundfeeds/rss/?outputType=xml` | 3.1 |
| Electronic Times (etnews) | KR | ko | trade | `rss.etnews.com/Section901.xml` | 9.0 |
| ZDNet Korea | KR | ko | trade | `feeds.feedburner.com/zdkorea` | 14.0 |
| AITNews (البوابة العربية للأخبار التقنية) | SA | ar | trade | `aitnews.com/feed/` | 5.0 |
| Tech-WD (عالم التقنية) | SA | ar | trade | `www.tech-wd.com/wd/feed/` | 3.0 |
| ShiftDelete.Net | TR | tr | trade | `shiftdelete.net/feed` | 7.6 |
| iThome | TW | zh | trade | `www.ithome.com.tw/rss` | 8.0 |
| Tuổi Trẻ | VN | vi | mainstream | `tuoitre.vn/rss/cong-nghe.rss` | 29.0 |

Code first, in the same step: the keyword and word-boundary fixes (4.2) with tests; hold back untranslated non-Latin items from clustering (4.4); duplicate-title check for non-Latin scripts; `index_from` on all 20 outlets (every one is in a new language). Consider `news_label_v4` for English entity names (4.4; relabels the window, about $0.05–0.10).

- **Effect:** Asia about 41 labeled a day (East Asia about 22), Middle East about 9, Africa about 8 (Youm7). Japanese, Korean and Chinese readers' own press enters the picture, not just its English editions.
- **Cost:** about $0.04 a day, $1.24 a month (double tokens for these scripts included).
- **Risks:**
  - This is the step where labels are least checked: stance wording differs across languages and cultures. The two-week index wait and the cross-check (4.5) are there for this.
  - AI Times Korea, ITmedia AI+ and QbitAI are AI-only trade feeds with high volume (mark `ai_focused: true` where the whole feed is AI).
  - East Asia would outnumber Europe. If that's too much, drop GIGAZINE, etnews and iThome (Taiwan) and keep 17.
  - cnBeta and Solidot are optional: both mainland Chinese, often aggregating other sites.

### Step 5: Western Europe beyond the big five (24 outlets)

| Outlet | Country | Lang | Type | Feed | AI items/day |
|---|---|---|---|---|---|
| Der Standard | AT | de | mainstream | `www.derstandard.at/rss/web` | 4.2 |
| ORF | AT | de | public-broadcaster | `rss.orf.at/news.xml` | 2.0 |
| EUobserver | BE | en | mainstream | `euobserver.com/feed/` | 2.4 |
| Neue Zürcher Zeitung | CH | de | mainstream | `www.nzz.ch/technologie.rss` | 1.0 |
| SRF | CH | de | public-broadcaster | `www.srf.ch/news/bnf/rss/1922` | 0.6 |
| Frankfurter Allgemeine | DE | de | mainstream | `www.faz.net/rss/aktuell/` (all news; the Digitec feed failed) | 1.4 |
| Süddeutsche Zeitung | DE | de | mainstream | `rss.sueddeutsche.de/rss/Digital` | 0.9 |
| t3n | DE | de | trade | `t3n.de/rss.xml` | 10.0 |
| Xataka | ES | es | trade | `www.xataka.com/feedburner.xml` | 5.0 |
| franceinfo | FR | fr | public-broadcaster | `www.francetvinfo.fr/internet.rss` | 6.8 |
| Le Figaro | FR | fr | mainstream | `www.lefigaro.fr/rss/figaro_secteur_high-tech.xml` | 2.1 |
| Libération | FR | fr | mainstream | `www.liberation.fr/arc/outboundfeeds/rss/?outputType=xml` | 4.0 |
| RTÉ | IE | en | public-broadcaster | `www.rte.ie/feeds/rss/?index=/news/business/` | 3.9 |
| The Irish Times | IE | en | mainstream | `www.irishtimes.com/arc/outboundfeeds/feed-business/?outputType=xml` | 3.3 |
| ANSA | IT | it | wire | `www.ansa.it/sito/ansait_rss.xml` | 0.6 |
| Il Sole 24 Ore | IT | it | business | `www.ilsole24ore.com/rss/tecnologia.xml` | 0.7 |
| la Repubblica | IT | it | mainstream | `www.repubblica.it/rss/tecnologia/rss2.0.xml` | 2.8 |
| Punto Informatico | IT | it | trade | `www.punto-informatico.it/feed/` | 4.0 |
| Het Financieele Dagblad | NL | nl | business | `fd.nl/?rss` | 0.7 |
| NOS | NL | nl | public-broadcaster | `feeds.nos.nl/nosnieuwstech` | 0.7 |
| NRC | NL | nl | mainstream | `www.nrc.nl/rss/` | 1.0 |
| Tweakers | NL | nl | trade | `tweakers.net/feeds/mixed.xml` | 8.2 |
| ECO | PT | pt | business | `eco.sapo.pt/feed/` | 2.0 |
| Observador | PT | pt | mainstream | `observador.pt/feed/` | 3.0 |

Code: names and positions for IT, NL, IE, PT, CH, AT; Italian and Dutch keywords (from step 4's list if that went first); `index_from` on the Italian and Dutch outlets (Portuguese will have served its wait in step 1).

- **Effect:** Europe 16.5 → about 34 labeled a day. Italy, the Netherlands, Ireland, Portugal, Switzerland and Austria reach the per-country threshold on most days (Italy and the Netherlands after their two-week wait).
- **Cost:** about $0.008 a day, $0.24 a month.
- **Risks:** Corriere della Sera is out (`ai-input=no`, feed frozen). FAZ and SZ add German right and left of centre; Germany would have seven outlets, more than any country but the US. Il Post and Les Echos return 403.

### Step 6: Nordics, Central and Eastern Europe, Ukraine, Russia (14 outlets)

| Outlet | Country | Lang | Type | Feed | AI items/day |
|---|---|---|---|---|---|
| Lupa.cz | CZ | cs | trade | `www.lupa.cz/rss/clanky/` | 0.7 |
| DR | DK | da | public-broadcaster | `www.dr.dk/nyheder/service/feeds/allenyheder` | 1.0 |
| Version2 | DK | da | trade | `www.version2.dk/rss` | 1.9 |
| ERR News | EE | en | public-broadcaster | `news.err.ee/rss` | 2.1 |
| Helsingin Sanomat | FI | fi | mainstream | `www.hs.fi/rss/tuoreimmat.xml` | 3.8 |
| Telex | HU | hu | mainstream | `telex.hu/rss` | 2.0 |
| Digi.no | NO | no | trade | `www.digi.no/rss` | 2.1 |
| E24 | NO | no | business | `e24.no/rss2/` | 4.8 |
| NRK | NO | no | public-broadcaster | `www.nrk.no/toppsaker.rss` | 0.2 |
| Rzeczpospolita | PL | pl | mainstream | `www.rp.pl/rss_main` | 1.0 |
| Spider's Web | PL | pl | trade | `spidersweb.pl/feed` | 2.5 |
| TVN24 | PL | pl | mainstream | `tvn24.pl/najnowsze.xml` | 0.6 |
| DOU | UA | uk | trade | `dou.ua/feed/` | 1.0 |
| TASS | RU | en | state-aligned | `tass.com/rss/v2.xml` | 3.0 |

Code: names and positions for NO, DK, FI, PL, HU, CZ, EE, UA, RU; Norwegian, Danish, Finnish, Polish, Hungarian, Czech and Ukrainian keywords; `index_from` on the outlets in those languages (not ERR News or TASS, which are in English).

- **Effect:** Europe about 43 labeled a day. Smaller countries mostly stay under the per-country threshold; they count in the region.
- **Cost:** about $0.004 a day, $0.12 a month.
- **Risks:** NRK's front-page feed carries little AI (0.2 a day); Yle's English feed had none and is left out. Ukraine's English outlets (Kyiv Independent, Ukrainska Pravda) had no AI items; DOU is a developer community site.
- **Russia (decided 26 November: add TASS).** TASS is the Russian state news agency; its English feed carries about 100 items a day, about 3 of them on AI. It goes in as `type: state-aligned`, so the source list says so, and it counts in Europe. Meduza and The Moscow Times (exile media, little AI) stay in reserve.

### Step 7: Weighting decisions (no new sources)

After steps 1–3 and two weeks of data: compute ranking options B and C (4.6) and a region-balanced index (4.7) offline, show Benjamin the differences, then decide. Any change goes on the About page.

- **Cost:** none (no model calls).
- **Risk:** any weighting is an editorial choice; the page must say which one it makes.

### Step 8 (optional): Bluesky accounts outside the US and UK

Hand-check the accounts listed in section 3 and add the right ones to `config/accounts.yaml`. Affects the social signal only. Cost: none (Bluesky is free; their posts are not labeled).

## 6. Decisions

Benjamin, 26 November:

1. **Egypt:** in Africa.
2. **`Content-Signal: use=reference`:** allowed (it doesn't say `ai-input=no`), so Techeconomy and Newsroom stay in.
3. **Gulf and Turkish outlets in step 2:** `type: state-aligned` (Asharq Al-Awsat, Saudi Gazette, Daily Sabah, Anadolu). Step 3's state-owned outlets (Sixth Tone, Antara, VietnamPlus) are marked the same way.
4. **Russia:** add TASS as state-aligned, in step 6.
5. **New languages:** two weeks out of the sentiment index, through `index_from` (4.5).

Still open: approval of each step, starting with step 1.

## Appendix: every candidate checked

"Feed checked" is the best URL tried for the outlet (alternatives that failed are not listed). "AI/day" is the keyword estimate described in section 3; "–" where the feed didn't work. "Plan" gives the step, "opt." for a working feed held in reserve, or the reason it is left out.

### Latin America (35 checked, 27 with a working feed, 13 in the plan)

| Outlet | Country | Lang | Type | Feed checked | robots.txt | Content-Signal | Feed | AI/day | Plan |
|---|---|---|---|---|---|---|---|---|---|
| Buenos Aires Times | AR | en | mainstream | `www.batimes.com.ar/feed` | allows | none | works, 5/day | 0.0 | no (little AI) |
| Clarín | AR | es | mainstream | `www.clarin.com/rss/tecnologia/` | allows | none | works, 2/day | 0.8 | opt. |
| Infobae | AR | es | mainstream | `www.infobae.com/arc/outboundfeeds/rss/category/tecno/` | allows | none | works, 67/day | 24.1 | Step 1 |
| La Nación | AR | es | mainstream | `www.lanacion.com.ar/arc/outboundfeeds/rss/?outputType=xml` | allows | none | works, 86/day | 2.0 | Step 1 |
| Página/12 | AR | es | mainstream | `www.pagina12.com.ar/rss/secciones/ciencia/notas` | allows | none | HTTP 404 | – | no |
| Agência Brasil (EBC) | BR | pt | public-broadcaster | `agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml` | allows | none | works, 10/day | 0.0 | opt. (public; little AI) |
| Canaltech | BR | pt | trade | `canaltech.com.br/rss/` | **disallows feed** | none | not fetched | – | no |
| Estadão | BR | pt | mainstream | `www.estadao.com.br/arc/outboundfeeds/feeds/rss/sections/e…` | allows | none | works, 3/day | 0.0 | no (little AI) |
| Exame | BR | pt | business | `exame.com/feed/` | allows | none | works, 25/day | 4.0 | Step 1 |
| Folha de S.Paulo | BR | pt | mainstream | `feeds.folha.uol.com.br/tec/rss091.xml` | allows | none | works, 7/day | 4.9 | Step 1 |
| g1 (Globo) | BR | pt | mainstream | `g1.globo.com/rss/g1/tecnologia/` | allows | none | works, 8/day | 5.6 | Step 1 |
| LABS (Latin America Business Stories) | BR | en | business | `labsnews.com/en/feed/` | allows | none | not a feed (bot check or HTML) | – | no |
| MIT Technology Review Brasil | BR | pt | trade | `mittechreview.com.br/feed/` | allows | none | works, 1/day | 0.3 | opt. |
| Núcleo Jornalismo | BR | pt | trade | `nucleo.jor.br/feed/` | allows | none | works, 2/day | 1.6 | Step 1 |
| Olhar Digital | BR | pt | trade | `olhardigital.com.br/feed/` | allows | none | works, 10/day | 4.0 | opt. |
| Tecnoblog | BR | pt | trade | `tecnoblog.net/feed/` | allows | none | works, 29/day | 4.6 | Step 1 |
| The Brazilian Report | BR | en | mainstream | `brazilian.report/feed/` | allows | none | HTTP 404 | – | no |
| The Rio Times | BR | en | mainstream | `www.riotimesonline.com/feed/` | allows | none | works, 10/day | 1.0 | opt. |
| BioBioChile | CL | es | mainstream | `feeds.feedburner.com/radiobiobio/NNeJ` | allows | none | stale (newest 15 days) | – | no |
| FayerWayer | CL | es | trade | `www.fayerwayer.com/arc/outboundfeeds/rss/?outputType=xml` | allows | none | works, 5/day | 1.1 | opt. |
| La Tercera | CL | es | mainstream | `www.latercera.com/arc/outboundfeeds/rss/?outputType=xml` | allows | none | works, 100/day | 5.0 | Step 1 |
| El Espectador | CO | es | mainstream | `www.elespectador.com/arc/outboundfeeds/discover/category/…` | allows | none | works, 1/day | 0.3 | opt. |
| El Tiempo | CO | es | mainstream | `www.eltiempo.com/rss/tecnosfera.xml` | allows | none | works, 6/day | 4.5 | Step 1 |
| Semana | CO | es | mainstream | `www.semana.com/arc/outboundfeeds/rss/?outputType=xml` | allows | none | works, 100/day | 2.0 | Step 1 |
| The Tico Times | CR | en | mainstream | `ticotimes.net/feed` | allows | none | works, 7/day | 0.0 | no (little AI) |
| El Universo | EC | es | mainstream | `www.eluniverso.com/arc/outboundfeeds/rss/?outputType=xml` | **disallows feed** | none | not fetched | – | no |
| El Financiero | MX | es | business | `www.elfinanciero.com.mx/arc/outboundfeeds/rss/?outputType…` | allows | none | works, 100/day | 4.0 | Step 1 |
| El Universal | MX | es | mainstream | `www.eluniversal.com.mx/rss.xml` | **disallows feed** | none | not fetched | – | no |
| Expansión | MX | es | business | `expansion.mx/rss/tecnologia` | allows | none | works, 3/day | 1.3 | Step 1 |
| La Jornada | MX | es | mainstream | `www.jornada.com.mx/rss/ciencias.xml` | allows | none | works, 2/day | 0.0 | no (little AI) |
| Mexico News Daily | MX | en | mainstream | `mexiconewsdaily.com/feed/` | allows | none | works, 8/day | 0.0 | no (little AI) |
| Milenio | MX | es | mainstream | `www.milenio.com/rss` | allows | none | HTTP 404 | – | no |
| Xataka México | MX | es | trade | `www.xataka.com.mx/feedburner.xml` | allows | none | works, 20/day | 1.0 | opt. |
| El Comercio | PE | es | mainstream | `elcomercio.pe/arc/outboundfeeds/rss/category/tecnologia/?…` | allows | none | works, 11/day | 1.1 | Step 1 |
| MercoPress | UY | en | mainstream | `en.mercopress.com/rss/` | allows | none | works, 10/day | 0.0 | no (little AI) |

### Africa (42 checked, 25 with a working feed, 12 in the plan)

| Outlet | Country | Lang | Type | Feed checked | robots.txt | Content-Signal | Feed | AI/day | Plan |
|---|---|---|---|---|---|---|---|---|---|
| Africanews | CG | en | mainstream | `www.africanews.com/feed/rss` | allows | none | works, 20/day | 0.4 | opt. |
| CIO Mag | CI | fr | trade | `cio-mag.com/feed/` | allows | none | stale (newest 21 days) | – | no |
| Ahram Online | EG | en | state-aligned | `english.ahram.org.eg/UI/Front/Rss.aspx` | allows | search=yes,ai-train=no,use=reference | HTTP 403 (refuses our client) | – | no |
| Daily News Egypt | EG | en | mainstream | `www.dailynewsegypt.com/feed/` | allows | none | works, 10/day | 0.0 | no (little AI) |
| Egypt Independent | EG | en | mainstream | `egyptindependent.com/feed/` | allows | none | works, 10/day | 2.0 | Step 1 |
| Mada Masr | EG | en | mainstream | `www.madamasr.com/en/feed/` | allows | search=yes,ai-train=no,use=reference | stale (newest 30 days) | – | no |
| Youm7 (tech) | EG | ar | mainstream | `www.youm7.com/rss/SectionRss?SectionID=328` | allows | none | works, 20/day | 5.0 | Step 4 |
| Addis Standard | ET | en | mainstream | `addisstandard.com/feed/` | allows | none | HTTP 403 (refuses our client) | – | no |
| MyJoyOnline | GH | en | mainstream | `www.myjoyonline.com/feed/` | allows | none | works, 50/day | 1.0 | Step 1 |
| Capital FM (Kenya) | KE | en | mainstream | `www.capitalfm.co.ke/news/feed/` | allows | none | works, 10/day | 0.0 | no (little AI) |
| Kenyans.co.ke | KE | en | mainstream | `www.kenyans.co.ke/feeds/news` | allows | search=yes,ai-train=no,use=reference | works, 20/day | 0.0 | no (little AI) |
| Nation (Kenya) | KE | en | mainstream | `nation.africa/kenya/rss.xml` | allows | search=yes,ai-train=no,use=reference | works, 25/day | 0.0 | opt. (Kenya; little AI) |
| TechMoran | KE | en | trade | `techmoran.com/feed/` | allows | none | HTTP 403 (refuses our client) | – | no |
| Techweez | KE | en | trade | `techweez.com/feed/` | allows | none | not a feed (bot check or HTML) | – | no |
| The EastAfrican | KE | en | mainstream | `www.theeastafrican.co.ke/tea/rss.xml` | allows | search=yes,ai-train=no,use=reference | HTTP 403 (refuses our client) | – | no |
| WeeTracker | KE | en | trade | `weetracker.com/feed/` | allows | none | works, 3/day | 0.4 | opt. |
| Hespress English | MA | en | mainstream | `en.hespress.com/feed` | allows | none | works, 10/day | 0.0 | no (little AI) |
| Morocco World News | MA | en | mainstream | `www.moroccoworldnews.com/feed/` | allows | none | HTTP 403 (refuses our client) | – | no |
| BusinessDay | NG | en | business | `businessday.ng/feed/` | allows | none | works, 5/day | 1.0 | Step 1 |
| Nairametrics | NG | en | business | `nairametrics.com/feed/` | allows | none | works, 20/day | 1.0 | Step 1 |
| Premium Times | NG | en | mainstream | `www.premiumtimesng.com/feed` | allows | none | works, 15/day | 1.0 | Step 1 |
| Punch | NG | en | mainstream | `punchng.com/feed/` | allows | none | works, 30/day | 0.0 | no (little AI) |
| TechCabal | NG | en | trade | `techcabal.com/feed/` | allows | none | works, 9/day | 0.9 | Step 1 |
| Techeconomy | NG | en | trade | `techeconomy.ng/feed.xml` | allows | search=yes,ai-train=no,use=reference | works, 19/day | 2.6 | Step 1 |
| Techpoint Africa | NG | en | trade | `techpoint.africa/feed/` | allows | none | HTTP 403 (refuses our client) | – | no |
| The Guardian Nigeria | NG | en | mainstream | `guardian.ng/feed/` | allows | none | HTTP 403 (refuses our client) | – | no |
| TheCable | NG | en | mainstream | `www.thecable.ng/feed` | allows | search=yes,ai-train=no,use=reference | HTTP 403 (refuses our client) | – | no |
| allAfrica | ZA | en | aggregator | `allafrica.com/tools/headlines/rdf/latest/headlines.rdf` | allows | none | works, 16/day | 1.0 | later (aggregator) |
| BusinessLIVE | ZA | en | business | `www.businesslive.co.za/rss/` | allows | none | HTTP 404 | – | no |
| BusinessTech | ZA | en | business | `businesstech.co.za/news/feed/` | allows | none | HTTP 403 (refuses our client) | – | no |
| Daily Maverick | ZA | en | mainstream | `www.dailymaverick.co.za/dmrss/` | allows | none | works, 7/day | 0.7 | Step 1 |
| Disrupt Africa | ZA | en | trade | `disruptafrica.com/feed/` | allows | none | works, 3/day | 0.0 | no (little AI) |
| IOL | ZA | en | mainstream | `www.iol.co.za/rss` | allows | none | works, 30/day | 1.0 | Step 1 |
| IT News Africa | ZA | en | trade | `www.itnewsafrica.com/feed/` | allows | none | stale (newest 19 days) | – | no |
| ITWeb | ZA | en | trade | `www.itweb.co.za/rss` | allows | none | works, 4/day | 1.4 | Step 1 |
| Mail & Guardian | ZA | en | mainstream | `mg.co.za/atom/` | allows | none | works, 17/day | 0.3 | opt. |
| MyBroadband | ZA | en | trade | `mybroadband.co.za/news/feed` | allows | none | HTTP 403 (refuses our client) | – | no |
| News24 | ZA | en | mainstream | `feeds.news24.com/articles/news24/TopStories/rss` | unreachable (= disallowed) | none | not fetched | – | no |
| Tech In Africa | ZA | en | trade | `www.techinafrica.com/feed/` | allows | none | works, 1/day | 0.3 | opt. |
| TechCentral | ZA | en | trade | `techcentral.co.za/feed/` | allows | none | works, 10/day | 2.3 | Step 1 |
| The Conversation Africa | ZA | en | opinion | `theconversation.com/africa/articles.atom` | allows | none | works, 2/day | 0.1 | opt. |
| TimesLIVE | ZA | en | mainstream | `www.timeslive.co.za/rss/` | allows | none | HTTP 404 | – | no |

### Middle East (34 checked, 22 with a working feed, 11 in the plan)

| Outlet | Country | Lang | Type | Feed checked | robots.txt | Content-Signal | Feed | AI/day | Plan |
|---|---|---|---|---|---|---|---|---|---|
| Arabian Business | AE | en | business | `www.arabianbusiness.com/feed` | allows | none | HTTP 403 (refuses our client) | – | no |
| Gulf Business | AE | en | business | `gulfbusiness.com/feed/` | allows | search=yes,ai-train=no,use=reference | HTTP 403 (refuses our client) | – | no |
| Gulf News | AE | en | mainstream | `gulfnews.com/feed` | allows | none | works, 6/day | 0.4 | Step 2 |
| Khaleej Times | AE | en | mainstream | `www.khaleejtimes.com/api/v1/collections/entertainment.rss` | allows | none | works, 12/day | 0.0 | no (no tech feed) |
| Sky News Arabia (tech) | AE | ar | mainstream | `www.skynewsarabia.com/rss/technology.xml` | allows | none | works, 6/day | 1.3 | Step 4 |
| The National | AE | en | mainstream | `www.thenationalnews.com/arc/outboundfeeds/rss/?outputType…` | allows | none | works, 59/day | 6.5 | Step 2 |
| WAM (Emirates News Agency) | AE | en | state-aligned | `www.wam.ae/en/rss` | allows | none | not a feed (bot check or HTML) | – | no |
| Wamda | AE | en | trade | `www.wamda.com/feed` | allows | none | works, 2/day | 0.4 | opt. |
| Calcalist (CTech) | IL | en | business | `www.calcalistech.com/ctechnews/rss` | allows | none | HTTP 404 | – | no |
| Globes | IL | en | business | `en.globes.co.il/WebService/Rss/RssFeeder.asmx/FeederNode?…` | allows | none | works, 6/day | 0.9 | Step 2 |
| Haaretz | IL | en | mainstream | `www.haaretz.com/srv/haaretz-latest-headlines` | allows | none | HTTP 403 (refuses our client) | – | no |
| Israel Hayom | IL | en | mainstream | `www.israelhayom.com/feed/` | allows | none | works, 9/day | 0.0 | no (little AI) |
| The Jerusalem Post | IL | en | mainstream | `www.jpost.com/rss/rssfeedsfrontpage.aspx` | allows | none | works, 3/day | 0.1 | opt. |
| The Times of Israel | IL | en | mainstream | `www.timesofisrael.com/feed/` | **disallows feed** | none | not fetched | – | no |
| Ynetnews | IL | en | mainstream | `www.ynetnews.com/Integration/StoryRss3082.xml` | allows | none | works, 5/day | 0.2 | no (little AI) |
| Tehran Times | IR | en | state-aligned | `www.tehrantimes.com/rss` | allows | none | works, 30/day | 0.0 | no (little AI) |
| L'Orient Today | LB | en | mainstream | `today.lorientlejour.com/rss` | allows | none | HTTP 404 | – | no |
| Al Jazeera (science and technology) | QA | en | mainstream | `www.aljazeera.com/xml/rss/all.xml?tag=technology` | allows | none | works, 25/day | 3.0 | no (outlet already in) |
| Al Jazeera Arabic | QA | ar | mainstream | `www.aljazeera.net/aljazeerarss/a7c186be-1baa-4bd4-9d80-a8…` | allows | none | works, 25/day | 0.0 | no (little AI) |
| The Peninsula | QA | en | mainstream | `thepeninsulaqatar.com/rss` | allows | none | not a feed (bot check or HTML) | – | no |
| AITNews (البوابة العربية للأخبار التقنية) | SA | ar | trade | `aitnews.com/feed/` | allows | none | works, 10/day | 5.0 | Step 4 |
| Al Arabiya English | SA | en | state-aligned | `english.alarabiya.net/feed/rss2/en/technology.xml` | allows | none | HTTP 403 (refuses our client) | – | no |
| Arab News | SA | en | state-aligned | `www.arabnews.com/rss.xml` | allows | none | HTTP 403 (refuses our client) | – | no |
| Asharq Al-Awsat (Arabic) | SA | ar | state-aligned | `aawsat.com/feed` | allows | none | works, 214/day | 7.7 | no (same outlet as English edition) |
| Asharq Al-Awsat (English) | SA | en | state-aligned | `english.aawsat.com/feed/` | allows | none | works, 54/day | 3.0 | Step 2 |
| Saudi Gazette | SA | en | state-aligned | `saudigazette.com.sa/rssFeed/74` | allows | none | works, 13/day | 0.8 | Step 2 |
| Tech-WD (عالم التقنية) | SA | ar | trade | `www.tech-wd.com/wd/feed/` | allows | none | works, 15/day | 3.0 | Step 4 |
| Anadolu Agency | TR | en | wire | `www.aa.com.tr/en/rss/default?cat=science-technology` | allows | none | works, 2/day | 1.3 | Step 2 |
| Daily Sabah | TR | en | state-aligned | `www.dailysabah.com/rss/business/tech` | allows | none | works, 4/day | 2.6 | Step 2 |
| Hürriyet Daily News | TR | en | mainstream | `www.hurriyetdailynews.com/rss.aspx` | allows | none | works, 3/day | 0.0 | no (little AI) |
| NTV (Turkey), technology | TR | tr | mainstream | `www.ntv.com.tr/teknoloji.rss` | allows | none | HTTP 403 (refuses our client) | – | no |
| ShiftDelete.Net | TR | tr | trade | `shiftdelete.net/feed` | allows | ai-train=yes,search=yes,ai-input=yes | works, 31/day | 7.6 | Step 4 |
| TRT World | TR | en | state-aligned | `www.trtworld.com/feed/rss.xml` | allows | none | works, 38/day | 1.9 | opt. (state) |
| Webrazzi | TR | tr | trade | `webrazzi.com/feed/` | **disallows feed** | none | not fetched | – | no |

### South Asia (24 checked, 15 with a working feed, 11 in the plan)

| Outlet | Country | Lang | Type | Feed checked | robots.txt | Content-Signal | Feed | AI/day | Plan |
|---|---|---|---|---|---|---|---|---|---|
| The Daily Star | BD | en | mainstream | `www.thedailystar.net/tech-startup/rss.xml` | allows | none | works, 6/day | 3.6 | Step 3 |
| Amar Ujala (tech) | IN | hi | mainstream | `www.amarujala.com/rss/technology.xml` | allows | none | works, 12/day | 3.2 | Step 4 |
| Analytics India Magazine | IN | en | trade | `analyticsindiamag.com/feed/` | allows | none | works, 8/day | 6.3 | Step 3 |
| Business Standard | IN | en | business | `www.business-standard.com/rss/technology-108.rss` | allows | none | HTTP 403 (refuses our client) | – | no |
| Dainik Jagran (tech) | IN | hi | mainstream | `www.jagran.com/rss/technology.xml` | allows | none | HTTP 404 | – | no |
| Entrackr | IN | en | trade | `entrackr.com/rss` | allows | none | works, 5/day | 1.1 | opt. |
| Gadgets 360 (NDTV) | IN | en | trade | `feeds.feedburner.com/gadgets360-latest` | allows | none | works, 20/day | 2.3 | opt. |
| Hindustan Times | IN | en | mainstream | `www.hindustantimes.com/feeds/rss/technology/rssfeed.xml` | allows | none | works, 6/day | 0.0 | no (little AI) |
| Inc42 | IN | en | trade | `inc42.com/feed/` | allows | search=yes,ai-input=yes,ai-train=no | works, 24/day | 5.0 | Step 3 |
| MediaNama | IN | en | trade | `www.medianama.com/feed/` | **disallows feed** | search=yes,ai-train=no,use=reference | not fetched | – | no |
| Mint | IN | en | business | `www.livemint.com/rss/technology` | allows | none | works, 9/day | 3.9 | Step 3 |
| Moneycontrol | IN | en | business | `www.moneycontrol.com/rss/technology.xml` | allows | none | HTTP 403 (refuses our client) | – | no |
| NDTV India (Hindi) | IN | hi | mainstream | `feeds.feedburner.com/ndtvkhabar-latest` | allows | none | works, 100/day | 5.0 | Step 4 |
| News18 Hindi (tech) | IN | hi | mainstream | `hindi.news18.com/rss/khabar/tech/tech.xml` | allows | none | HTTP 403 (refuses our client) | – | no |
| Scroll.in | IN | en | mainstream | `feeds.feedburner.com/ScrollinArticles.rss` | allows | none | works, 21/day | 0.6 | Step 3 |
| The Hindu | IN | en | mainstream | `www.thehindu.com/sci-tech/technology/feeder/default.rss` | allows | none | works, 10/day | 6.0 | Step 3 |
| The Indian Express | IN | en | mainstream | `indianexpress.com/section/technology/feed/` | allows | none | works, 6/day | 3.4 | Step 3 |
| The Times of India | IN | en | mainstream | `timesofindia.indiatimes.com/rssfeeds/66949542.cms` | allows | none | stale (newest 50 days) | – | no |
| The Wire | IN | en | mainstream | `thewire.in/rss` | allows | none | not a feed (bot check or HTML) | – | no |
| ThePrint | IN | en | mainstream | `theprint.in/feed/` | allows | none | not a feed (bot check or HTML) | – | no |
| EconomyNext | LK | en | business | `economynext.com/feed/` | allows | none | HTTP 403 (refuses our client) | – | no |
| Dawn | PK | en | mainstream | `www.dawn.com/feeds/home` | allows | none | works, 26/day | 2.0 | Step 3 |
| ProPakistani | PK | en | trade | `propakistani.pk/feed/` | allows | none | works, 10/day | 0.0 | no (little AI) |
| The Express Tribune | PK | en | mainstream | `tribune.com.pk/feed/technology` | allows | none | works, 1/day | 0.6 | Step 3 |

### East Asia (43 checked, 27 with a working feed, 17 in the plan)

| Outlet | Country | Lang | Type | Feed checked | robots.txt | Content-Signal | Feed | AI/day | Plan |
|---|---|---|---|---|---|---|---|---|---|
| 36Kr | CN | zh | trade | `36kr.com/feed` | allows | none | not a feed (bot check or HTML) | – | no |
| China News Service (ECNS) | CN | en | state-aligned | `www.ecns.cn/rss/rss.xml` | allows | none | works, 14/day | 1.5 | opt. (state) |
| cnBeta | CN | zh | trade | `www.cnbeta.com.tw/backend.php` | allows | none | works, 68/day | 20.1 | opt. |
| IT之家 (ITHome) | CN | zh | trade | `www.ithome.com/rss/` | allows | none | works, 60/day | 17.0 | Step 4 |
| People's Daily (English), sci-tech | CN | en | state-aligned | `en.people.cn/rss/90882.xml` | allows | none | stale (newest 539 days) | – | no |
| Sixth Tone | CN | en | state-aligned | `www.sixthtone.com/rss` | allows | none | works, 51/day | 6.0 | Step 3 |
| Solidot | CN | zh | trade | `www.solidot.org/index.rss` | allows | none | works, 10/day | 2.5 | opt. |
| Yicai Global | CN | en | business | `www.yicaiglobal.com/rss` | allows | none | HTTP 404 | – | no |
| 人民网 (People's Daily), IT | CN | zh | state-aligned | `www.people.com.cn/rss/it.xml` | allows | none | stale (newest 876 days) | – | no |
| 机器之心 (Synced) | CN | zh | trade | `www.jiqizhixin.com/rss` | allows | none | not a feed (bot check or HTML) | – | no |
| 虎嗅 (Huxiu) | CN | zh | trade | `www.huxiu.com/rss/0.xml` | allows | none | ReadTimeout: The read operation timed ou | – | no |
| 量子位 (QbitAI) | CN | zh | trade | `www.qbitai.com/feed` | allows | none | works, 10/day | 8.0 | Step 4 |
| Hong Kong Free Press | HK | en | mainstream | `hongkongfp.com/feed/` | allows | none | works, 5/day | 0.3 | opt. |
| RTHK | HK | en | public-broadcaster | `rthk9.rthk.hk/rthk/news/rss/e_expressnews_elocal.xml` | allows | none | works, 12/day | 0.6 | opt. |
| Asahi Shimbun | JP | ja | mainstream | `www.asahi.com/rss/asahi/newsheadlines.rdf` | allows | none | works, 21/day | 0.0 | opt. |
| GIGAZINE | JP | ja | trade | `gigazine.net/news/rss_2.0/` | allows | none | works, 30/day | 15.0 | Step 4 |
| Impress Watch | JP | ja | trade | `www.watch.impress.co.jp/data/rss/1.0/ipw/feed.rdf` | allows | none | works, 20/day | 1.9 | Step 4 |
| ITmedia AI+ | JP | ja | trade | `rss.itmedia.co.jp/rss/2.0/aiplus.xml` | allows | none | works, 14/day | 13.3 | Step 4 |
| Kyodo News | JP | en | wire | `english.kyodonews.net/rss/all.xml` | allows | none | HTTP 404 | – | no |
| NHK | JP | ja | public-broadcaster | `www.nhk.or.jp/rss/news/cat0.xml` | **disallows feed** | none | not fetched | – | no |
| NHK World | JP | en | public-broadcaster | `www3.nhk.or.jp/nhkworld/data/en/news/backstories/rss.xml` | allows | none | HTTP 404 | – | no |
| Nikkei xTECH | JP | ja | trade | `xtech.nikkei.com/rss/index.rdf` | allows | none | works, 67/day | 13.9 | Step 4 |
| Nippon.com | JP | en | mainstream | `www.nippon.com/en/rss/` | allows | none | HTTP 404 | – | no |
| The Japan News (Yomiuri) | JP | en | mainstream | `japannews.yomiuri.co.jp/feed/` | allows | none | empty feed | – | no |
| The Japan Times | JP | en | mainstream | `www.japantimes.co.jp/feed/` | allows | none | works, 30/day | 1.0 | opt. (all-news) |
| The Mainichi (English) | JP | en | mainstream | `mainichi.jp/english/rss/etc/english.rss` | allows | none | not a feed (bot check or HTML) | – | no |
| AI Times (Korea) | KR | ko | trade | `www.aitimes.com/rss/allArticle.xml` | allows | none | works, 50/day | 42.0 | Step 4 |
| BusinessKorea | KR | en | business | `www.businesskorea.co.kr/rss/allArticle.xml` | allows | none | works, 50/day | 4.0 | opt. |
| Chosun Ilbo | KR | ko | mainstream | `www.chosun.com/arc/outboundfeeds/rss/?outputType=xml` | allows | none | works, 34/day | 3.1 | Step 4 |
| Electronic Times (etnews) | KR | ko | trade | `rss.etnews.com/Section901.xml` | allows | none | works, 30/day | 9.0 | Step 4 |
| KED Global | KR | en | business | `www.kedglobal.com/newsRss` | allows | none | empty feed | – | no |
| Korea JoongAng Daily | KR | en | mainstream | `koreajoongangdaily.joins.com/xmls/joins_rss.xml` | allows | none | HTTP 404 | – | no |
| The Elec | KR | en | trade | `www.thelec.net/rss/allArticle.xml` | allows | none | works, 50/day | 10.0 | Step 3 |
| The Hankyoreh | KR | ko | mainstream | `www.hani.co.kr/rss/` | allows | none | works, 30/day | 0.0 | opt. |
| The Hankyoreh (English) | KR | en | mainstream | `english.hani.co.kr/rss/` | allows | none | works, 30/day | 0.0 | no (little AI) |
| The Korea Times | KR | en | mainstream | `www.koreatimes.co.kr/www/rss/rss.xml` | allows | none | works, 114/day | 20.0 | Step 3 |
| Yonhap News Agency | KR | en | wire | `en.yna.co.kr/RSS/news.xml` | allows | none | works, 103/day | 11.0 | Step 3 |
| ZDNet Korea | KR | ko | trade | `feeds.feedburner.com/zdkorea` | allows | none | works, 30/day | 14.0 | Step 4 |
| DigiTimes Asia | TW | en | trade | `www.digitimes.com/rss/daily.xml` | allows | none | works, 43/day | 18.0 | Step 3 |
| Focus Taiwan (CNA) | TW | en | wire | `focustaiwan.tw/rss/sci-tech.xml` | allows | search=yes,ai-input=yes,ai-train=no | HTTP 404 | – | no |
| iThome | TW | zh | trade | `www.ithome.com.tw/rss` | allows | search=yes,ai-input=yes,ai-train=no | works, 23/day | 8.0 | Step 4 |
| Taipei Times | TW | en | mainstream | `www.taipeitimes.com/xml/index.rss` | allows | none | works, 50/day | 3.0 | Step 3 |
| TechNews 科技新報 | TW | zh | trade | `technews.tw/feed/` | allows | none | HTTP 403 (refuses our client) | – | no |

### Southeast Asia (30 checked, 18 with a working feed, 10 in the plan)

| Outlet | Country | Lang | Type | Feed checked | robots.txt | Content-Signal | Feed | AI/day | Plan |
|---|---|---|---|---|---|---|---|---|---|
| Antara (English) | ID | en | wire | `en.antaranews.com/rss/news.xml` | allows | none | works, 50/day | 4.0 | Step 3 |
| CNN Indonesia | ID | id | mainstream | `www.cnnindonesia.com/teknologi/rss` | allows | none | works, 16/day | 4.1 | Step 4 |
| DailySocial | ID | id | trade | `dailysocial.id/feed` | allows | none | works, 0/day | 0.0 | no (little AI) |
| detikInet | ID | id | mainstream | `rss.detik.com/index.php/inet` | unreachable (= disallowed) | none | not fetched | – | no |
| Kompas Tekno | ID | id | mainstream | `tekno.kompas.com/rss` | allows | none | HTTP 404 | – | no |
| Tempo English | ID | en | mainstream | `en.tempo.co/rss/business` | allows | search=yes,ai-train=no,use=reference | HTTP 403 (refuses our client) | – | no |
| The Jakarta Post | ID | en | mainstream | `www.thejakartapost.com/rss` | allows | none | HTTP 404 | – | no |
| Khmer Times | KH | en | mainstream | `www.khmertimeskh.com/feed/` | allows | none | HTTP 403 (refuses our client) | – | no |
| Free Malaysia Today | MY | en | mainstream | `www.freemalaysiatoday.com/feed/` | allows | none | works, 50/day | 3.0 | Step 3 |
| Malay Mail | MY | en | mainstream | `www.malaymail.com/feed/rss/tech-gadgets` | allows | none | works, 2/day | 0.7 | opt. |
| New Straits Times | MY | en | mainstream | `www.nst.com.my/feed` | allows | **ai-input=no** | works, 50/day | 4.0 | no (ai-input=no) |
| The Star (Malaysia) | MY | en | mainstream | `www.thestar.com.my/rss/Tech/Tech-News` | allows | none | HTTP 404 | – | no |
| BusinessWorld | PH | en | business | `www.bworldonline.com/feed/` | allows | none | works, 30/day | 2.0 | Step 3 |
| GMA News | PH | en | mainstream | `data.gmanetwork.com/gno/rss/scitech/feed.xml` | allows | none | works, 2/day | 0.3 | opt. |
| Inquirer Technology | PH | en | mainstream | `technology.inquirer.net/feed` | allows | none | works, 2/day | 0.6 | opt. |
| Rappler | PH | en | mainstream | `www.rappler.com/technology/feed/` | allows | none | works, 4/day | 3.0 | Step 3 |
| CNA | SG | en | public-broadcaster | `www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=…` | allows | none | works, 20/day | 7.0 | Step 3 |
| e27 | SG | en | trade | `e27.co/feed/` | allows | none | works, 8/day | 4.0 | Step 3 |
| Tech in Asia | SG | en | trade | `www.techinasia.com/feed` | allows | none | HTTP 403 (refuses our client) | – | no |
| The Business Times | SG | en | business | `www.businesstimes.com.sg/rss/technology` | allows | none | works, 2/day | 1.5 | opt. |
| The Straits Times (tech) | SG | en | mainstream | `www.straitstimes.com/news/tech/rss.xml` | allows | none | HTTP 400 | – | no (outlet already in; HTTP 400) |
| Bangkok Post | TH | en | mainstream | `www.bangkokpost.com/rss/data/business.xml` | allows | none | works, 10/day | 3.0 | Step 3 |
| Blognone | TH | th | trade | `www.blognone.com/atom.xml` | allows | none | works, 1/day | 0.6 | opt. |
| Khaosod English | TH | en | mainstream | `www.khaosodenglish.com/feed/` | allows | none | works, 5/day | 0.0 | no (little AI) |
| Thai PBS World | TH | en | public-broadcaster | `www.thaipbsworld.com/feed/` | allows | none | not a feed (bot check or HTML) | – | no |
| The Nation Thailand | TH | en | mainstream | `www.nationthailand.com/rss` | allows | none | empty feed | – | no |
| Tuổi Trẻ | VN | vi | mainstream | `tuoitre.vn/rss/cong-nghe.rss` | allows | none | works, 50/day | 29.0 | Step 4 |
| VietnamPlus (English) | VN | en | state-aligned | `en.vietnamplus.vn/rss/home.rss` | allows | none | works, 50/day | 2.0 | Step 3 |
| VnExpress (Số hóa) | VN | vi | mainstream | `vnexpress.net/rss/so-hoa.rss` | allows | none | HTTP 404 | – | no |
| VnExpress International | VN | en | mainstream | `e.vnexpress.net/rss/news.rss` | allows | none | works, 9/day | 0.4 | opt. |

### Oceania (18 checked, 13 with a working feed, 7 in the plan)

| Outlet | Country | Lang | Type | Feed checked | robots.txt | Content-Signal | Feed | AI/day | Plan |
|---|---|---|---|---|---|---|---|---|---|
| ABC News (Australia), science and technology | AU | en | public-broadcaster | `www.abc.net.au/news/feed/2942460/rss.xml` | allows | none | works, 11/day | 0.0 | no (outlet already in) |
| Crikey | AU | en | opinion | `www.crikey.com.au/feed/` | allows | none | works, 8/day | 0.8 | Step 2 |
| InnovationAus | AU | en | trade | `www.innovationaus.com/feed/` | allows | search=yes,ai-train=no,use=reference | HTTP 403 (refuses our client) | – | no |
| IT Brief Australia | AU | en | trade | `itbrief.com.au/feed` | allows | none | works, 10/day | 10.0 | opt. (PR-heavy) |
| iTnews | AU | en | trade | `www.itnews.com.au/RSS/rss.ashx` | allows | none | works, 6/day | 1.1 | Step 2 |
| news.com.au | AU | en | mainstream | `www.news.com.au/technology/rss` | **disallows feed** | none | not fetched | – | no |
| SBS News | AU | en | public-broadcaster | `www.sbs.com.au/news/topic/technology/feed` | allows | none | HTTP 404 | – | no |
| Startup Daily | AU | en | trade | `www.startupdaily.net/feed/` | allows | none | works, 5/day | 0.9 | Step 2 |
| The Conversation (Australia) | AU | en | opinion | `theconversation.com/au/technology/articles.atom` | allows | none | works, 1/day | 0.3 | opt. |
| The Sydney Morning Herald | AU | en | mainstream | `www.smh.com.au/rss/technology.xml` | allows | none | works, 1/day | 0.6 | Step 2 |
| The Fiji Times | FJ | en | mainstream | `www.fijitimes.com.fj/feed/` | allows | none | not a feed (bot check or HTML) | – | no |
| 1News (TVNZ) | NZ | en | public-broadcaster | `www.1news.co.nz/arc/outboundfeeds/rss/?outputType=xml` | allows | none | works, 41/day | 1.2 | Step 2 |
| Newsroom | NZ | en | mainstream | `newsroom.co.nz/feed/` | allows | search=yes,ai-train=no,use=reference | works, 15/day | 4.0 | Step 2 |
| NZ Herald | NZ | en | mainstream | `www.nzherald.co.nz/arc/outboundfeeds/rss/section/business…` | allows | none | works, 10/day | 0.0 | no (little AI) |
| RNZ | NZ | en | public-broadcaster | `www.rnz.co.nz/rss/business.xml` | allows | none | works, 15/day | 1.0 | Step 2 |
| RNZ Pacific | NZ | en | public-broadcaster | `www.rnz.co.nz/rss/pacific.xml` | allows | none | works, 6/day | 0.0 | opt. |
| Stuff | NZ | en | mainstream | `www.stuff.co.nz/rss` | allows | none | works, 11/day | 0.3 | opt. |
| The Spinoff | NZ | en | opinion | `thespinoff.co.nz/feed` | allows | none | HTTP 404 | – | no |

### North America (9 checked, 8 with a working feed, 5 in the plan)

| Outlet | Country | Lang | Type | Feed checked | robots.txt | Content-Signal | Feed | AI/day | Plan |
|---|---|---|---|---|---|---|---|---|---|
| BetaKit | CA | en | trade | `betakit.com/feed/` | allows | none | works, 5/day | 1.6 | Step 2 |
| CTV News | CA | en | mainstream | `www.ctvnews.ca/rss/ctvnews-ca-sci-tech-public-rss-1.822295` | **disallows feed** | none | not fetched | – | no |
| Global News | CA | en | mainstream | `globalnews.ca/tech/feed/` | allows | none | works, 1/day | 1.0 | Step 2 |
| La Presse | CA | fr | mainstream | `www.lapresse.ca/affaires/techno/rss` | allows | none | works, 1/day | 0.9 | Step 2 |
| Le Devoir | CA | fr | mainstream | `www.ledevoir.com/rss/manchettes.xml` | allows | none | works, 7/day | 0.2 | opt. |
| Radio-Canada | CA | fr | public-broadcaster | `ici.radio-canada.ca/rss/5717` | allows | none | works, 33/day | 3.3 | Step 2 |
| The Globe and Mail | CA | en | mainstream | `www.theglobeandmail.com/arc/outboundfeeds/rss/category/bu…` | allows | none | works, 2/day | 1.0 | Step 2 |
| Al-Monitor | US | en | mainstream | `www.al-monitor.com/rss` | allows | none | works, 20/day | 0.0 | no (little AI) |
| Bloomberg Línea | US | es | business | `www.bloomberglinea.com/arc/outboundfeeds/rss/?outputType=xml` | allows | none | works, 14/day | 2.0 | opt. (Miami HQ: country?) |

### Europe (86 checked, 70 with a working feed, 38 in the plan)

| Outlet | Country | Lang | Type | Feed checked | robots.txt | Content-Signal | Feed | AI/day | Plan |
|---|---|---|---|---|---|---|---|---|---|
| Der Standard | AT | de | mainstream | `www.derstandard.at/rss/web` | allows | none | works, 9/day | 4.2 | Step 5 |
| futurezone | AT | de | trade | `futurezone.at/xml/rss` | allows | none | works, 10/day | 4.2 | opt. |
| ORF | AT | de | public-broadcaster | `rss.orf.at/news.xml` | allows | none | works, 24/day | 2.0 | Step 5 |
| EUobserver | BE | en | mainstream | `euobserver.com/feed/` | allows | none | works, 12/day | 2.4 | Step 5 |
| Science\|Business | BE | en | trade | `sciencebusiness.net/rss.xml` | allows | none | HTTP 404 | – | no |
| Tech.eu | BE | en | trade | `tech.eu/feed/` | **disallows feed** | none | not fetched | – | no |
| The Brussels Times | BE | en | mainstream | `www.brusselstimes.com/feed` | allows | none | not a feed (bot check or HTML) | – | no |
| VRT NWS (English) | BE | en | public-broadcaster | `www.vrt.be/vrtnws/en.rss.articles.xml` | allows | none | works, 4/day | 0.1 | opt. |
| Neue Zürcher Zeitung | CH | de | mainstream | `www.nzz.ch/technologie.rss` | allows | none | works, 1/day | 1.0 | Step 5 |
| SRF | CH | de | public-broadcaster | `www.srf.ch/news/bnf/rss/1922` | allows | none | works, 12/day | 0.6 | Step 5 |
| Swissinfo | CH | en | public-broadcaster | `www.swissinfo.ch/eng/rss` | allows | none | HTTP 410 | – | no |
| iROZHLAS | CZ | cs | public-broadcaster | `www.irozhlas.cz/rss/irozhlas` | allows | search=yes,ai-train=no,use=reference | works, 20/day | 0.0 | no (little AI) |
| Lupa.cz | CZ | cs | trade | `www.lupa.cz/rss/clanky/` | allows | none | works, 3/day | 0.7 | Step 6 |
| AlgorithmWatch | DE | en | opinion | `algorithmwatch.org/en/feed/` | allows | none | works, 0/day | 0.1 | opt. (low volume) |
| Die Zeit | DE | de | mainstream | `newsfeed.zeit.de/digital/index` | **disallows feed** | none | not fetched | – | no |
| Frankfurter Allgemeine | DE | de | mainstream | `www.faz.net/rss/aktuell/` | allows | none | works, 19/day | 1.4 | Step 5 |
| Golem.de | DE | de | trade | `rss.golem.de/rss.php?feed=RSS2.0` | allows | none | works, 38/day | 5.0 | opt. |
| netzpolitik.org | DE | de | trade | `netzpolitik.org/feed/` | **disallows feed** | none | not fetched | – | no |
| Süddeutsche Zeitung | DE | de | mainstream | `rss.sueddeutsche.de/rss/Digital` | allows | none | works, 1/day | 0.9 | Step 5 |
| t3n | DE | de | trade | `t3n.de/rss.xml` | allows | none | works, 20/day | 10.0 | Step 5 |
| tagesschau | DE | de | public-broadcaster | `www.tagesschau.de/wirtschaft/index~rss2.xml` | allows | none | works, 4/day | 0.7 | opt. |
| taz | DE | de | mainstream | `taz.de/!p4608;rss/` | allows | none | works, 50/day | 1.0 | opt. |
| DR | DK | da | public-broadcaster | `www.dr.dk/nyheder/service/feeds/allenyheder` | allows | none | works, 20/day | 1.0 | Step 6 |
| Version2 | DK | da | trade | `www.version2.dk/rss` | allows | none | works, 3/day | 1.9 | Step 6 |
| ERR News | EE | en | public-broadcaster | `news.err.ee/rss` | allows | none | works, 26/day | 2.1 | Step 6 |
| El Confidencial | ES | es | mainstream | `rss.elconfidencial.com/tecnologia/` | allows | none | works, 2/day | 0.0 | no (little AI) |
| El País América | ES | es | mainstream | `feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/…` | allows | none | works, 14/day | 1.1 | no (El País already in) |
| elDiario.es | ES | es | mainstream | `www.eldiario.es/rss/` | allows | none | works, 14/day | 0.4 | opt. |
| Hipertextual | ES | es | trade | `hipertextual.com/feed` | allows | none | works, 9/day | 1.2 | opt. |
| La Vanguardia | ES | es | mainstream | `www.lavanguardia.com/rss/home.xml` | allows | none | works, 20/day | 0.6 | opt. |
| RTVE | ES | es | public-broadcaster | `api2.rtve.es/rss/temas_tecnologia.xml` | **disallows feed** | none | not fetched | – | no |
| Xataka | ES | es | trade | `www.xataka.com/feedburner.xml` | allows | none | works, 30/day | 5.0 | Step 5 |
| Helsingin Sanomat | FI | fi | mainstream | `www.hs.fi/rss/tuoreimmat.xml` | allows | none | works, 91/day | 3.8 | Step 6 |
| Yle News | FI | en | public-broadcaster | `feeds.yle.fi/uutiset/v1/recent.rss?publisherIds=YLE_NEWS` | allows | none | works, 3/day | 0.0 | opt. |
| ActuIA | FR | fr | trade | `www.actuia.com/feed/` | allows | none | works, 2/day | 2.1 | opt. |
| franceinfo | FR | fr | public-broadcaster | `www.francetvinfo.fr/internet.rss` | allows | none | works, 11/day | 6.8 | Step 5 |
| Jeune Afrique | FR | fr | mainstream | `www.jeuneafrique.com/feed/` | allows | none | works, 12/day | 0.0 | no (little AI) |
| L'Usine Digitale | FR | fr | trade | `www.usine-digitale.fr/rss` | **disallows feed** | none | not fetched | – | no |
| Le Figaro | FR | fr | mainstream | `www.lefigaro.fr/rss/figaro_secteur_high-tech.xml` | allows | none | works, 3/day | 2.1 | Step 5 |
| Le Monde Afrique | FR | fr | mainstream | `www.lemonde.fr/afrique/rss_full.xml` | allows | none | works, 7/day | 0.0 | no (little AI) |
| Les Echos | FR | fr | business | `services.lesechos.fr/rss/les-echos-tech-medias.xml` | allows | none | HTTP 403 (refuses our client) | – | no |
| Libération | FR | fr | mainstream | `www.liberation.fr/arc/outboundfeeds/rss/?outputType=xml` | allows | none | works, 50/day | 4.0 | Step 5 |
| Numerama | FR | fr | trade | `www.numerama.com/feed/` | allows | none | works, 15/day | 0.0 | opt. |
| RFI Afrique | FR | fr | public-broadcaster | `www.rfi.fr/fr/afrique/rss` | allows | none | works, 19/day | 0.0 | no (little AI) |
| The Africa Report | FR | en | business | `www.theafricareport.com/feed/` | allows | none | works, 6/day | 0.0 | no (little AI) |
| Iran International | GB | en | mainstream | `www.iranintl.com/en/feed` | allows | none | works, 10/day | 0.2 | no (little AI) |
| Middle East Eye | GB | en | mainstream | `www.middleeasteye.net/rss` | allows | none | works, 20/day | 0.0 | no (little AI) |
| Kathimerini (English) | GR | en | mainstream | `www.ekathimerini.com/rss` | allows | none | HTTP 403 (refuses our client) | – | no |
| Telex | HU | hu | mainstream | `telex.hu/rss` | allows | none | works, 50/day | 2.0 | Step 6 |
| RTÉ | IE | en | public-broadcaster | `www.rte.ie/feeds/rss/?index=/news/business/` | allows | none | works, 22/day | 3.9 | Step 5 |
| Silicon Republic | IE | en | trade | `www.siliconrepublic.com/feed` | allows | none | HTTP 403 (refuses our client) | – | no |
| The Irish Times | IE | en | mainstream | `www.irishtimes.com/arc/outboundfeeds/feed-business/?outpu…` | allows | none | works, 16/day | 3.3 | Step 5 |
| TheJournal.ie | IE | en | mainstream | `www.thejournal.ie/feed/` | **disallows feed** | none | not fetched | – | no |
| AGI | IT | it | wire | `www.agi.it/innovazione/rss` | allows | none | works, 1/day | 0.7 | opt. |
| ANSA | IT | it | wire | `www.ansa.it/sito/ansait_rss.xml` | allows | none | works, 18/day | 0.6 | Step 5 |
| Corriere della Sera | IT | it | mainstream | `xml2.corriereobjects.it/rss/tecnologia.xml` | allows | **ai-input=no** | stale (newest 1612 days) | – | no |
| Il Post | IT | it | mainstream | `www.ilpost.it/feed/` | allows | none | HTTP 403 (refuses our client) | – | no |
| Il Sole 24 Ore | IT | it | business | `www.ilsole24ore.com/rss/tecnologia.xml` | allows | none | works, 1/day | 0.7 | Step 5 |
| la Repubblica | IT | it | mainstream | `www.repubblica.it/rss/tecnologia/rss2.0.xml` | allows | none | works, 4/day | 2.8 | Step 5 |
| Punto Informatico | IT | it | trade | `www.punto-informatico.it/feed/` | allows | none | works, 20/day | 4.0 | Step 5 |
| Wired Italia | IT | it | trade | `www.wired.it/feed/rss` | allows | none | stale (newest 148 days) | – | no |
| LSM (Latvia) | LV | en | public-broadcaster | `eng.lsm.lv/rss/` | allows | none | works, 16/day | 0.0 | no (little AI) |
| Meduza | LV | en | mainstream | `meduza.io/rss/en/all` | allows | none | works, 18/day | 0.0 | opt. |
| de Volkskrant | NL | nl | mainstream | `www.volkskrant.nl/tech/rss.xml` | allows | none | works, 1/day | 0.6 | opt. |
| Het Financieele Dagblad | NL | nl | business | `fd.nl/?rss` | allows | none | works, 5/day | 0.7 | Step 5 |
| NOS | NL | nl | public-broadcaster | `feeds.nos.nl/nosnieuwstech` | allows | none | works, 1/day | 0.7 | Step 5 |
| NRC | NL | nl | mainstream | `www.nrc.nl/rss/` | allows | none | works, 18/day | 1.0 | Step 5 |
| The Moscow Times | NL | en | mainstream | `www.themoscowtimes.com/rss/news` | allows | none | works, 8/day | 0.2 | opt. |
| Tweakers | NL | nl | trade | `tweakers.net/feeds/mixed.xml` | allows | none | works, 24/day | 8.2 | Step 5 |
| Digi.no | NO | no | trade | `www.digi.no/rss` | allows | none | works, 6/day | 2.1 | Step 6 |
| E24 | NO | no | business | `e24.no/rss2/` | allows | none | works, 23/day | 4.8 | Step 6 |
| NRK | NO | no | public-broadcaster | `www.nrk.no/toppsaker.rss` | allows | none | works, 19/day | 0.2 | Step 6 |
| Notes from Poland | PL | en | mainstream | `notesfrompoland.com/feed/` | allows | none | works, 2/day | 0.0 | no (little AI) |
| Rzeczpospolita | PL | pl | mainstream | `www.rp.pl/rss_main` | allows | none | works, 20/day | 1.0 | Step 6 |
| Spider's Web | PL | pl | trade | `spidersweb.pl/feed` | allows | none | works, 31/day | 2.5 | Step 6 |
| TVN24 | PL | pl | mainstream | `tvn24.pl/najnowsze.xml` | allows | none | works, 13/day | 0.6 | Step 6 |
| ECO | PT | pt | business | `eco.sapo.pt/feed/` | allows | none | works, 22/day | 2.0 | Step 5 |
| Observador | PT | pt | mainstream | `observador.pt/feed/` | allows | none | works, 51/day | 3.0 | Step 5 |
| Público | PT | pt | mainstream | `feeds.feedburner.com/PublicoRSS` | allows | none | works, 10/day | 0.0 | no (little AI) |
| G4Media | RO | ro | mainstream | `www.g4media.ro/feed` | allows | none | works, 30/day | 0.0 | no (little AI) |
| Habr (AI hub) | RU | ru | trade | `habr.com/ru/rss/hub/artificial_intelligence/` | allows | none | works, 40/day | 33.0 | no (user blogs) |
| Kommersant | RU | ru | business | `www.kommersant.ru/RSS/section-hitech.xml` | allows | none | empty feed | – | no |
| TASS | RU | en | state-aligned | `tass.com/rss/v2.xml` | allows | none | works, 100/day | 3.0 | Step 6 |
| DOU | UA | uk | trade | `dou.ua/feed/` | allows | none | works, 5/day | 1.0 | Step 6 |
| The Kyiv Independent | UA | en | mainstream | `kyivindependent.com/news-archive/rss/` | allows | none | works, 15/day | 0.0 | opt. |
| Ukrainska Pravda | UA | en | mainstream | `www.pravda.com.ua/eng/rss/` | allows | none | works, 20/day | 0.0 | opt. |
