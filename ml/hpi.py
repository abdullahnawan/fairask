"""Load the CREA MLS HPI workbook into one tidy monthly table.

The workbook ships one sheet per region, each wide: a Date column, six
`<type>_HPI` index columns and six `<type>_Benchmark` price columns. Fair value
needs the opposite shape — one row per region, type and month — so this reshapes
it once and every later step joins against that.

CREA's own property-type names are kept. They do not line up with the four types
FairAsk accepts (there is no semi-detached series, and Single_Family covers both
detached and semi), so mapping between them is a valuation decision and belongs
with the valuation code, not in a loader.

    python ml/hpi.py        # writes data/processed/hpi_monthly.csv
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DEFAULT_WORKBOOK = REPO / "data" / "raw" / "crea_hpi" / "Not Seasonally Adjusted (M).xlsx"
OUTPUT = REPO / "data" / "processed" / "hpi_monthly.csv"

# Not seasonally adjusted, because these are the benchmark prices CREA publishes
# as the headline figure for a region and type in a given month.

# sheet name -> the region name used everywhere else in FairAsk
REGIONS = {
    "CAMBRIDGE": "Cambridge",
    "KITCHENER_WATERLOO": "Kitchener-Waterloo",
    "GREATER_TORONTO": "Greater Toronto",
    "MISSISSAUGA": "Mississauga",
    "OAKVILLE_MILTON": "Oakville-Milton",
}

PROPERTY_TYPES = (
    "Composite",
    "Single_Family",
    "One_Storey",
    "Two_Storey",
    "Townhouse",
    "Apartment",
)


def load_hpi(
    workbook: Path = DEFAULT_WORKBOOK,
    regions: dict[str, str] = REGIONS,
) -> pd.DataFrame:
    """Return one row per region, property type and month.

    Columns: region, property_type, month, hpi_index, benchmark_price.
    Benchmark prices are whole dollars, as CREA publishes them.
    """
    if not workbook.exists():
        raise FileNotFoundError(
            f"CREA HPI workbook not found at {workbook}. "
            "It is a manual download; see data/SOURCES.md."
        )

    frames = []
    for sheet, region in regions.items():
        wide = pd.read_excel(workbook, sheet_name=sheet)
        missing = [
            column
            for ptype in PROPERTY_TYPES
            for column in (f"{ptype}_HPI", f"{ptype}_Benchmark")
            if column not in wide.columns
        ]
        if missing:
            raise ValueError(f"sheet {sheet} is missing columns: {missing}")

        for ptype in PROPERTY_TYPES:
            frames.append(
                pd.DataFrame(
                    {
                        "region": region,
                        "property_type": ptype,
                        "month": pd.to_datetime(wide["Date"]),
                        "hpi_index": wide[f"{ptype}_HPI"].astype(float),
                        "benchmark_price": wide[f"{ptype}_Benchmark"].astype("int64"),
                    }
                )
            )

    tidy = pd.concat(frames, ignore_index=True)
    return tidy.sort_values(["region", "property_type", "month"], ignore_index=True)


def main() -> None:
    tidy = load_hpi()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    tidy.to_csv(OUTPUT, index=False)
    print(
        f"{len(tidy):,} rows -> {OUTPUT.relative_to(REPO)}\n"
        f"{tidy['region'].nunique()} regions x {tidy['property_type'].nunique()} types x "
        f"{tidy['month'].nunique()} months "
        f"({tidy['month'].min():%Y-%m} to {tidy['month'].max():%Y-%m})"
    )


if __name__ == "__main__":
    main()
