# Energy data strip: plan

Drafted 2026-11-27 for Benjamin to approve step by step. **Steps 1 and 3 are done** (probe and fixtures, findings in section 1; day-ahead prices from Energinet on `/energy/`). Step 2 waits on the Energy-Charts license question.

## Summary

- **What it is:** a short row of figures on `/energy/`, under the masthead: today's renewable share and generation mix for a few countries, and today's day-ahead power price for a few price areas, each with a 7-day sparkline. The figures sit next to the news; they are never labeled, averaged into the sentiment index or sent to a model.
- **Cost:** none. No model calls, no paid data. Two to four extra HTTP requests per publish.
- **Sources:** Energy-Charts (Fraunhofer ISE) for the generation mix, Energi Data Service (Energinet) for prices. Both answer robots.txt with 404, which RFC 9309 treats as no restrictions (checked 2026-11-27 with the generic user agent). Neither needs a key.
- **One finding changes the earlier shortlist:** Energy-Charts' **price** endpoint says its data is "for private and internal use only" and forbids external use (the prices come from EPEX SPOT). So Energy-Charts is used for generation only, and prices come from Energinet, whose data is CC BY 4.0.

## 1. Sources, checked

| Source | Endpoint | What we take | License | Limits seen |
|---|---|---|---|---|
| Energy-Charts | `GET https://api.energy-charts.info/public_power?country=<cc>&start=<date>&end=<date>` | Net generation per production type (MW, 15-min) plus `Renewable share of generation` and `Renewable share of load`, ready-made | No restriction in the response; the site states CC BY 4.0 for its own data. Credit "Energy-Charts (Fraunhofer ISE)" | None hit |
| Energy-Charts | `GET /price?bzn=SE3` | **Not used** | "Private and internal use only" | n/a |
| Energi Data Service | `GET https://api.energidataservice.dk/dataset/DayAheadPrices?start=<date>&sort=TimeUTC` | Day-ahead price per area, EUR/MWh, 15-min | CC BY 4.0. Credit "Source: Energinet (www.energidataservice.dk)" | **HTTP 429 after about five calls in a minute**, so one request per publish |
| Energi Data Service | `PowerSystemRightNow` | Possible later: Danish CO₂ intensity and flows, per minute | CC BY 4.0 | Same |

### Step 1 findings (2026-11-27)

Probed through the project's own `Http` client (generic user agent, robots.txt checked) and recorded fixtures.

- **Energinet `DayAheadPrices` carries six areas:** DE, DK1, DK2, NO2, SE3, SE4, at 15-minute resolution, EUR and DKK. SE1, SE2 and the rest of Europe are not in it; those need ENTSO-E (step 4). The older `Elspotprices` dataset is empty now: don't use it.
- **Energinet's `start` and `end` are Danish local time** (`TimeDK`), not UTC. The fetcher should pass Stockholm-day bounds converted to Danish time (the same zone) and read `TimeUTC` for storage.
- **Energinet rate limit:** HTTP 429 after about five quick calls ("try again in 37 seconds"). One call per publish, with a 15-second host interval in `http.host_min_interval_s`, is well inside it.
- **Energy-Charts generation works for:** SE, DE, FR, ES, PL, IT, NL, FI (15-minute data, 11–22 production types, a ready-made `Renewable share of generation` series).
  - **GB is not usable:** only 6 types (no nuclear, solar, offshore wind or hydro), so its "renewable share" of about 75% counts onshore wind against gas. GB would need NESO or Elexon later.
  - **NO has no renewable-share series;** DK returns 404 (Energinet covers Denmark).
- **Energy-Charts' license for generation data is not published anywhere I could reach.** Its robots.txt and `llms.txt` say spot-market and futures prices (EPEX SPOT / EEX) "may not be redistributed"; they say nothing either way about generation. The API responses for generation carry no `license_info` (the price responses do). **Benjamin decides:** ask Fraunhofer ISE (energy-charts contact) for written permission to show daily means with credit, or take generation from ENTSO-E instead once its key exists (step 4).
- **Energinet's license is CC BY 4.0** (its support page). Credit line: "Source: Energinet (www.energidataservice.dk)". The prices themselves originate at the power exchanges; the About page should say Energinet publishes them.

Fixtures recorded under `tests/fixtures/http/` (keys `energy:energy-charts:power:{se,de,fr,es,pl,uk}` and `energy:energinet:dayahead`), one hour of data each. The fixture trimmer now keeps every entry of `production_types` (a list of series, not of articles) and trims each series instead; before that it kept only the first five types and dropped the renewable share.

## 2. How it fits the code

- **Not items.** These are numbers over time, not articles, so they don't go through `fetchers/` → `items`. A new module `src/quiet_ai/pipeline/energy_data.py` fetches through the same `Http` client (robots.txt, per-host spacing, retries, fixtures) and writes to a new table:

  ```sql
  CREATE TABLE energy_series (
      source  TEXT NOT NULL,   -- energy-charts | energinet
      metric  TEXT NOT NULL,   -- renewable_share | gen_<type> | price_day_ahead
      zone    TEXT NOT NULL,   -- country code or price area
      day     TEXT NOT NULL,   -- Stockholm date
      value   REAL NOT NULL,   -- daily mean (MW, %, EUR/MWh)
      PRIMARY KEY (source, metric, zone, day)
  );
  ```

  Daily means only, so the table stays small and we store nothing finer than the site shows.
- **When:** in the publish (`qa run`), after ingest. Not in the 2-hourly collect: the strip only changes once a day. A failed fetch never stops the publish; the strip shows the last day it has, dated.
- **Editions:** `editions/energy/<date>.json` gets an `energy_data` block (today's figures and seven days of daily means), so a frozen edition shows what it showed that morning.
- **Page:** a strip in `index.html.j2`, only when the desk has `energy_data` (the energy desk). Sparklines reuse `build.sparkline` (inline SVG, colors from tokens). Numbers in `--mono`, labels in `--sans`. No color encodes good or bad: `--signal` stays for navigation, and umber/sage stay for stance. Must fit 380px without horizontal scroll and work without JavaScript.
- **About page:** a "Data" line under the energy desk naming both sources and their licenses.
- **Tests:** recorded responses in `tests/fixtures/http/` (via `qa ingest --record`-style recording, trimmed), a parser test per source, a test that a missing fetch leaves the strip on the last day, and `test_site.py` still passing (nothing loaded from other sites).
- **Settings:** `energy_data:` in `settings.yaml`: on/off, the countries for the mix, the price areas, and the sparkline length.

## 3. Steps

Each step is a separate yes or no.

1. **Probe and record (no page change).** One live call to each endpoint to settle the open questions in section 1, record fixtures, confirm the country list Energy-Charts supports. About 10 minutes, no cost.
2. **Generation mix.** Table, fetch, edition block and the strip with renewable share for a first set of countries. Suggested: SE, DE, FR, ES, PL (GB dropped, see step 1); Benjamin picks. Waits on the Energy-Charts license question.
3. **Day-ahead prices.** Add Energinet prices for SE3, SE4, NO2, DK1, DK2 and DE, same strip. No license question; can go before step 2.
   **Done 2026-11-27.** `pipeline/energy_data.py` makes one request per publish (`qa run`, after ingest; also `qa ingest --record` and every `--dry-run`), stores daily mean, min and max per area in `energy_daily`, and `build_editions` puts an `energy_data` block in the energy desk's editions. The page shows each area's day (mean, range) and a 7-day ink sparkline (`build.price_spark`); phones get one line per area. The About page's Desks section names Energinet and CC BY 4.0. Settings: `energy_data:` in `settings.yaml`. Tests: `tests/test_energy_data.py`.
4. **ENTSO-E (optional, later).** All European price zones (all four Swedish ones) and cross-border flows from one source. Needs Benjamin to register at transparency.entsoe.eu and email transparency@entsoe.eu for API access (about three working days), then put the token in `.env` and the GitHub secrets. Agents never enter the token.
5. **Gas storage (optional, later).** GIE AGSI+ EU storage fill level, a figure the energy press quotes often in winter. Free key, same registration pattern; GIE must be credited.

## 4. Not chosen

- Electricity Maps: free key is non-commercial and one zone.
- Nord Pool: market data is a paid subscription; the free endpoint behind its website is unofficial and may change.
- Energy-Charts prices: external use forbidden (see summary).
- Paid wrappers found through Orbit (cernion, greeneris and similar): they resell the free sources above per call.
