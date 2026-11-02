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
