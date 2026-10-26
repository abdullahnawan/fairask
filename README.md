# FairAsk

Is the asking price fair? Paste a house listing from Waterloo Region or the GTA
and FairAsk returns a fair value range, a verdict, and the top reasons behind it.

**Status: early development.** No model, API or frontend exists yet. No accuracy
numbers are published, because none have been measured.

## What it does

Estimates fair value from historical sales and market data, then reports:

- a fair value range and a verdict (Great deal / Good / Fair / Overpriced)
- why, in plain language, from the model's own feature contributions
- cost to own: Canadian mortgage payment, stress test, land transfer tax, CMHC insurance
- market context: benchmark price trend, buyer's or seller's market

## Scope

Waterloo Region (Kitchener, Waterloo, Cambridge, townships) and the GTA.
Detached, semi-detached, townhouse and condo apartment.

Listings are imported by pasting text or a screenshot. **No listing site is
scraped.**

## Layout

```
data/   download and prep scripts, SOURCES.md (raw data is gitignored)
ml/     feature pipeline, training, evaluation, saved models
api/    FastAPI app, deal engine, finance math
web/    Next.js frontend
docs/   model card, design notes
```

## Setup

Requires Python 3.12.

```sh
py -3.12 -m venv .venv
.venv/Scripts/activate      # Windows; use source .venv/bin/activate elsewhere
pip install -r requirements.txt
```

## Data

Every source, its license and how to obtain it are listed in `data/SOURCES.md`.
Raw data is never committed. Private sold comps are never published in any form.
