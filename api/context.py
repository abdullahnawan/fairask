"""Market context and red flags for the deal report.

Context answers "what is this market doing?" from two sources:

* the CREA HPI benchmark for the listing's region and type: change over 1 and
  5 years, and how far it sits from its peak (data/processed/hpi_monthly.csv);
* TRREB Market Watch for its municipality or Toronto district: the
  sales-to-new-listings ratio (SNLR), average days on market and sale-to-list
  ratio (data/processed/trreb_market.csv, GTA only).

Buyer's or seller's market uses CREA's convention on SNLR: under 40% buyer's,
40% to 60% balanced, over 60% seller's.

Red flags are plain sentences, each one a reason to look closer, not a verdict:
a listing sitting twice as long as its area's average (or 60 days with no area
figure), any price cut, and an asking price more than one range-half outside
the fair value range.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

BUYERS_BELOW, SELLERS_ABOVE = 40.0, 60.0
STALE_DAYS_WITHOUT_AREA = 60


@dataclass(frozen=True)
class HpiContext:
    month: str
    benchmark_cents: int
    change_1y: float | None
    change_5y: float | None
    peak_month: str
    from_peak: float      # 0 at the peak, negative below it


@dataclass(frozen=True)
class AreaMarket:
    area: str
    month: str
    snlr: float
    balance: str
    months_inventory: float
    avg_days_on_market: int
    sale_to_list: float   # 1.06 means homes sold 6% over asking on average


def hpi_context(hpi: pd.DataFrame, region: str, crea_type: str) -> HpiContext:
    series = hpi[(hpi["region"] == region) & (hpi["property_type"] == crea_type)]
    if series.empty:
        raise KeyError(f"no HPI series for {region} / {crea_type}")
    prices = series.set_index(pd.to_datetime(series["month"]))["benchmark_price"].sort_index()
    latest, now = prices.index[-1], prices.iloc[-1]

    def change(years: int) -> float | None:
        then = latest - pd.DateOffset(years=years)
        return float(now / prices[then] - 1) if then in prices.index else None

    peak = prices.idxmax()
    return HpiContext(
        month=f"{latest:%Y-%m}",
        benchmark_cents=int(now) * 100,
        change_1y=change(1),
        change_5y=change(5),
        peak_month=f"{peak:%Y-%m}",
        from_peak=float(now / prices[peak] - 1),
    )


def market_balance(snlr: float) -> str:
    if snlr < BUYERS_BELOW:
        return "Buyer's market"
    return "Seller's market" if snlr > SELLERS_ABOVE else "Balanced market"


def area_market(trreb: pd.DataFrame, area: str) -> AreaMarket | None:
    """The TRREB figures for one municipality or district; None outside TRREB's areas."""
    rows = trreb[trreb["area"] == area]
    if rows.empty:
        return None
    row = rows.iloc[0]
    return AreaMarket(
        area=area,
        month=str(row["month"]),
        snlr=float(row["snlr"]),
        balance=market_balance(float(row["snlr"])),
        months_inventory=float(row["months_inventory"]),
        avg_days_on_market=int(row["ldom"]),
        sale_to_list=int(row["sp_lp"]) / 100,
    )


def red_flags(
    asking_cents: int,
    low_cents: int,
    fair_cents: int,
    high_cents: int,
    days_on_market: int | None = None,
    area_days_on_market: int | None = None,
    original_list_cents: int | None = None,
) -> list[str]:
    flags = []
    if days_on_market is not None:
        if area_days_on_market:
            if days_on_market >= 2 * area_days_on_market:
                flags.append(f"On the market {days_on_market} days, twice or more the area "
                             f"average of {area_days_on_market}.")
        elif days_on_market >= STALE_DAYS_WITHOUT_AREA:
            flags.append(f"On the market {days_on_market} days.")
    if original_list_cents is not None and original_list_cents > asking_cents:
        cut = original_list_cents - asking_cents
        flags.append(f"Price cut by ${cut / 100:,.0f} ({cut / original_list_cents:.1%}) "
                     f"from ${original_list_cents / 100:,.0f}.")
    if asking_cents < low_cents - (fair_cents - low_cents):
        flags.append("Asking is far below the fair range: check condition, fees and the listing details.")
    elif asking_cents > high_cents + (high_cents - fair_cents):
        flags.append("Asking is far above the fair range.")
    return flags
