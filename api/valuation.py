"""Fair value for one listing: today's benchmark x the model's adjustment.

    fair value = benchmark now (region, type) x exp(model prediction)
    range      = benchmark now x exp(p10 - margin) .. exp(p90 + margin)

The models and the feature spec are the ones ml/train.py saved. The reasons are
the model's SHAP contributions, turned into dollars by ml/explain.py and into
plain words here. Latitude and longitude are reported together as "Location".
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ml"))
from adjust import HPI_TYPE  # noqa: E402
from explain import MODELS, contributions, load, prepare  # noqa: E402

SQFT_PER_M2 = 10.7639

FLAG_LABELS = {
    "basement_finished": "Finished basement",
    "basement_apartment": "Basement apartment or separate entrance",
    "basement_walkout": "Walkout basement",
    "garage": "Garage",
    "renovated": "Renovated or updated",
    "new_build": "New build",
    "pool": "Pool",
    "ravine": "Ravine lot",
}


@dataclass(frozen=True)
class Reason:
    text: str
    dollars_cents: int   # positive: this raised the fair value


@dataclass(frozen=True)
class Valuation:
    benchmark_cents: int
    benchmark_month: str
    fair_cents: int
    low_cents: int
    high_cents: int
    reasons: list[Reason]


@lru_cache(maxsize=1)
def models(path: Path = MODELS) -> tuple[lgb.Booster, lgb.Booster, lgb.Booster, dict]:
    booster, spec = load(path)
    low = lgb.Booster(model_file=str(path / "quantile_p10.txt"))
    high = lgb.Booster(model_file=str(path / "quantile_p90.txt"))
    return booster, low, high, spec


def describe(feature: str, value: object) -> str:
    """What a feature's value means for this house, in words."""
    if feature in ("lat", "long"):
        return "Location"
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return f"{feature.replace('_', ' ').capitalize()} not given"
    if feature in FLAG_LABELS:
        return FLAG_LABELS[feature] if value else f"No {FLAG_LABELS[feature].lower()} mentioned"
    v = float(value) if not isinstance(value, str) else value
    return {
        "property_type": lambda: str(v).replace("_", " ").capitalize(),
        "region": lambda: f"Region: {v}",
        "beds_above": lambda: f"{v:g} bedroom{'s' * (v != 1)} above grade",
        "beds_below": lambda: f"{v:g} bedroom{'s' * (v != 1)} below grade",
        "baths": lambda: f"{v:g} bathroom{'s' * (v != 1)}",
        "sqft_mid": lambda: f"{v:,.0f} sq ft",
        "parking": lambda: f"{v:g} parking space{'s' * (v != 1)}",
        "lot_area_m2": lambda: f"Lot of {v * SQFT_PER_M2:,.0f} sq ft",
        "year_built": lambda: f"Built in {v:.0f}",
        "footprint_m2": lambda: "Building footprint",
    }[feature]()


def benchmark_now(hpi: pd.DataFrame, region: str, property_type: str) -> tuple[float, str]:
    crea_type = HPI_TYPE[property_type]
    series = hpi[(hpi["region"] == region) & (hpi["property_type"] == crea_type)]
    if series.empty:
        raise KeyError(f"no HPI series for {region} / {crea_type}")
    latest = series.sort_values("month").iloc[-1]
    return float(latest["benchmark_price"]), f"{pd.Timestamp(latest['month']):%Y-%m}"


def value(listing: dict, hpi: pd.DataFrame, top: int = 5) -> Valuation:
    """listing holds the model's features by name; missing ones are unknown."""
    booster, low_model, high_model, spec = models()
    benchmark, month = benchmark_now(hpi, listing["region"], listing["property_type"])
    # None -> NaN so LightGBM reads "unknown"; an untrained region is unknown too.
    row = {k: np.nan if v is None else v for k, v in listing.items()}
    if row["region"] not in spec["categories"]["region"]:
        row["region"] = np.nan
    X = prepare(pd.DataFrame([row]), spec)
    margin = spec["range_margin_log"]
    log_fair = float(booster.predict(X)[0])
    log_low = min(float(low_model.predict(X)[0]) - margin, log_fair)    # quantiles can cross
    log_high = max(float(high_model.predict(X)[0]) + margin, log_fair)
    fair = benchmark * np.exp(log_fair)

    table = contributions(booster, X, benchmark, top=len(X.columns))
    table["text"] = [describe(f, v) for f, v in zip(table["feature"], table["value"])]
    # Contributions add in log space, so grouped ones (lat + long) are summed there.
    grouped = table.groupby("text", sort=False)["shap"].sum()
    dollars = fair * (1 - np.exp(-grouped))
    order = dollars.abs().sort_values(ascending=False).index[:top]
    return Valuation(
        benchmark_cents=round(benchmark) * 100,
        benchmark_month=month,
        fair_cents=round(fair) * 100,
        low_cents=round(benchmark * np.exp(log_low)) * 100,
        high_cents=round(benchmark * np.exp(log_high)) * 100,
        reasons=[Reason(text, round(dollars[text]) * 100) for text in order],
    )
