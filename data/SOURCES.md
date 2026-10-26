# Data sources

Every dataset FairAsk uses, its terms, and how to obtain it.

**Raw data is never committed.** `data/raw/`, `data/processed/` and `data/private/`
are gitignored. Only the scripts that download or prepare data live in git.

Sources marked **scripted** are fetched by `python data/download.py <name>`.
Sources marked **manual** need a login, a licence click or a form, so they cannot
be automated — follow the instructions in the row and save the file to the path given.

## Training data (sold prices)

### `toronto` — scripted
Toronto residential sales, roughly 2019. 15,236 rows with sold and list price,
beds, baths, square footage, parking, property type and lat/long.

- Source: [slavaspirin/Toronto-housing-price-prediction](https://github.com/slavaspirin/Toronto-housing-price-prediction) — `houses.csv`
- Lands in: `data/raw/toronto_sales/houses.csv`
- Terms: **no licence stated.** Used locally for model training only. Credited here
  and in the model card. Not redistributed — the file is not committed to this repo.
- Row count measured on download, 2026-10-26. The upstream README says 15,234;
  the file actually holds 15,236 data rows. The measured number is used above.

### `brampton` — scripted
Brampton sales, January to May 2021. 1,193 rows, adding sold date, garage, air
conditioning and heating type.

- Source: [AndrewTymkiv/real_estate_analysis](https://github.com/AndrewTymkiv/real_estate_analysis) — `Resources/Sold_homes_combined_final.csv`
- Lands in: `data/raw/brampton_sales/Sold_homes_combined_final.csv`
- Terms: **no licence stated.** Same handling as the Toronto set above.

### Waterloo Region sold comps — manual, not yet obtained
Local sales, for validating the model where it is actually meant to be used.

- Source: a realtor or Cornerstone Association of REALTORS, by request
- Lands in: `data/private/` (gitignored)
- Terms: **private.** Never committed, never published. Individual sales, addresses
  and rows must never appear in the README, the model card or a screenshot. Only
  aggregate results, such as an accuracy figure, may be reported.

## Market and baseline data

### CREA MLS® Home Price Index — manual
Monthly benchmark prices, 2005 to September 2026, by region and property type.
Covers Cambridge, Kitchener-Waterloo, Greater Toronto, Mississauga and Oakville-Milton.
This is the backbone of the fair value estimate.

- Source: <https://www.crea.ca/housing-market-stats/mls-home-price-index/hpi-tool/>
  → "Download the data" → the MLS® HPI zip
- Lands in: `data/raw/crea_hpi/` — four workbooks, of which FairAsk reads
  `Not Seasonally Adjusted (M).xlsx`
- Terms: **CREA copyright.** Used for calculations only. The files are not
  republished and no benchmark table is committed or posted.
- Downloaded: October 2026 (data through September 2026)

### TRREB monthly aggregates — manual
Sales, new listings, sales-to-new-listings ratio, months of inventory, days on
market and sale-to-list ratio for 65 GTA areas, 1996 to October 2022.

- Source: [michaelarman/GTA_Housing](https://github.com/michaelarman/GTA_Housing)
- Terms: collected with TRREB's permission by the repository author. Credited here.

### TRREB community reports — manual
Quarterly market statistics by community, including Waterloo Region.

- Source: <https://public.trreb.ca/> market statistics → community reports (PDF)
- Terms: public documents. Cited as TRREB.

### Waterloo Region monthly home prices — manual
Monthly average price, median price and sales count by property type, 2018 to 2024.

- Source: <https://www.kaggle.com/datasets/milankozo/waterloo-region-home-prices-2018-2024>
- Terms: **CC0** — public domain, no restrictions.
- Manual because Kaggle downloads need an account and an API token.

### CMHC Rental Market Survey 2025 — manual
Average rent by bedroom count per metro area, for the investor view.

- Source: CMHC Housing Market Information Portal, Rental Market Survey
- Terms: open data. Cited as CMHC.

### Bank of Canada posted mortgage rate — manual
Weekly 5-year conventional mortgage rate, series `V80691335`, for the mortgage
and stress test math.

- Source: Bank of Canada Valet API, <https://www.bankofcanada.ca/valet/observations/V80691335/json>
- Terms: open. Cited as Bank of Canada.
- Not scripted yet — it is first needed in Phase 4.

## Feature enrichment (joined by location)

These fill gaps in the sold datasets. All are manual: each needs a form, an
account, or a map query that is easier to do by hand once.

| Source | Adds | Terms |
|---|---|---|
| [Toronto Property Boundaries](https://open.toronto.ca/dataset/property-boundaries/) | Lot size (`STATEDAREA`) for Toronto sales | Open Government Licence – Toronto |
| Toronto Building Construction Dates (Borealis, UofT Map & Data Library) | Year built per parcel, pre-1901 to 2003 | **CC BY-NC** — non-commercial, reference use. Must be stated in the model card |
| [Toronto Cleared Building Permits](https://open.toronto.ca/dataset/building-permits-cleared-permits/) | New builds and renovations, 2000 onward | Open Government Licence – Toronto |
| Kitchener, Waterloo, Cambridge, Mississauga and Brampton building permits | Year built for newer homes, renovations, finished basements; Waterloo property area; Cambridge lot area | Municipal ArcGIS open data, per-city open licences |
| [StatCan Open Database of Buildings](https://www.statcan.gc.ca/en/lode/databases/odb) | Building footprint area, for estimating square footage | Open Government Licence – Canada |

## Known gaps

Recorded here so no one later mistakes a gap for a modelling choice. **These are
not filled with synthetic or estimated values.**

- No free Waterloo Region sold prices. Until local comps arrive, the model is
  trained on GTA sales only, and no claim about Waterloo Region accuracy can be made.
- No GTA sales after 2021. Old sales are time-adjusted to today with the HPI,
  which assumes a typical home for its region and type moved with the benchmark.
- No lot size for Kitchener.
- No year built for Waterloo Region homes older than about 1997.
