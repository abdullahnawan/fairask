"""Clean the Brampton sold dataset into model-ready rows.

This source is a PDF extraction, and the extraction went wrong in several ways
that all have to be handled or the model trains on nonsense:

* **Every listing may appear twice.** 46 MLS numbers repeat. The second copy is
  a worse pass over the same page: prices misgrouped as "$4,49,000", padded
  whitespace, and sometimes disagreeing attributes — one pair differs on both
  community and washroom count. Of the 46, 42 have exactly one well-formed copy,
  so the well-formed one wins. Where both are well-formed they turned out to be
  genuinely different addresses sharing a misread MLS number, and both are kept.
* **Prices lose digits.** Two rows sold at a tenth of list price ($799,000 ->
  $79,900). Anything outside a 0.5-2.0 sold/list band is an error, not a bargain.
* **Dates are mixed format.** 693 rows prove M/D/YYYY (second component > 12),
  but six dates land outside the documented Jan-May 2021 window: five look like
  D/M transpositions and one is a year typo ("3/17/2001"). Rather than guess at
  a correction, those rows are dropped. Recovering them is a judgement call
  that needs a human.
* **Categorical values are clipped** to a fixed width: "Semi-Detac", "Electr",
  "Grnd S", "Built-". They are kept exactly as found. Expanding them would mean
  inventing the missing characters.

Unlike the Toronto source this file has no square footage, no coordinates and no
parking count — only a garage type. Those columns are absent rather than filled
with zeros, so nothing downstream can mistake a gap for a measurement.

    python ml/brampton.py        # writes data/processed/brampton_clean.csv
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO / "data" / "raw" / "brampton_sales" / "Sold_homes_combined_final.csv"
OUTPUT = REPO / "data" / "processed" / "brampton_clean.csv"

# The dataset is documented as January to May 2021. Dates outside this are
# extraction errors, not sales.
SOLD_WINDOW = ("2021-01-01", "2021-05-31")

# A sold price this far from list price is a lost digit, not a real sale.
RATIO_BAND = (0.5, 2.0)

# Values arrive clipped to a fixed width, so these keys are deliberately short.
# Brampton's file contains no condo apartments.
TYPE_MAP = {
    "Detached": "detached",
    "Semi-Detac": "semi_detached",
    "Att/Row/Tw": "townhouse",
}
PROPERTY_TYPES = tuple(sorted(set(TYPE_MAP.values())))

# Canadian grouping: one to three digits, then strict groups of three.
_WELL_FORMED_PRICE = re.compile(r"^\$\d{1,3}(?:,\d{3})*$")


def parse_price(text: str) -> int:
    """"$599,000" -> 599000. Misgrouped commas give the same digits."""
    digits = re.sub(r"[^0-9]", "", str(text))
    if not digits:
        raise ValueError(f"cannot parse price: {text!r}")
    return int(digits)


def is_well_formed_price(text: str) -> bool:
    """True when commas fall in the right places, marking the better extraction."""
    return bool(_WELL_FORMED_PRICE.match(str(text).strip()))


def load_brampton(path: Path = DEFAULT_CSV) -> pd.DataFrame:
    """Return one cleaned row per sale, for the three in-scope property types."""
    if not path.exists():
        raise FileNotFoundError(
            f"Brampton CSV not found at {path}. Run: python data/download.py brampton"
        )

    raw = pd.read_csv(path)

    # Trim the padding the extraction left behind before anything is compared.
    for column in raw.columns:
        if raw[column].dtype == object:
            raw[column] = raw[column].astype(str).str.strip().replace({"nan": None, "": None})

    # Prefer the better extraction of each listing, then drop the rest.
    raw["_well_formed"] = raw["List Price"].map(is_well_formed_price) & raw["Sold Price"].map(
        is_well_formed_price
    )
    raw = raw.sort_values("_well_formed", ascending=False)
    raw = raw.drop_duplicates(subset=["MLS#", "St#", "Street Name"], keep="first")

    in_scope = raw[raw["Type"].isin(TYPE_MAP)].copy()

    contract_date = pd.to_datetime(in_scope["Contract Date"], format="%m/%d/%Y", errors="coerce")
    sold_date = pd.to_datetime(in_scope["Sold Date"], format="%m/%d/%Y", errors="coerce")

    clean = pd.DataFrame(
        {
            "mls": in_scope["MLS#"],
            "sold_price": in_scope["Sold Price"].map(parse_price).astype("int64"),
            "list_price": in_scope["List Price"].map(parse_price).astype("int64"),
            "property_type": in_scope["Type"].map(TYPE_MAP),
            "style": in_scope["Style"],
            "beds_above": in_scope["Br"].astype("int64"),
            "beds_below": in_scope["Additional"].astype("int64"),
            "baths": in_scope["Wr"].astype("int64"),
            "kitchens": in_scope["Kit"].astype("int64"),
            "has_family_room": in_scope["Fam"].eq("Y"),
            "garage_type": in_scope["Garage Type"],
            "air_conditioning": in_scope["A/C"],
            "heat": in_scope["Heat"],
            "community": in_scope["Community"],
            "street_number": in_scope["St#"],
            "street_name": in_scope["Street Name"],
            "contract_date": contract_date,
            "sold_date": sold_date,
        }
    )
    clean["beds_total"] = clean["beds_above"] + clean["beds_below"]
    clean["days_on_market"] = (clean["sold_date"] - clean["contract_date"]).dt.days

    start, end = SOLD_WINDOW
    low, high = RATIO_BAND
    ratio = clean["sold_price"] / clean["list_price"]
    keep = (
        clean["sold_date"].between(pd.Timestamp(start), pd.Timestamp(end))
        & clean["contract_date"].notna()
        & (clean["sold_date"] >= clean["contract_date"])
        & ratio.between(low, high)
    )
    return clean[keep].reset_index(drop=True)


def main() -> None:
    raw = pd.read_csv(DEFAULT_CSV)
    clean = load_brampton()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    clean.to_csv(OUTPUT, index=False)

    print(f"{len(raw):,} raw rows -> {len(clean):,} clean ({len(raw) - len(clean):,} dropped)")
    print(f"written to {OUTPUT.relative_to(REPO)}\n")
    print(clean["property_type"].value_counts().to_string())
    print(
        f"\nsold {clean['sold_date'].min():%Y-%m-%d} to {clean['sold_date'].max():%Y-%m-%d}"
        f"\nmedian days on market: {clean['days_on_market'].median():.0f}"
        f"\nmedian sold/list: {(clean['sold_price'] / clean['list_price']).median():.3f}"
    )


if __name__ == "__main__":
    main()
