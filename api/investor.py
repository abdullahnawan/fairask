"""Investor view: what a home would rent for and whether the rent covers it.

Rent is CMHC's average for a new tenant ("turnover" rent) in the listing's
metro area and bedroom count, from the 2025 Rental Market Survey
(data/processed/cmhc_rents.csv). CMHC surveys purpose-built apartment buildings,
so for a house the figure is a floor, and the report shows CMHC's reliability
grade beside it.

    gross yield = 12 x monthly rent / price
    cash flow   = rent - mortgage payment - monthly costs - vacancy and
                  maintenance allowances (shares of rent)

Allowances default to zero so the numbers only include what the user entered
or accepted; the API decides what to suggest.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# FairAsk HPI region -> CMHC census metropolitan area. Oakville and Milton
# are inside the Toronto CMA; Cambridge shares Kitchener-Waterloo's.
CMHC_CENTRE = {
    "Greater Toronto": "Toronto CMA",
    "Mississauga": "Toronto CMA",
    "Oakville-Milton": "Toronto CMA",
    "Kitchener-Waterloo": "Kitchener-Cambridge-Waterloo CMA",
    "Cambridge": "Kitchener-Cambridge-Waterloo CMA",
}
BEDROOM_GROUPS = ("Studio", "1 Bedroom", "2 Bedroom", "3 Bedroom +")


@dataclass(frozen=True)
class Rent:
    rent_cents: int
    centre: str
    survey: str
    reliability: str | None


@dataclass(frozen=True)
class InvestorView:
    rent_cents: int
    gross_yield: float
    monthly_costs_cents: int
    cash_flow_cents: int   # negative means the owner tops it up every month


def cmhc_rent(rents: pd.DataFrame, region: str, bedrooms: int) -> Rent | None:
    """CMHC turnover rent for the region's metro area; None if unknown or suppressed."""
    centre = CMHC_CENTRE.get(region)
    group = BEDROOM_GROUPS[min(max(bedrooms, 0), 3)]
    row = rents[(rents["centre"] == centre) & (rents["bedrooms"] == group)]
    if row.empty or pd.isna(row["rent"].iloc[0]):
        return None
    grade = row["reliability"].iloc[0]
    return Rent(int(row["rent"].iloc[0]) * 100, centre, str(row["survey"].iloc[0]),
                None if pd.isna(grade) else str(grade))


def investor_view(
    price_cents: int,
    rent_cents: int,
    mortgage_payment_cents: int,
    property_tax_cents: int = 0,
    condo_fees_cents: int = 0,
    insurance_cents: int = 0,
    vacancy_share: float = 0.0,
    maintenance_share: float = 0.0,
) -> InvestorView:
    money = (price_cents, rent_cents, mortgage_payment_cents, property_tax_cents,
             condo_fees_cents, insurance_cents)
    if not all(type(v) is int for v in money):
        raise TypeError("money must be integer cents")
    if price_cents <= 0 or min(money) < 0:
        raise ValueError("price must be positive and costs cannot be negative")
    # A share passed as a percentage (5 for 5%) would wipe out the cash flow.
    if not (0 <= vacancy_share < 1 and 0 <= maintenance_share < 1):
        raise ValueError("vacancy and maintenance are shares of rent between 0 and 1")
    allowances = round(rent_cents * (vacancy_share + maintenance_share))
    costs = mortgage_payment_cents + property_tax_cents + condo_fees_cents + insurance_cents
    return InvestorView(
        rent_cents=rent_cents,
        gross_yield=12 * rent_cents / price_cents,
        monthly_costs_cents=costs,
        cash_flow_cents=rent_cents - costs - allowances,
    )
