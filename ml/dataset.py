"""Assemble the model table: one row per sale with every feature joined on.

Everything upstream produces one narrow file per idea (prices, lots, keywords,
year built). This is the only place they meet, so it is also the only place the
target is defined:

    target = log(sold_price / benchmark_then)

where benchmark_then is the CREA benchmark for the sale's region and property
type in the month it sold. The number is "how this house compares with the
typical home of its type at the time", in log space so that a feature's effect
reads as a percentage premium. Fair value for a listing today is then

    benchmark_now * exp(model prediction)

and the baseline the model has to beat is predicting zero, i.e. "every house is
worth exactly its benchmark".

Year built is coalesced here, because the rule depends on the Toronto sale
month decided in ml/adjust.py: a permit issued after the assumed sale year
cannot describe the house that was sold, so it is dropped in favour of what the
agent wrote, if anything.

    python ml/dataset.py        # writes data/processed/model_table.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from adjust import HPI_REGION, HPI_TYPE, TORONTO_ASSUMED_MONTH, benchmarks, load_hpi_table
from keywords import FLAGS

REPO = Path(__file__).resolve().parent.parent
PROCESSED = REPO / "data" / "processed"
OUTPUT = PROCESSED / "model_table.csv"

INPUTS = {
    "toronto_adjusted": PROCESSED / "toronto_adjusted.csv",
    "toronto_lots": PROCESSED / "toronto_lots.csv",
    "toronto_keywords": PROCESSED / "toronto_keywords.csv",
    "toronto_year_built": PROCESSED / "toronto_year_built.csv",
    "toronto_footprints": PROCESSED / "toronto_footprints.csv",
    "brampton_adjusted": PROCESSED / "brampton_adjusted.csv",
}

# Columns the model may see. Brampton has only the first block; the rest are
# empty for it, which LightGBM treats as "unknown" rather than zero.
CATEGORICAL = ["property_type", "region"]
NUMERIC = [
    "beds_above", "beds_below", "baths",
    "sqft_mid", "footprint_m2", "parking", "lat", "long", "lot_area_m2", "year_built",
    *FLAGS,
]
FEATURES = CATEGORICAL + NUMERIC

# Columns that must never be features. list_price carries the market heat of
# its own moment; the rest identify the row or are the answer.
NEVER_FEATURES = {"mls", "source", "district", "sold_price", "list_price", "sold_month",
                  "hpi_factor", "price_today", "benchmark_then", "target"}


def _check(paths: dict[str, Path]) -> None:
    missing = [name for name, path in paths.items() if not path.exists()]
    if missing:
        raise FileNotFoundError(
            f"missing processed tables: {missing}. Run the ml/ scripts listed in the README."
        )


def coalesce_year_built(toronto: pd.DataFrame) -> pd.Series:
    """Permit year if it predates the assumed sale, else what the agent wrote.

    A permit after the sale year is a later rebuild or a pre-construction unit,
    so it says nothing about the house that changed hands.
    """
    sale_year = TORONTO_ASSUMED_MONTH.year
    permit = toronto["year_built_permit"].where(toronto["year_built_permit"] <= sale_year)
    stated = toronto["year_built_stated"].where(toronto["year_built_stated"] <= sale_year)
    return permit.fillna(stated).astype("Float64")


def _benchmark_then(sales: pd.DataFrame, hpi: pd.DataFrame, city: str) -> np.ndarray:
    table = benchmarks(hpi, HPI_REGION[city])
    index = pd.MultiIndex.from_arrays(
        [sales["property_type"].map(HPI_TYPE), pd.to_datetime(sales["sold_month"])]
    )
    then = table.reindex(index)
    if then.isna().any():
        raise ValueError(f"no benchmark for some {city} sales")
    return then.to_numpy()


def build(paths: dict[str, Path] = INPUTS) -> pd.DataFrame:
    """Return the model table. Features in FEATURES, target in 'target'."""
    _check(paths)
    hpi = load_hpi_table()

    toronto = pd.read_csv(paths["toronto_adjusted"])
    for name in ("toronto_lots", "toronto_keywords", "toronto_year_built", "toronto_footprints"):
        extra = pd.read_csv(paths[name])
        toronto = toronto.merge(extra, on="mls", how="left", validate="one_to_one")
    toronto["year_built"] = coalesce_year_built(toronto)
    toronto["source"] = "toronto"
    toronto["region"] = HPI_REGION["Toronto"]
    toronto["district"] = toronto["city_district"]
    toronto["benchmark_then"] = _benchmark_then(toronto, hpi, "Toronto")

    brampton = pd.read_csv(paths["brampton_adjusted"])
    brampton["source"] = "brampton"
    brampton["region"] = HPI_REGION["Brampton"]
    brampton["district"] = brampton["community"]
    brampton["benchmark_then"] = _benchmark_then(brampton, hpi, "Brampton")

    keep = ["mls", "source", "district", "sold_price", "sold_month", "hpi_factor",
            "price_today", "benchmark_then", *FEATURES]
    table = pd.concat(
        [toronto.reindex(columns=keep), brampton.reindex(columns=keep)], ignore_index=True
    )
    for flag in FLAGS:
        # Brampton has no descriptions, so its flags are unknown, not False.
        table[flag] = table[flag].astype("Float64")
    table["target"] = np.log(table["sold_price"] / table["benchmark_then"])
    return table


def main() -> None:
    table = build()
    table.to_csv(OUTPUT, index=False)
    print(f"{len(table):,} rows x {len(FEATURES)} features -> {OUTPUT.relative_to(REPO)}")
    print(table["source"].value_counts().to_string(), end="\n\n")
    print("feature coverage (share of rows with a value):")
    coverage = table[NUMERIC].notna().mean().sort_values(ascending=False)
    for name, share in coverage.items():
        print(f"  {name:20} {share:6.1%}")
    print(
        f"\ntarget = log(sold / benchmark): median {table['target'].median():+.3f}, "
        f"IQR {table['target'].quantile(0.25):+.3f} to {table['target'].quantile(0.75):+.3f}"
    )


if __name__ == "__main__":
    main()
