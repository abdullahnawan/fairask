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
