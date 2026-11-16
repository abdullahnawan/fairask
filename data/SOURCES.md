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
  the file actually holds 15,236 data rows, counted with a CSV parser because
  description fields contain embedded newlines. The measured number is used above.

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

### CREA MLS® Home Price Index — `python data/market.py`
Monthly benchmark prices, 2005 to September 2026, by region and property type.
Covers Cambridge, Kitchener-Waterloo, Greater Toronto, Mississauga and Oakville-Milton.
This is the backbone of the fair value estimate.

- Source: <https://www.crea.ca/housing-market-stats/mls-home-price-index/hpi-tool/>.
  `data/market.py` reads that page, takes the newest `MLS_HPI_<Mon>_<Year>.zip`
  link and extracts it. The zip is named for the month CREA **published** it, so
  `MLS_HPI_Oct_2026.zip` holds data through September 2026.
- Lands in: `data/raw/crea_hpi/` — four workbooks, of which FairAsk reads
  `Not Seasonally Adjusted (M).xlsx`
- Terms: **CREA copyright.** Used for calculations only. The files are not
  republished and no benchmark table is committed or posted.
- Downloaded: October 2026 by hand; re-fetched by the script 2026-11-16 (same
  release, data through September 2026)

### TRREB Market Watch — `python data/market.py`
Monthly report for every GTA municipality and Toronto district: sales, average
and median price, new and active listings, sales-to-new-listings ratio (SNLR),
months of inventory, sale-to-list ratio and days on market. This is what the
deal report uses to call a buyer's or seller's market.

- Source: <https://trreb.ca/market-data/market-watch/>. The script takes the
  newest `mwYYMM.pdf` link (public, no login; robots.txt only disallows /wp-admin/).
- Lands in: `data/raw/trreb/mwYYMM.pdf`, parsed to `data/processed/trreb_market.csv`
  (the monthly "All Home types" table only).
- Needs `pdftotext` on PATH (xpdf or poppler; Git for Windows ships it).
- Check: every row must satisfy sales x average price = dollar volume to within a
  dollar per sale. 76 areas, 0 dropped, for October 2026.
- Terms: public report. Cited as TRREB. Only the aggregates are used.
- Downloaded: 2026-11-16 (October 2026 report)

### TRREB monthly aggregates — manual
Sales, new listings, sales-to-new-listings ratio, months of inventory, days on
market and sale-to-list ratio for 65 GTA areas, 1996 to October 2022.

- Source: [michaelarman/GTA_Housing](https://github.com/michaelarman/GTA_Housing)
- Terms: collected with TRREB's permission by the repository author. Credited here.

### TRREB community reports — manual
Quarterly market statistics by community, including Waterloo Region.

- Source: <https://public.trreb.ca/> market statistics, then community reports (PDF)
- Terms: public documents. Cited as TRREB.

### Waterloo Region monthly home prices — manual
Monthly average price, median price and sales count by property type, 2018 to 2024.

- Source: <https://www.kaggle.com/datasets/milankozo/waterloo-region-home-prices-2018-2024>
- Terms: **CC0** — public domain, no restrictions.
- Manual because Kaggle downloads need an account and an API token.

### CMHC Rental Market Survey 2025 — `python data/market.py`
Average rent paid by a new tenant ("turnover units"), by bedroom count, for the
Toronto and Kitchener-Cambridge-Waterloo metro areas, October 2025. Used for the
investor view's rent estimate.

- Source: <https://www.cmhc-schl.gc.ca/professionals/housing-markets-data-and-research/housing-data/data-tables/rental-market/rental-market-report-data-tables>.
  The script takes the newest `rmr-canada-<year>-en.xlsx` and reads Table 6.0.
- Lands in: `data/raw/cmhc/`, parsed to `data/processed/cmhc_rents.csv` with
  CMHC's reliability grade (a excellent to d fair; suppressed values left empty).
- Limit: the survey covers purpose-built rental apartments of three or more
  units. For a detached or semi it is a floor, not a comparable.
- Terms: open data. Cited as CMHC.
- Downloaded: 2026-11-16 (2025 survey, published December 2025)

### Bank of Canada posted mortgage rate — manual
Weekly 5-year conventional mortgage rate, series `V80691335`, for the mortgage
and stress test math.

- Source: Bank of Canada Valet API, <https://www.bankofcanada.ca/valet/observations/V80691335/json>
- Terms: open. Cited as Bank of Canada.
- Not scripted yet — it is first needed in Phase 4.

## Feature enrichment (joined by location)

These fill gaps in the sold datasets.

### `toronto_parcels` — scripted
Every property boundary in Toronto, used to measure the lot each sale sits on.

- Source: [Toronto Property Boundaries](https://open.toronto.ca/dataset/property-boundaries/)
  — the "Property Boundaries (wgs84) - shapefile" resource
- Lands in: `data/raw/toronto_parcels/property_bnds_gcc_wgs84.zip`
- Terms: Open Government Licence – Toronto. The file is not committed or
  republished; only measurements derived from it are.
- **Not version-pinned.** The City serves the current refresh, so this is the
  one source whose bytes can change under the project. The copy FairAsk was
  built against: refreshed 2026-10-26, downloaded 2026-10-27, 57,578,200 bytes,
  498,443 polygons.
- **It carries no lot area.** The attribute table holds only `OBJECTID` and
  `F_TYPE`, so area is computed from the polygon geometry by `ml/parcels.py`.
- Despite the "wgs84" in the file name the geometry is EPSG:3857 Web Mercator,
  per the `.prj`. Area in that projection is inflated by about 1.91x at
  Toronto's latitude, and `ml/parcels.py` corrects for it.

### `toronto_permits_2000_2016` and `toronto_permits_2017` — scripted
Every building permit the City has closed since 2000, with the street address,
the kind of work, and the dates it was issued and completed. A permit for a new
house or new building gives the year a home was built, which the sold data lacks.

- Source: [Toronto Cleared Building Permits](https://open.toronto.ca/dataset/building-permits-cleared-permits/)
  — the "Cleared Permits 2000 to 2016" and "Cleared Building Permits since 2017" CSVs
- Lands in: `data/raw/toronto_permits/cleared_permits_2000_2016.csv` and
  `data/raw/toronto_permits/cleared_permits_since_2017.csv`
- Terms: Open Government Licence – Toronto. Not committed or republished.
- **Not version-pinned.** The since-2017 file is refreshed daily. The copies
  FairAsk was built against: 2000-2016 last modified 2025-07-08, 155,623,064
  bytes; since-2017 last modified 2026-11-14, 153,068,855 bytes.
- The City notes records applied for before 1999-10-01 are likely incomplete,
  so year built from permits is only trustworthy for homes built in 2000 or later.

### `statcan_odb_on_1`, `statcan_odb_on_2`, `statcan_odb_on_3` — scripted
Building footprints for Ontario from Statistics Canada's Open Database of
Buildings, version 3.0 (released 2025-04-15), as three zipped GeoPackages.
Records carry the footprint polygon and, where the source city supplied them,
`sq_ft`, `floors`, `year_built` and `address`. Used to estimate square footage
where a Toronto listing has none.

- Source: [The Open Database of Buildings](https://www150.statcan.gc.ca/n1/pub/34-26-0001/342600012018001-eng.htm)
- Lands in: `data/raw/statcan_odb/ODB_v3_ON_1.zip`, `_2.zip`, `_3.zip`
  (about 375, 369 and 299 MB)
- Terms: Open Government Licence – Canada. Not committed or republished.
- Which of the three parts covers Toronto is not documented, so all three are
  downloaded and the Toronto rows are selected by the `csdname` attribute.
  Measured: parts 1 and 2 hold 567,869 Toronto buildings; part 3 holds none.
  `ml/footprints.py` unzips the two GeoPackages next to their downloads,
  because SQLite cannot read inside a zip.
- **For Toronto, sq_ft and floors are empty on every record** (StatCan writes
  `..` for missing). Only the outline, an address on about 70%, and a
  `height` with a median of 4.1 m are present. That height is too low to be a
  two-storey house, so it is not used as a storey count.
- The geometry is EPSG:3347, Statistics Canada Lambert, which is conformal, not
  equal-area: at Toronto it stretches lengths by 1.024, so areas are divided by
  1.0485.

The rest are manual: each needs a form, an account, or a map query that is
easier to do by hand once.

| Source | Adds | Terms |
|---|---|---|
| Toronto Building Construction Dates (Borealis, UofT Map & Data Library) | Year built per parcel, pre-1901 to 2003 | **CC BY-NC** — non-commercial, reference use. Must be stated in the model card |
| Kitchener, Waterloo, Cambridge, Mississauga and Brampton building permits | Year built for newer homes, renovations, finished basements; Waterloo property area; Cambridge lot area | Municipal ArcGIS open data, per-city open licences |

## Known gaps

Recorded here so no one later mistakes a gap for a modelling choice. **These are
not filled with synthetic or estimated values.**

- No free Waterloo Region sold prices. Until local comps arrive, the model is
  trained on GTA sales only, and no claim about Waterloo Region accuracy can be made.
- No GTA sales after 2021. The newest sale in either training set is from May
  2021, so recent market movement has to come from the HPI rather than from sales.
- **The Toronto sold dataset carries no sale date at all** - there is no such
  column. Its rows are anchored to **June 2019** by decision (2026-11-15), as
  the single constant `TORONTO_ASSUMED_MONTH` in `ml/adjust.py`. The evidence:
  years mentioned in descriptions peak in 2018 (410 rows) and 2019 (262) and
  collapse after (2020: 18, 2021: 9); the latest stated build year is 2018;
  MLS numbers sit in one narrow band. The Greater Toronto benchmark moved
  about 5% across 2019, so a mid-year anchor bounds the level error near
  ±2.5%. Every Toronto `price_today` inherits that error, and it is an
  inference, not a measurement. Building permits issued after 2019 cannot
  describe a 2019 sale, so year built is treated as unknown for those.
- CREA publishes no Brampton index and no semi-detached series. Brampton sales
  are adjusted with the Greater Toronto benchmark and semis with the
  single-family one. Both substitutions are in `ml/adjust.py`.
- Lot size is only meaningful where a sale sits on its own parcel. A
  condominium's parcel is shared by every unit, and a COMMON parcel under a
  condo or townhouse block covers the whole development, so only detached and
  semi-detached sales get a lot: 5,541 of 14,892 Toronto sales.
- No lot size for Kitchener.
- No year built for Waterloo Region homes older than about 1997.
