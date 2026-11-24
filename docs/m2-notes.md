# M2 notes: relevance, embeddings, stories

Run on 2026-11-24 against ~3,800 ingested items (1,900 relevant in the 72h window).

## Relevance

`pipeline/relevance.py`, in order:

1. **Always relevant by kind**: repos, models, datasets, spaces, papers, Product Hunt AI launches. They come from AI-specific listings or queries.
2. **Always relevant by source**: feeds marked `ai_focused: true` in `sources.yaml` (AI sections, AI newsletters, lab blogs, 37 in all), plus Hugging Face Posts.
3. **Keyword in the headline**: AI terms in five languages (AI, KI, IA, "künstliche Intelligenz", ...), company, product and people names (OpenAI, Nvidia, Claude, Altman, Huang, ...) and data centers. Acronyms and names that are also ordinary words are matched case-sensitively, so "chair" never fires "AI".
4. **Ambiguous**: a strong term only in the summary, or a weaker topic word (chips, Microsoft, robots, Musk, ...). These go to Haiku (`llm/prompts/relevance_v1.md`) in batches of 25, together with relevant non-English items that still need an English title. Results are cached per content hash, so an item is never sent twice.
5. Everything else is not relevant.

First run: 623 relevant by kind, 390 by source, 845 by keyword, 1,559 not relevant, **367 ambiguous**. With no `ANTHROPIC_API_KEY` set, ambiguous items stay undecided and are left out of stories, and non-English titles stay untranslated. A sample of the ambiguous ones shows why Haiku is needed: "Alibaba readies T-Head chip IPO" (AI chips, yes), "Dems crash Elon Musk's Texas honeymoon" (no).

Near-duplicates: same source, same normalized title, different URL. Marked `dup_of` and skipped.

## Embeddings

`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` through fastembed (ONNX, CPU, ~220 MB download, cached in `.cache/fastembed`). Embedded text: English title (or original) + first 300 characters of the summary.

Chosen over the brief's `BAAI/bge-small-en-v1.5` after a side-by-side on real headlines:

| | bge-small-en | multilingual MiniLM |
|---|---|---|
| Same story, English vs French/German/Swedish | 0.79 / 0.72 / 0.59 | 0.68 / 0.64 / 0.46 |
| Unrelated AI headlines | 0.40 to 0.53 | −0.07 to 0.31 |

The multilingual model leaves a much wider gap between "same story" and "different story". It also clusters Swedish, German, French and Spanish headlines without waiting for translation.

## Clustering

`pipeline/cluster.py`. Only items without a story are placed, oldest first, so existing assignments never move and story IDs stay stable:

1. **Links first.** An HN post or Bluesky post that links to an article, a Techmeme lead pointing at an outlet's URL, a paper naming its GitHub repo, an OpenRouter model naming its Hugging Face repo: each joins the story of what it points at.
2. **Similarity.** Cosine similarity to story centroids, plus 0.03 per shared name (max 2). Join the best story at or above 0.62.
3. **Strict kinds.** Repos, models, datasets, spaces, papers and launches have generic descriptions ("a framework for AI agents"). They join, and can be joined, by similarity only at 0.8 or above. Below that, links are the only way in.
4. Otherwise the item founds a new story; the ID is derived from the item's ID.
5. **Merge.** Two stories above 0.76 that share a name (or a link) merge into the older one.

Threshold grid (join / merge), biggest stories:

| join | result |
|---|---|
| 0.50 | 190-item Huang story, plus a 121-item blob of unrelated "AI and society" pieces |
| 0.55 | Same blob at 95 items |
| **0.62** | Huang 148 (all about his return and the reactions), Megaspeed blacklist separate, no blobs |
| 0.65 | Huang 147, its market angle split off (21 items) and the math-proof story split in two |

**Spam found:** 69 GitHub repos named variants of "manus--ai" from different owners, each with 190 to 370 farmed stars, formed a 48-item "story". A star minimum wouldn't catch them. The GitHub fetcher now drops any repo name (compared as a set of words) published by three or more owners.

Live result after tuning: 1,093 items placed, 14 by link, 340 by similarity, 739 stories, of which 74 have two or more items. Top: Huang's return (169 items, 45 outlets), US blacklists Megaspeed (14 outlets), "the AI boom had a really bad week" (13), entry-level jobs report (8), Claude's math proof verified (8), Grok deepfake lawsuits (7).

## Known limits

- Ranking in `qa cluster` is a placeholder: outlets, then sources, then items. M3 adds the momentum score.
- The window's many single-item stories are expected (one blog post, one repo). They matter for "Rising" and "The gap" later.
- Without an API key, 367 ambiguous items are left out of stories, and the representative headline can be non-English when no English item exists.
- GDELT: English editions only now (`sourcelang:english`). It was rate-limited again on the last run.
