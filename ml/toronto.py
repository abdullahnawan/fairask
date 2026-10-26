"""Clean the Toronto sold dataset into model-ready rows.

The raw file is a scrape of listing pages, so the useful numbers arrive as
display strings: bedrooms as "3 + 1 beds", square footage as a bucket like
"800-899 sq. ft.", parking as "no parking". This turns each into a number, and
refuses rather than guesses when a value does not parse — a silent zero in a
price model is worse than a crash.

Two quirks of this particular file:

* One row (index 14) holds a scraped HTML error page instead of listing fields.
  It is dropped.
* The square-footage buckets are not one consistent scheme. "1400-1599",
  "1100-1500" and "700-1100" all appear, so the buckets overlap and a midpoint
  is an approximation, not a measurement. Both bounds are kept alongside it so
  later code can treat the width honestly.

    python ml/toronto.py        # writes data/processed/toronto_clean.csv
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO / "data" / "raw" / "toronto_sales" / "houses.csv"
OUTPUT = REPO / "data" / "processed" / "toronto_clean.csv"

# The four types FairAsk values. Everything else in the file is out of scope:
# multi-unit (Duplex, Triplex, Multiplex, Store W/Apt/Offc), non-freehold
# ownership (Co-Op Apt, Co-Ownership Apt, Leasehold Condo), and a handful of
# oddities (Link, Comm Element Condo, Det Condo, Cottage) whose mapping is a
# judgement call. They are dropped and counted rather than guessed at.
# shortcut: revisit if the model needs the ~240 dropped Link/Comm Element rows.
TYPE_MAP = {
    "Detached": "detached",
    "Semi-Detached": "semi_detached",
    "Att/Row/Twnhouse": "townhouse",
    "Condo Townhouse": "townhouse",
    "Condo Apt": "condo_apartment",
}
PROPERTY_TYPES = tuple(sorted(set(TYPE_MAP.values())))

# "3 beds" or "2 + 1 beds" — the second number is bedrooms below grade.
_BEDS = re.compile(r"^\s*(\d+)\s*(?:\+\s*(\d+)\s*)?beds?\s*$", re.IGNORECASE)
# Buckets use an en dash, except "0-499" which uses a plain hyphen.
_SQFT = re.compile(r"^\s*(\d+)\s*[-\u2013]\s*(\d+)\s*sq\.\s*ft\.\s*$", re.IGNORECASE)
_SQFT_MISSING = re.compile(r"^\s*(N/A|NA|)\s*sq\.\s*ft\.\s*$", re.IGNORECASE)
_PARKING = re.compile(r"^\s*(?:(\d+)\s*parking|no\s*parking)\s*$", re.IGNORECASE)


def parse_beds(text: str) -> tuple[int, int]:
    """"2 + 1 beds" -> (2 above grade, 1 below grade)."""
    match = _BEDS.match(str(text))
    if not match:
        raise ValueError(f"cannot parse bedrooms: {text!r}")
    return int(match.group(1)), int(match.group(2) or 0)


def parse_sqft_range(text: str) -> tuple[int | None, int | None]:
    """"800-899 sq. ft." -> (800, 899). "N/A sq. ft." -> (None, None)."""
    text = str(text)
    if match := _SQFT.match(text):
        return int(match.group(1)), int(match.group(2))
    if _SQFT_MISSING.match(text):
        return None, None
    raise ValueError(f"cannot parse square footage: {text!r}")


def parse_parking(text: str) -> int:
    """"no parking" is a real zero, not a missing value."""
    match = _PARKING.match(str(text))
    if not match:
        raise ValueError(f"cannot parse parking: {text!r}")
    return int(match.group(1) or 0)


def load_toronto(path: Path = DEFAULT_CSV) -> pd.DataFrame:
    """Return one cleaned row per listing, for the four in-scope property types."""
    if not path.exists():
        raise FileNotFoundError(
            f"Toronto CSV not found at {path}. Run: python data/download.py toronto"
        )

    raw = pd.read_csv(path)

    # One row is a scraped HTML error page; its type field holds markup.
    raw = raw[~raw["type"].astype(str).str.contains("<", regex=False)]

    in_scope = raw[raw["type"].isin(TYPE_MAP)].copy()

    beds = in_scope["bedrooms"].map(parse_beds)
    sqft = in_scope["sqft"].map(parse_sqft_range)

    clean = pd.DataFrame(
        {
            "mls": in_scope["mls"].astype(str),
            "sold_price": in_scope["final_price"].astype("int64"),
            "list_price": in_scope["list_price"].astype("int64"),
            "property_type": in_scope["type"].map(TYPE_MAP),
            "beds_above": [b[0] for b in beds],
            "beds_below": [b[1] for b in beds],
            "baths": in_scope["bathrooms"].str.extract(r"(\d+)", expand=False).astype("int64"),
            "parking": in_scope["parking"].map(parse_parking),
            "sqft_min": [s[0] for s in sqft],
            "sqft_max": [s[1] for s in sqft],
            "lat": in_scope["lat"].astype(float),
            "long": in_scope["long"].astype(float),
            "city_district": in_scope["city_district"],
            "mean_district_income": in_scope["mean_district_income"],
            "description": in_scope["description"],
        }
    )
    clean["beds_total"] = clean["beds_above"] + clean["beds_below"]
    clean["sqft_mid"] = (clean["sqft_min"] + clean["sqft_max"]) / 2

    return clean.reset_index(drop=True)


def main() -> None:
    raw = pd.read_csv(DEFAULT_CSV)
    clean = load_toronto()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    clean.to_csv(OUTPUT, index=False)

    dropped = len(raw) - len(clean)
    print(f"{len(raw):,} raw rows -> {len(clean):,} clean ({dropped:,} dropped)")
    print(f"written to {OUTPUT.relative_to(REPO)}\n")
    print(clean["property_type"].value_counts().to_string())
    missing = clean["sqft_mid"].isna().sum()
    print(f"\nsquare footage missing: {missing:,} rows ({missing / len(clean):.1%})")


if __name__ == "__main__":
    main()
