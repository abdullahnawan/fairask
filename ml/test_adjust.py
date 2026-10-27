"""Tests for HPI time adjustment.

These build their own three-month HPI table instead of reading the real one, so
they pin the arithmetic rather than today's benchmark prices, and they run on a
machine that has never downloaded the CREA workbook.
"""

from __future__ import annotations

import pandas as pd
import pytest

from adjust import HPI_REGION, HPI_TYPE, benchmarks, time_adjust
from brampton import PROPERTY_TYPES as BRAMPTON_TYPES
from toronto import PROPERTY_TYPES as TORONTO_TYPES


@pytest.fixture
def hpi() -> pd.DataFrame:
    """Greater Toronto, three months, two series. Apartments fall; houses rise."""
    months = pd.to_datetime(["2021-01-01", "2021-02-01", "2021-03-01"])
    rows = [
        ("Single_Family", months, [1_000_000, 1_100_000, 1_200_000]),
        ("Apartment", months, [600_000, 550_000, 500_000]),
        ("Townhouse", months, [800_000, 800_000, 800_000]),
    ]
    return pd.concat(
        pd.DataFrame(
            {
                "region": "Greater Toronto",
                "property_type": ptype,
                "month": month,
                "hpi_index": 100.0,
                "benchmark_price": price,
            }
        )
        for ptype, month, price in rows
    ).reset_index(drop=True)


def sale(property_type: str, sold_date: str, price: int) -> pd.DataFrame:
    return pd.DataFrame(
        {"sold_date": [pd.Timestamp(sold_date)], "sold_price": [price],
         "property_type": [property_type]}
    )


class TestTimeAdjust:
    def test_scales_by_the_benchmark_ratio(self, hpi: pd.DataFrame) -> None:
        """A detached sale in January is quoted in March dollars: 1.2x."""
        out = time_adjust(sale("detached", "2021-01-15", 500_000), hpi, "Brampton")
        assert out["hpi_factor"].iloc[0] == pytest.approx(1.2)
        assert out["price_today"].iloc[0] == 600_000

    def test_a_falling_market_adjusts_downwards(self, hpi: pd.DataFrame) -> None:
        """Condo benchmarks really did fall after 2021, so the factor must be
        allowed below 1. A model trained on upward-only adjustment would price
        every old condo sale too high."""
        out = time_adjust(sale("condo_apartment", "2021-01-31", 600_000), hpi, "Brampton")
        assert out["hpi_factor"].iloc[0] == pytest.approx(500_000 / 600_000)
        assert out["price_today"].iloc[0] == 500_000

    def test_a_sale_in_the_target_month_is_left_alone(self, hpi: pd.DataFrame) -> None:
        out = time_adjust(sale("townhouse", "2021-03-20", 777_000), hpi, "Brampton")
        assert out["hpi_factor"].iloc[0] == 1.0
        assert out["price_today"].iloc[0] == 777_000

    def test_any_day_in_a_month_uses_that_months_benchmark(self, hpi: pd.DataFrame) -> None:
        first = time_adjust(sale("detached", "2021-02-01", 500_000), hpi, "Brampton")
        last = time_adjust(sale("detached", "2021-02-28", 500_000), hpi, "Brampton")
        assert first["sold_month"].iloc[0] == last["sold_month"].iloc[0] == pd.Timestamp(
            "2021-02-01"
        )

    def test_semis_are_adjusted_with_the_detached_series(self, hpi: pd.DataFrame) -> None:
        """CREA publishes no semi-detached benchmark. This is the approximation
        that fills the gap, and it should be visible in a test, not buried."""
        semi = time_adjust(sale("semi_detached", "2021-01-10", 500_000), hpi, "Brampton")
        detached = time_adjust(sale("detached", "2021-01-10", 500_000), hpi, "Brampton")
        assert semi["hpi_factor"].iloc[0] == detached["hpi_factor"].iloc[0]

    def test_original_columns_survive(self, hpi: pd.DataFrame) -> None:
        out = time_adjust(sale("detached", "2021-01-15", 500_000), hpi, "Brampton")
        assert out["sold_price"].iloc[0] == 500_000
        assert list(out.columns[:3]) == ["sold_date", "sold_price", "property_type"]

    def test_explicit_target_month(self, hpi: pd.DataFrame) -> None:
        out = time_adjust(
            sale("detached", "2021-01-15", 500_000), hpi, "Brampton",
            target_month=pd.Timestamp("2021-02-01"),
        )
        assert out["hpi_factor"].iloc[0] == pytest.approx(1.1)

    def test_a_month_the_hpi_does_not_cover_raises(self, hpi: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="does not cover"):
            time_adjust(sale("detached", "2019-06-01", 500_000), hpi, "Brampton")

    def test_an_unmappable_property_type_raises(self, hpi: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="no HPI series"):
            time_adjust(sale("duplex", "2021-01-15", 500_000), hpi, "Brampton")


class TestMappings:
    def test_every_cleaned_property_type_has_an_hpi_series(self) -> None:
        assert set(TORONTO_TYPES) | set(BRAMPTON_TYPES) <= set(HPI_TYPE)

    def test_brampton_and_toronto_share_the_greater_toronto_benchmark(self) -> None:
        assert HPI_REGION["Brampton"] == HPI_REGION["Toronto"] == "Greater Toronto"

    def test_unknown_region_raises(self, hpi: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="no HPI rows"):
            benchmarks(hpi, "Cambridge")
