"""Year built for Toronto sales, from the City of Toronto cleared building permits.

The sold data never says when a house was built, and age is one of the larger
drivers of price once size and location are known. The City publishes every
building permit it has closed since 2000, with a street address and the kind of
work. A permit whose work is "New Building" at a sale address dates the house.

Two limits are stated here because nothing downstream can discover them:

* **Coverage starts around 2000.** The City says records applied for before
  October 1999 are likely incomplete, and nothing older is published at all.
  A home with no new-building permit is therefore *probably older than 2000*,
  which is useful, but it is not a year. The column is left empty.
* **The permit may be newer than the sale.** The Toronto source has no sale
  date, and the permits run to the present day, so a 2022 rebuild can attach to
  a house sold in 2019. The earliest permit at each address is kept, together
  with a count, and the sale-date question is settled where the model table
  is built (ml/dataset.py) rather than guessed at here.

Matching is on street number, street name, street type and direction, all
upper-cased, with the long street types listings use ("Court") folded to the
abbreviations the permit file uses ("CRT"). Dropping direction would merge
Queen St E with Queen St W, and dropping type would merge the two 38 Kings.

    python ml/permits.py        # writes data/processed/toronto_year_built.csv
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
PERMIT_FILES = (
    REPO / "data" / "raw" / "toronto_permits" / "cleared_permits_2000_2016.csv",
    REPO / "data" / "raw" / "toronto_permits" / "cleared_permits_since_2017.csv",
)
TORONTO_CLEAN = REPO / "data" / "processed" / "toronto_clean.csv"
OUTPUT = REPO / "data" / "processed" / "toronto_year_built.csv"

# Long street types as listings write them -> the abbreviation the permit
# file uses. Anything already abbreviated passes through unchanged.
STREET_TYPES = {
    "STREET": "ST", "AVENUE": "AVE", "ROAD": "RD", "DRIVE": "DR", "CRESCENT": "CRES",
    "BOULEVARD": "BLVD", "COURT": "CRT", "PLACE": "PL", "CIRCLE": "CRCL", "TRAIL": "TRL",
    "GARDENS": "GDNS", "TERRACE": "TERR", "SQUARE": "SQ", "PARKWAY": "PKWY",
    "HEIGHTS": "HTS", "GROVE": "GRV",
}
KNOWN_TYPES = set(STREET_TYPES.values()) | {
    "WAY", "LANE", "PK", "GATE", "HILL", "MEWS", "PATH", "RDGE", "ROW", "RUN", "VIEW",
    "WALK", "WOOD",
}
DIRECTIONS = {"E", "W", "N", "S", "EAST", "WEST", "NORTH", "SOUTH"}

# Work that means a building went up. "Second Suite (New)" and laneway suites
# are additions to a house that already exists, so they are deliberately absent.
NEW_BUILDING = re.compile(r"^NEW (R )?BUILDING")
DEAD_STATUSES = {"CANCELLED", "REFUSED", "SUPERSEDED"}
PERMIT_COLUMNS = [
    "STREET_NUM", "STREET_NAME", "STREET_TYPE", "STREET_DIRECTION",
    "WORK", "STRUCTURE_TYPE", "STATUS", "ISSUED_DATE", "COMPLETED_DATE",
]


def address_key(address: str) -> tuple[str, str, str, str] | None:
    """Turn "38 Grenville St" into ("38", "GRENVILLE", "ST", ""); None without a number."""
    words = str(address).split(",")[0].strip().upper().split()
    if len(words) < 2 or not re.fullmatch(r"\d+[A-Z]?", words[0]):
        return None
    number, rest = words[0], words[1:]
    direction = rest.pop()[0] if len(rest) > 1 and rest[-1] in DIRECTIONS else ""
    street_type = ""
    if len(rest) > 1 and (rest[-1] in KNOWN_TYPES or rest[-1] in STREET_TYPES):
        street_type = STREET_TYPES.get(rest[-1], rest[-1])
        rest.pop()
    return number, " ".join(rest), street_type, direction


def load_permits(paths: tuple[Path, ...] = PERMIT_FILES) -> pd.DataFrame:
    """New-building permits only, with a join key and the year they were issued."""
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found. Run: python data/download.py "
                "toronto_permits_2000_2016 toronto_permits_2017"
            )
    permits = pd.concat(
        [pd.read_csv(path, usecols=PERMIT_COLUMNS, dtype=str, low_memory=False) for path in paths],
        ignore_index=True,
    )
    for column in PERMIT_COLUMNS[:7]:
        permits[column] = permits[column].fillna("").str.strip().str.upper()

    keep = (
        permits["WORK"].str.match(NEW_BUILDING)
        & ~permits["STATUS"].isin(DEAD_STATUSES)
        # A new garage is a new building to the City, not a new house.
        & ~permits["STRUCTURE_TYPE"].str.contains("GARAGE", regex=False)
    )
    permits = permits[keep].copy()

    # Issued is when construction could start. 6% of rows lack it; completed
    # is never missing and is the next best date. Both formats begin YYYY.
    issued = permits["ISSUED_DATE"].replace("", None).fillna(permits["COMPLETED_DATE"])
    permits["year"] = issued.str[:4].astype(int)
    permits["key"] = (
        permits["STREET_NUM"] + "|" + permits["STREET_NAME"] + "|"
        + permits["STREET_TYPE"] + "|" + permits["STREET_DIRECTION"].str[:1]
    )
    return permits[["key", "year", "STRUCTURE_TYPE"]]


def year_built(sales: pd.DataFrame, permits: pd.DataFrame) -> pd.DataFrame:
    """mls, year_built_permit and new_building_permits for each sale.

    year_built_permit is the earliest new-building permit at the address and is
    empty where there is none. new_building_permits counts them, so a later
    rebuild is visible rather than silently overwriting the original year.
    """
    sale_key = sales["address"].map(lambda a: "|".join(k) if (k := address_key(a)) else None)
    by_address = permits.groupby("key")["year"].agg(["min", "size"])

    out = pd.DataFrame({"mls": sales["mls"].to_numpy()})
    out["year_built_permit"] = sale_key.map(by_address["min"]).astype("Int64").to_numpy()
    out["new_building_permits"] = (
        sale_key.map(by_address["size"]).fillna(0).astype(int).to_numpy()
    )
    return out


def main() -> None:
    if not TORONTO_CLEAN.exists():
        raise FileNotFoundError(f"{TORONTO_CLEAN} not found. Run: python ml/toronto.py")

    sales = pd.read_csv(TORONTO_CLEAN)
    permits = load_permits()
    out = year_built(sales, permits)
    out.to_csv(OUTPUT, index=False)

    matched = out["year_built_permit"].notna()
    print(f"{len(permits):,} new-building permits, {len(sales):,} sales -> {OUTPUT.relative_to(REPO)}")
    print(f"year built from a permit: {matched.sum():,} ({matched.mean():.1%})\n")
    print(
        out.assign(property_type=sales["property_type"].to_numpy())
        .groupby("property_type")["year_built_permit"]
        .agg(matched="count", earliest="min", median="median", latest="max")
        .to_string()
    )
    rebuilt = (out["new_building_permits"] > 1).sum()
    print(f"\naddresses with more than one new-building permit: {rebuilt:,}")


if __name__ == "__main__":
    main()
