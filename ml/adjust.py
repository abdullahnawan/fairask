"""Time-adjust past sale prices to the latest month the HPI covers.

A house that sold for $700k in March 2021 is not evidence that it is worth
$700k now. Training on raw sold prices would teach the model that 2021 Brampton
and 2019 Toronto describe the same market, and the biggest signal in the data
would be the year, not the house. This multiplies each sale by the change in the
CREA benchmark for its region and property type between the month it sold and
the target month, so every price is quoted in the same month's dollars.

Two mappings live here rather than in `ml/hpi.py`, because they are valuation
judgements, not facts about the workbook:

* **Region.** CREA publishes no Brampton series. Brampton and Toronto sales are
  both adjusted with the Greater Toronto benchmark, which is the aggregate they
  belong to. Within-GTA differences in how fast a submarket moved are lost.
* **Property type.** CREA has no semi-detached series, so semis are adjusted
  with Single_Family, the same series as detached.

    python ml/adjust.py        # writes data/processed/brampton_adjusted.csv
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
HPI_TABLE = REPO / "data" / "processed" / "hpi_monthly.csv"
BRAMPTON_CLEAN = REPO / "data" / "processed" / "brampton_clean.csv"
OUTPUT = REPO / "data" / "processed" / "brampton_adjusted.csv"

# city a sale is in -> the CREA region whose benchmark tracks it
HPI_REGION = {
    "Toronto": "Greater Toronto",
    "Brampton": "Greater Toronto",
    "Mississauga": "Mississauga",
    "Cambridge": "Cambridge",
    "Kitchener": "Kitchener-Waterloo",
    "Waterloo": "Kitchener-Waterloo",
}

# FairAsk property type -> the CREA series used to move its price through time
HPI_TYPE = {
    "detached": "Single_Family",
    "semi_detached": "Single_Family",
    "townhouse": "Townhouse",
    "condo_apartment": "Apartment",
}


def load_hpi_table(path: Path = HPI_TABLE) -> pd.DataFrame:
    """Read the tidy HPI table written by ml/hpi.py."""
    if not path.exists():
        raise FileNotFoundError(f"HPI table not found at {path}. Run: python ml/hpi.py")
    return pd.read_csv(path, parse_dates=["month"])


def benchmarks(hpi: pd.DataFrame, region: str) -> pd.Series:
    """Benchmark price for one region, indexed by (CREA property type, month)."""
    rows = hpi[hpi["region"] == region]
    if rows.empty:
        raise ValueError(f"no HPI rows for region {region!r}")
    return rows.set_index(["property_type", "month"])["benchmark_price"]


def time_adjust(
    sales: pd.DataFrame,
    hpi: pd.DataFrame,
    city: str,
    target_month: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Add sold_month, hpi_factor and price_today to a cleaned sales frame.

    `sales` needs sold_date, sold_price and property_type. The target defaults to
    the newest month in the HPI — never "today", because the benchmark stops
    where CREA's last release does and adjusting past it would be extrapolation.
    """
    region = HPI_REGION[city]
    table = benchmarks(hpi, region)
    target = pd.Timestamp(target_month) if target_month else table.index.levels[1].max()

    sold_month = pd.to_datetime(sales["sold_date"]).dt.to_period("M").dt.to_timestamp()
    crea_type = sales["property_type"].map(HPI_TYPE)
    if crea_type.isna().any():
        unmapped = sorted(sales.loc[crea_type.isna(), "property_type"].unique())
        raise ValueError(f"no HPI series for property type: {unmapped}")

    then = table.reindex(pd.MultiIndex.from_arrays([crea_type, sold_month]))
    now = table.reindex(pd.MultiIndex.from_arrays([crea_type, [target] * len(sales)]))
    if then.isna().any() or now.isna().any():
        raise ValueError(
            f"{region} HPI does not cover every sale month between "
            f"{sold_month.min():%Y-%m} and {target:%Y-%m}"
        )

    adjusted = sales.copy()
    adjusted["sold_month"] = sold_month.to_numpy()
    adjusted["hpi_factor"] = now.to_numpy() / then.to_numpy()
    adjusted["price_today"] = (adjusted["sold_price"] * adjusted["hpi_factor"]).round().astype(
        "int64"
    )
    return adjusted


def main() -> None:
    # Only Brampton is adjusted here. The Toronto source carries no sale date at
    # all, so there is no month to adjust its rows from; see data/SOURCES.md.
    if not BRAMPTON_CLEAN.exists():
        raise FileNotFoundError(
            f"{BRAMPTON_CLEAN} not found. Run: python ml/brampton.py"
        )

    sales = pd.read_csv(BRAMPTON_CLEAN, parse_dates=["sold_date", "contract_date"])
    hpi = load_hpi_table()
    adjusted = time_adjust(sales, hpi, city="Brampton")
    adjusted.to_csv(OUTPUT, index=False)

    target = adjusted["sold_month"].max()
    print(f"{len(adjusted):,} Brampton sales -> {OUTPUT.relative_to(REPO)}")
    print(
        f"sold {adjusted['sold_month'].min():%Y-%m} to {target:%Y-%m}, "
        f"adjusted to {load_hpi_table()['month'].max():%Y-%m}\n"
    )
    print(
        adjusted.groupby("property_type")
        .agg(
            sales=("sold_price", "size"),
            median_sold=("sold_price", "median"),
            median_today=("price_today", "median"),
            factor=("hpi_factor", "median"),
        )
        .round(3)
        .to_string()
    )


if __name__ == "__main__":
    main()
