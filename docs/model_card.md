# Model card: FairAsk adjustment model (draft)

Status: **draft**, written at the end of Phase 3. Every number here comes from
`ml/results/2026-11-15_n16030_eval.json`, produced by `python ml/train.py`.

## What it does

Estimates the fair value of a home in the GTA as

    fair value = CREA benchmark (region, property type, month) x exp(model prediction)

The model predicts `log(sold price / benchmark)`: how far a particular house sits
from the typical home of its type at the time it sold. Working in log space means
each feature acts as a percentage premium or discount on the benchmark.

A price range comes from two quantile models (10th and 90th percentile), widened
by a conformal margin so that it holds the sold price about 80% of the time.

## Data

| Source | Rows used | Sold | Notes |
|---|---|---|---|
| Toronto sold dataset (slavaspirin) | 14,892 | about 2019, **no sale date recorded** | Anchored to June 2019 by decision; see below |
| Brampton sold dataset (AndrewTymkiv) | 1,138 | Jan to May 2021 | PDF extraction; no sq ft, coordinates, parking or description |
| CREA MLS HPI | 7,830 benchmark rows | 2005-01 to 2026-09 | Not seasonally adjusted |

Features joined onto the Toronto sales: lot area from City parcel polygons,
building footprint from Statistics Canada's Open Database of Buildings v3, year
built from City building permits (or the description), and keyword flags from
the listing description (finished basement, garage, renovated and others).

Full sources, licences and gaps: `data/SOURCES.md`.

## How it was evaluated

* **Holdout by location.** Five folds grouped by district (Toronto city district,
  Brampton community). Every sale is predicted by a model that never saw its
  district. No random split.
* **Pooled out-of-fold.** One score over all 16,030 out-of-fold predictions.
* **Untuned.** LightGBM parameters were fixed before the first run.
* **Baseline:** the CREA benchmark alone, i.e. predicting every house at exactly
  the typical price for its region, type and month.

## Results

| Rows | Baseline MAE | Baseline MAPE | Model MAE | Model MAPE | Model median APE |
|---|---|---|---|---|---|
| All (16,030) | $294,777 | 26.4% | $118,332 | 12.1% | 9.0% |
| Toronto (14,892) | $296,506 | 26.3% | $117,437 | 12.2% | 9.0% |
| Brampton (1,138) | $272,155 | 28.0% | $130,047 | 11.7% | 9.2% |

Price range: the raw quantile models held the sold price 65.2% of the time
against an 80% target. A conformal margin of 0.046 in log units, fitted on half
the districts and scored on the other half, brings coverage to 80.6%.

Most influential features (mean absolute SHAP, log units): longitude 0.170,
latitude 0.139, square footage 0.091, bathrooms 0.088, property type 0.037.

Footprint was kept because it measurably helped: adding it as a feature cut MAE
from $119,765 to $118,629. Using it to fill in missing square footage did not
help ($119,599), so it is not used that way. That comparison was run before the
"N years old" year-built fallback was removed (it often described a roof or
furnace, not the house); the current model scores $118,332.

## Where these numbers do not apply

* **This is GTA accuracy. Nothing has been measured in Waterloo Region**, the
  product's main market. No free sold-price data exists there; see Phase 6.
* **Toronto sale months are assumed.** The source records none. Evidence puts the
  sales in 2018 to 2019, and every Toronto row is treated as June 2019. If that
  is wrong by a year, the benchmark the model compares against is off by roughly
  the HPI's movement over that year.
* **The data is old.** The newest sale is from May 2021. The model learns how
  features move a price relative to the benchmark; the benchmark carries the
  market from then to now. That relationship may itself have shifted.
* **Brampton rows lack most features.** The model has to value them from beds,
  baths and type alone, which is part of why their range is wider.

## Known gaps and limits

* Year built is known for only 13.9% of sales. Permits start around 2000, so most
  older homes have none.
* Square footage is a listing bucket, not a measurement, and is missing for 34.9%
  of rows after joining both sources.
* Lot size is kept only for detached and semi-detached homes. A condo or
  townhouse block's parcel is the whole development.
* Keyword flags record that a phrase appears, not that it is true. "Renovated"
  cannot tell a 2019 kitchen from a 1995 one.
* Location dominates the explanations as raw latitude and longitude. The deal
  report has to present these as "location", not as coordinates.

## Benchmark forecast (backtest only)

`ml/forecast.py` forecasts each CREA benchmark series (5 regions x 6 types)
3 and 6 months ahead. A ridge regression on recent monthly changes was compared
with two baselines in a rolling-origin backtest from 2015-01 to 2026-09: at each
month the ridge was refitted on past data only. Its settings were fixed before
the first run. Results (`ml/results/2026-11-19_forecast_eval.*`), as MAPE:

| Horizon | No change | Same change as last year | Ridge |
|---|---|---|---|
| 3 months | 4.21% | 5.00% | 4.28% |
| 6 months | 6.83% | 7.79% | 7.08% |

**The ridge does not beat "no change"**, and from 2022 on it does worse (5.08%
against 4.00% at 3 months). The app does not show a forecast for that reason.

## Licensing notes that travel with the model

* Toronto and Brampton sold datasets: no licence stated. Used locally, credited,
  not redistributed.
* CREA HPI: CREA copyright. Used for calculation only, not republished.
* Toronto Building Construction Dates (Borealis): **CC BY-NC**. Listed as a
  source, but not yet used by this model.
* Statistics Canada ODB: Open Government Licence - Canada.
* City of Toronto parcels and permits: Open Government Licence - Toronto.
