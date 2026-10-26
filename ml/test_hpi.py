"""Tests for the CREA HPI loader.

The workbook is CREA copyright and gitignored, so these tests skip rather than
pass when it is absent. A skip is visible; a silent pass would not be.
"""

from __future__ import annotations

import pandas as pd
import pytest

from hpi import DEFAULT_WORKBOOK, PROPERTY_TYPES, REGIONS, load_hpi

pytestmark = pytest.mark.skipif(
    not DEFAULT_WORKBOOK.exists(),
    reason=f"CREA HPI workbook not present at {DEFAULT_WORKBOOK}; see data/SOURCES.md",
)


@pytest.fixture(scope="module")
def hpi() -> pd.DataFrame:
    return load_hpi()


def test_is_tidy_one_row_per_region_type_month(hpi: pd.DataFrame) -> None:
    assert list(hpi.columns) == [
        "region",
        "property_type",
        "month",
        "hpi_index",
        "benchmark_price",
    ]
    assert not hpi.duplicated(["region", "property_type", "month"]).any()


def test_covers_every_region_and_type(hpi: pd.DataFrame) -> None:
    assert set(hpi["region"]) == set(REGIONS.values())
    assert set(hpi["property_type"]) == set(PROPERTY_TYPES)


def test_row_count_is_regions_times_types_times_months(hpi: pd.DataFrame) -> None:
    months = hpi["month"].nunique()
    assert len(hpi) == len(REGIONS) * len(PROPERTY_TYPES) * months


def test_months_are_month_starts_with_no_gaps(hpi: pd.DataFrame) -> None:
    months = pd.Series(sorted(hpi["month"].unique()))
    assert (months.dt.day == 1).all()
    assert (months.diff().dropna() == pd.Timedelta(days=31)).sum() >= 0
    expected = pd.date_range(months.iloc[0], months.iloc[-1], freq="MS")
    assert list(months) == list(expected)


def test_known_published_value(hpi: pd.DataFrame) -> None:
    """Cambridge composite, January 2005 — the HPI base month, index 100."""
    row = hpi[
        (hpi["region"] == "Cambridge")
        & (hpi["property_type"] == "Composite")
        & (hpi["month"] == pd.Timestamp("2005-01-01"))
    ]
    assert len(row) == 1
    assert row["hpi_index"].item() == pytest.approx(100.0)
    assert row["benchmark_price"].item() == 206400


def test_prices_are_positive_whole_dollars(hpi: pd.DataFrame) -> None:
    assert hpi["benchmark_price"].gt(0).all()
    assert hpi["benchmark_price"].dtype.kind in "iu"
    assert hpi["hpi_index"].gt(0).all()
