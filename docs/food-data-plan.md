# Food desk data strip: plan

Drafted 2026-11-27 for Benjamin to approve step by step. **Steps 1 and 2 are done:** the strip is on `/food/`. It follows the energy strip (`docs/energy-data-plan.md`, `pipeline/energy_data.py`).

## Summary

- **What it is:** a row of figures on `/food/`, under the masthead: the EU's average farm-gate prices for milling wheat, feed maize and feed barley, butter and skimmed milk powder (weekly), and nitrogen, phosphorus and potash fertiliser (monthly). Each shows the latest value, the change over four weeks (or a month for fertiliser) and a 12-point ink sparkline.
- **Source:** the European Commission's Agri-food Data Portal API. It's European: member states report the prices, and the Commission publishes EU averages.
- **Cost:** none. No model calls, no key, three requests per publish.
- **License:** CC BY 4.0 under the Commission's reuse decision (2011/833/EU). The portal has no legal notice of its own; the Commission's notice covers EU-owned content on its sites. Credit: "European Commission, Agri-food Data Portal".

## 1. Sources, checked (2026-11-27)

Probed through the project's `Http` client (generic user agent). robots.txt: `agridata.ec.europa.eu` only blocks country factsheet pages; `api.tech.ec.europa.eu` answers 404 (no restrictions, RFC 9309). No authentication; the docs mention a rate limit without numbers.

| Series | Endpoint | Frequency | EU average | Latest on 27 Nov | Unit |
|---|---|---|---|---|---|
| Milling wheat, feed maize, feed barley | `GET /agrifood/api/cereal/prices?memberStateCodes=EU&productCodes=BLTPAN,MAI,ORGFOUR&beginDate=…&endDate=…` | Weekly | Yes (`marketName: National Average`, one delivery stage) | Week of 16–22 Nov: €209, €225, €179 | € per tonne |
| Butter, skimmed milk powder | `GET /agrifood/api/dairy/prices?memberStateCodes=EU&products=BUTTER,SMP&beginDate=…&endDate=…` | Weekly | Yes | Week of 16–22 Nov: €402.80, €348.69 | € per 100 kg |
| Nitrogen, phosphorus, potash fertiliser | `GET /agrifood/api/fertiliser/prices?years=…` | Monthly | EU only (`memberStateName: European Commission`) | September: €469, €742, €363 | € per tonne |

Things the fetcher must handle:
- **Prices are strings with a euro sign, and the decimal mark varies by dataset:** cereals use a comma (`€209,19`), dairy uses a dot (`€402.80`), and fertiliser is a plain number. Some cereal rows have `null` or junk (`€#######`); skip them.
- **Dates are `dd/mm/yyyy`;** sort by parsed date, never by the string.
- **The lag:** a week's prices appear about four days after it ends (16–22 Nov was published on 26 Nov). The strip should say "week of 16 Nov", not today's date. Fertiliser lags about two months.
- **An unknown filter value returns HTTP 500, not 400** (`months=Sep` did). A 500 must leave the last stored values in place, like the energy strip.
- **Raw milk** (monthly, per country) has no EU average row, so it's left out.
- **The old endpoint host** (`agridata.ec.europa.eu/api`) still works for now; the docs say to use `api.tech.ec.europa.eu`.

Fixtures recorded under `tests/fixtures/http/` (keys `agri:cereal:eu`, `agri:dairy:eu`, `agri:fertiliser`), filtered to the products above so the fixture trimmer keeps the rows that matter.

## 2. How it fits the code (built)

- `pipeline/food_data.py`: three requests per publish (`qa run` after ingest, `qa data` in the deploy, every `--dry-run` and `qa ingest --record`). It parses both decimal marks, skips junk values, keeps only the EU's `National Average` rows, and stores one value per week or month in `desk_figures` (a new table in `SCHEMA`; the energy strip keeps its own `energy_daily`). A failed fetch leaves the stored values.
- `build_editions` adds a `food_data` block to the food desk's editions: each figure's latest period and value, its change over 4 weeks (fertiliser: a month), and its last 12 values.
- The page reuses the energy strip's markup and CSS (`data-strip`, `prices`, `build.price_spark` with a unit and step). The heading names the week; fertiliser rows name their month. Ink only. On phones long names wrap rather than lose their end.
- The About page's Desks section credits the Commission and CC BY 4.0.
- Settings: `food_data:` in `settings.yaml` (products, points, change window). A cereal's `label` must be the API's product name, since cereal rows carry the name, not the code.
- `qa energy` is now `qa data` (energy and food); the old name still works.

## 3. Steps

1. **Probe and record.** Done.
2. **Build the strip.** Done 2026-11-27, with the five weekly figures (three cereals, butter, skimmed milk powder) plus nitrogen fertiliser. Benjamin picks the products; the API also has pigmeat, poultry, eggs, olive oil, sugar, rice and fruit and vegetable prices.
3. **Optional:** a per-country view (the API has most member states for cereals and dairy), e.g. Sweden's milling wheat next to the EU average.

## 4. Not chosen

- FAOSTAT and the FAO Food Price Index: worldwide, but only found through a paid wrapper in Orbit; FAO's own API is unchecked.
- USDA NASS and FAS: US-only and need a key.
- Eurostat food inflation: consumer prices, monthly; possible later, it's the same Commission license.
