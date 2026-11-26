# Desks (2026-11-26)

The site grew from one subject (AI) to five **desks**: AI, Energy, Biotech & health tech, Space, and Agriculture &
food supply. Each desk is a full copy of the page: its own stories, sentiment, map, narratives, index, archive and
day's line. Stance always means stance toward that desk's own subject, so desks are never averaged together.

Benjamin chose layout draft A of two (a desk row under the nameplate, AI stays the front page) over B (a front page
across desks, AI moved to /ai/).

## What the data said first

Over three days the outlets sent 3,996 news items, but only 76 about energy, 56 space, 49 biotech and 22 food:
most outlets were read through their technology feed. So every desk needed its own feeds.

## Sources (verified 2026-11-26)

Each feed was fetched with the project's own client (robots.txt, generic user agent, one fetch) and checked for
recent items and content signals. None asks for `ai-input=no`; The Atlantic's new feeds keep its `llm: false`.

- **89 section feeds of 48 outlets we already read** (climate, energy, health, science, space, agriculture).
  They carry no `desk:`; relevance sorts each item.
- **42 specialist outlets** (`group: desk-<key>`). 33 carry `desk:` and skip the relevance call. Official bodies
  (NASA, ESA, FDA, EMA, FAO, IAEA) and outlets that mix in other subjects (STAT, Korea Biomedical Review, OilPrice)
  have no `desk:` and are sorted by relevance.
- Rough volume before relevance: energy ~130 items a day, biotech ~170 (much general health, which relevance drops),
  space ~20 plus ~80 from mixed science feeds, food ~160.
- Blocked with 403 and left out (not worked around): Fierce Biotech, Fierce Pharma, Endpoints, Civil Eats,
  Farmers Weekly UK, Successful Farming, AgWeb, ESI Africa, Energy Voice, USDA, IRENA. No working feed: WFP,
  Recharge, JAXA, Bloomberg Green, Washington Post climate, DW's section feeds.
- To check: the countries of Energy Tracker Asia (HK), European Spaceflight (IE) and Latam Satelital (AR) are best
  guesses; pv magazine Latin America is set to DE (the publisher).

## How it works

- **Relevance** (`relevance_v3`): AI is still decided by keywords first. With more than one desk, press items
  (news, newsletters, aggregators, Hacker News) without an AI keyword go to Haiku, which returns a desk or none.
  So no desk needs keyword lists in 23 languages. `llm: false` sources are sorted by `DESK_KEYWORDS` (English).
  Migration 6 sends the last three days' rejected items through it again, once.
- **Store**: `items.desk` and `stories.desk`; everything before was AI. Editions and the sentiment index are keyed
  by desk. AI's frozen editions stay at `editions/<date>.json`; other desks' go to `editions/<desk>/<date>.json`.
- **Clustering**: an item joins, and a story merges with, stories of its own desk only.
- **Labels**: one prompt per desk (`news_label_<desk>_v1`). Tracks stay technical / political / economic. The
  economic track gains `shortage` (energy, food, drug shortages). Energy and food measure **outlook** (alarmed −2 to
  hopeful +2): "for or against energy" means nothing, and the prompt judges the wording, never the technology (a
  hopeful oil story and a hopeful solar story are both positive). Biotech and space measure critical to enthusiastic.
- **Summaries and the day's line**: `story_summary_desk_v1` and `weather_desk_v1`, with a "Desk:" line first in
  the material. AI keeps its prompts, so nothing on the AI desk is relabeled or rewritten.
- **Builders**: Rising and The gap stay on the AI desk.
- **Site**: AI at `/`, the others at `/energy/`, `/biotech/`, `/space/`, `/food/`, each with `week/`, `month/`,
  `year/`, `narratives/`, `sentiment/` and `archive/`. The site navigation points at the current desk's pages;
  About is shared and lists the desks.

## Cost

AI's last week: about $0.71 (labels $0.25, summaries $0.33, day's lines $0.10, relevance $0.03).

- Relevance: every press item without an AI keyword now costs a share of a Haiku call: about 1,500 items a day,
  60 calls, about $0.04 a day.
- Per new desk: labels about $0.01–0.02 a day; summaries (top 12 per view, Sonnet, only when a story grows) and the
  day's lines about $0.05.
- In all, roughly $8–12 a month on top of AI, inside the $30 cap. The first publish also labels and summarizes the
  three days sent back through relevance: a one-off of perhaps $0.50–1.

## Not done yet

- Hand labels for the new desks (`tests/gold/`), for Benjamin, before their labels are trusted like AI's.
- A desk's sentiment needs three outlets a day; Food and Space may often have none at first.
- An item belongs to one desk. A story that is both AI and energy (a data center's power deal) lands on one of them.
