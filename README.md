# FairAsk

Is the asking price fair? Paste a house listing from Waterloo Region or the GTA
and FairAsk returns a fair value range, a verdict, and the top reasons behind it.

**Status: working app (FastAPI + Next.js), run locally.** The valuation model
is evaluated on GTA sales only; see `docs/model_card.md` for how, and what the
numbers do not cover. Nothing has been measured in Waterloo Region, and the
report says so on every Waterloo Region listing.

## What it does

Estimates fair value from historical sales and market data, then reports:

- a fair value range and a verdict (Great deal / Good / Fair / Overpriced)
- why, in plain language, from the model's own feature contributions
- cost to own: Canadian mortgage payment, stress test, land transfer tax, CMHC insurance
- market context: benchmark price trend, buyer's or seller's market
- investor view: CMHC rent estimate, gross yield, monthly cash flow
- red flags: long time on the market, price cuts, an asking price far outside the range

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

## Run the app

The API needs the trained models (`python ml/train.py`) and the processed
tables (the scripts in `data/` and `ml/`).

```sh
# terminal 1: the API on http://127.0.0.1:8000
uvicorn main:app --app-dir api

# terminal 2: the web app on http://localhost:3000
cd web
npm install
npm run dev
```

Paste a listing's text or pick a screenshot (read in the browser with
Tesseract.js), check the filled-in form, and press the button.

## Tests

```sh
python -m pytest ml data api     # Python: data, model, deal engine, API
cd web && npm test                # Vitest: form conversion, listing parser
```
