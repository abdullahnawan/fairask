"""Tests for the CREA HPI loader.

The real workbook is CREA copyright and gitignored, so the tests that read it
skip rather than pass when it is absent. A skip is visible; a silent pass would
not be. The validation guards are tested against a workbook built in a temp
directory instead, so they stay covered on a machine that has never downloaded
the real one.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hpi import CREA_PROPERTY_TYPES, DEFAULT_WORKBOOK, REGIONS, load_hpi

needs_workbook = pytest.mark.skipif(
    not DEFAULT_WORKBOOK.exists(),
    reason=f"CREA HPI workbook not present at {DEFAULT_WORKBOOK}; see data/SOURCES.md",
)

ONE_SHEET = {"CAMBRIDGE": "Cambridge"}


def write_workbook(
    tmp_path: Path, *, drop: str | None = None, blank: str | None = None
) -> Path:
    """A minimal three-month workbook in the shape ml/hpi.py expects."""
    frame = pd.DataFrame({"Date": pd.date_range("2005-01-01", periods=3, freq="MS")})
    for ptype in CREA_PROPERTY_TYPES:
        frame[f"{ptype}_HPI"] = [100.0, 101.0, 102.0]
        frame[f"{ptype}_Benchmark"] = [200_000, 202_000, 204_000]
    if drop:
        frame = frame.drop(columns=[drop])
    if blank:
        frame.loc[1, blank] = None

    path = tmp_path / "hpi.xlsx"
    with pd.ExcelWriter(path) as writer:
        frame.to_excel(writer, sheet_name="CAMBRIDGE", index=False)
    return path


class TestValidation:
    def test_a_complete_sheet_loads(self, tmp_path: Path) -> None:
        tidy = load_hpi(write_workbook(tmp_path), regions=ONE_SHEET)
        assert len(tidy) == len(CREA_PROPERTY_TYPES) * 3

    def test_a_missing_workbook_says_where_to_get_it(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="SOURCES.md"):
            load_hpi(tmp_path / "absent.xlsx")

    def test_a_missing_column_names_the_sheet(self, tmp_path: Path) -> None:
        workbook = write_workbook(tmp_path, drop="Apartment_Benchmark")
        with pytest.raises(ValueError, match="missing columns"):
            load_hpi(workbook, regions=ONE_SHEET)

    def test_a_month_with_no_value_names_the_sheet(self, tmp_path: Path) -> None:
        """CREA does not publish every type for every small market back to 2005.
        A later-starting series arrives as blanks; without this guard it reached
        .astype("int64") and raised a pandas error naming no sheet."""
        workbook = write_workbook(tmp_path, blank="Apartment_Benchmark")
        with pytest.raises(ValueError, match="no value in"):
            load_hpi(workbook, regions=ONE_SHEET)


@pytest.fixture(scope="module")
def hpi() -> pd.DataFrame:
    return load_hpi()


@needs_workbook
class TestAgainstTheRealWorkbook:
    def test_is_tidy_one_row_per_region_type_month(self, hpi: pd.DataFrame) -> None:
        assert list(hpi.columns) == [
            "region",
            "property_type",
            "month",
            "hpi_index",
            "benchmark_price",
        ]
        assert not hpi.duplicated(["region", "property_type", "month"]).any()

    def test_covers_every_region_and_type(self, hpi: pd.DataFrame) -> None:
        assert set(hpi["region"]) == set(REGIONS.values())
        assert set(hpi["property_type"]) == set(CREA_PROPERTY_TYPES)

    def test_row_count_is_regions_times_types_times_months(self, hpi: pd.DataFrame) -> None:
        months = hpi["month"].nunique()
        assert len(hpi) == len(REGIONS) * len(CREA_PROPERTY_TYPES) * months

    def test_months_are_month_starts_with_no_gaps(self, hpi: pd.DataFrame) -> None:
        months = pd.Series(sorted(hpi["month"].unique()))
        assert (months.dt.day == 1).all()
        expected = pd.date_range(months.iloc[0], months.iloc[-1], freq="MS")
        assert list(months) == list(expected)

    def test_known_published_value(self, hpi: pd.DataFrame) -> None:
        """Cambridge composite, January 2005 — the HPI base month, index 100."""
        row = hpi[
            (hpi["region"] == "Cambridge")
            & (hpi["property_type"] == "Composite")
            & (hpi["month"] == pd.Timestamp("2005-01-01"))
        ]
        assert len(row) == 1
        assert row["hpi_index"].item() == pytest.approx(100.0)
        assert row["benchmark_price"].item() == 206400

    def test_prices_are_positive_whole_dollars(self, hpi: pd.DataFrame) -> None:
        assert hpi["benchmark_price"].gt(0).all()
        assert hpi["benchmark_price"].dtype.kind in "iu"
        assert hpi["hpi_index"].gt(0).all()
