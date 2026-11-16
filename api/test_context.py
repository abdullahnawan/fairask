"""Tests for market context and red flags, on small hand-made tables."""

from __future__ import annotations

import pandas as pd
import pytest

from context import area_market, hpi_context, market_balance, red_flags


def hpi_table() -> pd.DataFrame:
    """Benchmark 100 in 2020-01, peaks at 150 in 2022-03, ends at 120 in 2025-01."""
    months = pd.date_range("2020-01-01", "2025-01-01", freq="MS")
    prices = [100_000 + 1_000 * i for i in range(27)]           # up to 126k by 2022-03
    prices[26] = 150_000                                          # the peak, 2022-03
    prices += [130_000] * (len(months) - 27 - 13) + [110_000] * 12 + [120_000]
    rows = pd.DataFrame({"month": months, "benchmark_price": prices})
    other = rows.assign(benchmark_price=1)                        # a different series
    return pd.concat([
        rows.assign(region="Kitchener-Waterloo", property_type="Single_Family"),
        other.assign(region="Kitchener-Waterloo", property_type="Apartment"),
    ])


class TestHpiContext:
    def test_changes_and_distance_from_peak(self) -> None:
        ctx = hpi_context(hpi_table(), "Kitchener-Waterloo", "Single_Family")
        assert ctx.month == "2025-01"
        assert ctx.benchmark_cents == 120_000_00
        assert ctx.change_1y == pytest.approx(120 / 110 - 1)
        assert ctx.change_5y == pytest.approx(120 / 100 - 1)
        assert ctx.peak_month == "2022-03"
        assert ctx.from_peak == pytest.approx(120 / 150 - 1)

    def test_short_history_leaves_5y_empty(self) -> None:
        table = hpi_table()
        recent = table[table["month"] >= "2022-01-01"]
        assert hpi_context(recent, "Kitchener-Waterloo", "Single_Family").change_5y is None

    def test_unknown_series_is_refused(self) -> None:
        with pytest.raises(KeyError):
            hpi_context(hpi_table(), "Ottawa", "Single_Family")


@pytest.mark.parametrize(
    ("snlr", "label"), [(35.9, "Buyer's market"), (40.0, "Balanced market"), (60.0, "Balanced market"), (60.1, "Seller's market")]
)
def test_market_balance_follows_crea_snlr_bands(snlr: float, label: str) -> None:
    assert market_balance(snlr) == label


def test_area_market_finds_a_district_and_misses_politely() -> None:
    trreb = pd.DataFrame(
        {"area": ["Brampton", "Toronto E01"], "month": ["2026-10"] * 2, "snlr": [35.9, 47.9],
         "months_inventory": [4.6, 2.4], "sp_lp": [98, 106], "ldom": [30, 13]}
    )
    e01 = area_market(trreb, "Toronto E01")
    assert (e01.balance, e01.avg_days_on_market, e01.sale_to_list) == ("Balanced market", 13, 1.06)
    assert area_market(trreb, "Kitchener") is None


class TestRedFlags:
    RANGE = dict(low_cents=900_000_00, fair_cents=1_000_000_00, high_cents=1_100_000_00)

    def test_a_clean_listing_has_no_flags(self) -> None:
        assert red_flags(1_000_000_00, **self.RANGE, days_on_market=10, area_days_on_market=20) == []

    def test_long_on_market_against_the_area(self) -> None:
        flags = red_flags(1_000_000_00, **self.RANGE, days_on_market=40, area_days_on_market=20)
        assert flags == ["On the market 40 days, twice or more the area average of 20."]

    def test_long_on_market_without_area_data_uses_60_days(self) -> None:
        assert red_flags(1_000_000_00, **self.RANGE, days_on_market=59) == []
        assert len(red_flags(1_000_000_00, **self.RANGE, days_on_market=60)) == 1

    def test_price_drop_states_the_amount(self) -> None:
        flags = red_flags(1_000_000_00, **self.RANGE, original_list_cents=1_080_000_00)
        assert flags == ["Price cut by $80,000 (7.4%) from $1,080,000."]

    def test_far_below_the_range(self) -> None:
        # More than one range-half (100k) below the low end.
        flags = red_flags(799_999_00, **self.RANGE)
        assert flags == ["Asking is far below the fair range: check condition, fees and the listing details."]
        assert red_flags(800_000_00, **self.RANGE) == []

    def test_far_above_the_range(self) -> None:
        assert red_flags(1_200_000_01, **self.RANGE) == ["Asking is far above the fair range."]
