"""Forecast CREA benchmark prices 3 and 6 months ahead, and backtest honestly.

Every series is one region and property type of the HPI (5 regions x 6 types).
Forecasts work on log prices, so a forecast is "how much will it change".

Three methods, scored the same way:

* **naive**: no change. The price in h months is today's price.
* **seasonal naive**: the same change as over those months last year. The HPI
  is not seasonally adjusted, so spring strength repeats.
* **ridge**: a linear model on the last 1, 2, 3, 6 and 12 months' changes plus
  last year's change over the target months, pooled across all series.
  Features are standardised and alpha is fixed at 1.0, chosen before the first
  run and not tuned.

The backtest is rolling-origin. For every month from 2015-01 to the last one
with an answer, the ridge is refitted on examples whose target month is at or
before that origin, then forecasts h months ahead. Nothing from after the
origin is ever seen. Every forecast is scored once against the real benchmark.

    python ml/forecast.py     # writes ml/results/<date>_forecast_eval.{json,md}
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from adjust import load_hpi_table

RESULTS = Path(__file__).resolve().parent / "results"
HORIZONS = (3, 6)
LAGS = (1, 2, 3, 6, 12)
FIRST_ORIGIN = pd.Timestamp("2015-01-01")
ALPHA = 1.0
METHODS = ("naive", "seasonal_naive", "ridge")


def log_prices(hpi: pd.DataFrame) -> pd.DataFrame:
    """Months down, one column per (region, type) series."""
    wide = hpi.pivot_table(index="month", columns=["region", "property_type"], values="benchmark_price")
    return np.log(wide.sort_index().asfreq("MS"))


def examples(logp: pd.DataFrame, h: int) -> pd.DataFrame:
    """One row per (origin month, series): features known at the origin, the
    change h months later, and the two baseline forecasts of that change."""
    def stack(frame: pd.DataFrame, name: str) -> pd.Series:
        return frame.stack(["region", "property_type"], future_stack=True).rename(name)

    parts = [stack(logp - logp.shift(k), f"lag_{k}") for k in LAGS]
    # last year's change over the same h months: log p[t+h-12] - log p[t-12]
    parts.append(stack(logp.shift(12 - h) - logp.shift(12), "last_year"))
    parts.append(stack(logp.shift(-h) - logp, "target"))
    parts.append(stack(logp, "log_price"))
    table = pd.concat(parts, axis=1).reset_index()
    table["target_month"] = table["month"] + pd.DateOffset(months=h)
    return table.dropna(subset=[f"lag_{k}" for k in LAGS] + ["last_year"])


FEATURES = [f"lag_{k}" for k in LAGS] + ["last_year"]


def backtest(table: pd.DataFrame) -> pd.DataFrame:
    """Forecast every scorable row from FIRST_ORIGIN on, refitting at each origin."""
    scored = table[(table["month"] >= FIRST_ORIGIN) & table["target"].notna()]
    rows = []
    for origin, now in scored.groupby("month"):
        # Only examples whose answer was already known at the origin.
        train = table[(table["target_month"] <= origin) & table["target"].notna()]
        model = make_pipeline(StandardScaler(), Ridge(alpha=ALPHA)).fit(train[FEATURES], train["target"])
        rows.append(now.assign(ridge=model.predict(now[FEATURES])))
    out = pd.concat(rows)
    out["naive"] = 0.0
    out["seasonal_naive"] = out["last_year"]
    return out


def scores(out: pd.DataFrame) -> dict[str, dict[str, float]]:
    """MAPE and median APE on price, per method."""
    actual = np.exp(out["log_price"] + out["target"])
    result = {}
    for method in METHODS:
        ape = (np.exp(out["log_price"] + out[method]) - actual).abs() / actual
        result[method] = {"mape": float(ape.mean()), "median_ape": float(ape.median())}
    return result


def main() -> None:
    logp = log_prices(load_hpi_table())
    report: dict = {
        "date": f"{date.today():%Y-%m-%d}",
        "series": int(logp.shape[1]),
        "data_through": f"{logp.index.max():%Y-%m}",
        "first_origin": f"{FIRST_ORIGIN:%Y-%m}",
        "ridge_alpha": ALPHA,
        "features": FEATURES,
        "horizons": {},
    }
    for h in HORIZONS:
        out = backtest(examples(logp, h))
        report["horizons"][str(h)] = {
            "forecasts": int(len(out)),
            "origins": f"{out['month'].min():%Y-%m} to {out['month'].max():%Y-%m}",
            "scores": scores(out),
            "scores_since_2022": scores(out[out["month"] >= "2022-01-01"]),
        }
    RESULTS.mkdir(exist_ok=True)
    stem = f"{report['date']}_forecast_eval"
    (RESULTS / f"{stem}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        f"# HPI forecast backtest {report['date']}",
        "",
        f"{report['series']} CREA benchmark series (region x type), data through {report['data_through']}.",
        f"Rolling origin from {report['first_origin']}; ridge refitted at every origin on past examples only "
        f"(alpha {ALPHA}, not tuned).",
        "",
        "| Horizon | Forecasts | Naive MAPE | Seasonal naive MAPE | Ridge MAPE |",
        "|---|---|---|---|---|",
    ]
    for h, r in report["horizons"].items():
        s = r["scores"]
        lines.append(f"| {h} months | {r['forecasts']:,} | {s['naive']['mape']:.2%} "
                     f"| {s['seasonal_naive']['mape']:.2%} | {s['ridge']['mape']:.2%} |")
    lines += ["", "Origins from 2022-01 (the peak and the fall after it):", "",
              "| Horizon | Naive MAPE | Seasonal naive MAPE | Ridge MAPE |", "|---|---|---|---|"]
    for h, r in report["horizons"].items():
        s = r["scores_since_2022"]
        lines.append(f"| {h} months | {s['naive']['mape']:.2%} | {s['seasonal_naive']['mape']:.2%} "
                     f"| {s['ridge']['mape']:.2%} |")
    lines.append("")
    (RESULTS / f"{stem}.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
