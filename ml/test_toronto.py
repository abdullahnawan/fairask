"""Tests for the Toronto sold dataset cleaner.

The parsers are pure and always tested. The loader tests need the downloaded
CSV, so they skip rather than pass when it is absent.
"""

from __future__ import annotations

import pandas as pd
import pytest

from toronto import (
    DEFAULT_CSV,
    PROPERTY_TYPES,
    load_toronto,
    parse_beds,
    parse_parking,
    parse_sqft_range,
)

EN_DASH = "\u2013"


class TestParseBeds:
    """'2 + 1 beds' means 2 bedrooms above grade and 1 below."""

    def test_plain_count_has_nothing_below_grade(self) -> None:
        assert parse_beds("3 beds") == (3, 0)

    def test_split_count(self) -> None:
        assert parse_beds("2 + 1 beds") == (2, 1)

    def test_zero_above_grade_is_kept_not_treated_as_missing(self) -> None:
        assert parse_beds("0 beds") == (0, 0)
        assert parse_beds("0 + 1 beds") == (0, 1)

    def test_largest_value_in_the_data(self) -> None:
        assert parse_beds("9 + 5 beds") == (9, 5)

    def test_singular_bed_is_accepted(self) -> None:
        assert parse_beds("1 bed") == (1, 0)

    def test_unparseable_raises_rather_than_guessing(self) -> None:
        with pytest.raises(ValueError):
            parse_beds("a few bedrooms")


class TestParseSqftRange:
    def test_en_dash_separator(self) -> None:
        assert parse_sqft_range(f"800{EN_DASH}899 sq. ft.") == (800, 899)

    def test_ascii_hyphen_separator(self) -> None:
        """Only the '0-499' bucket uses a plain hyphen."""
        assert parse_sqft_range("0-499 sq. ft.") == (0, 499)

    def test_not_available_is_missing_not_zero(self) -> None:
        assert parse_sqft_range("N/A sq. ft.") == (None, None)

    def test_wide_bucket(self) -> None:
        assert parse_sqft_range(f"3500{EN_DASH}5000 sq. ft.") == (3500, 5000)

    def test_unparseable_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_sqft_range("big sq. ft.")


class TestParseParking:
    def test_count(self) -> None:
        assert parse_parking("2 parking") == 2

    def test_none_is_zero_not_missing(self) -> None:
        assert parse_parking("no parking") == 0

    def test_unparseable_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_parking("maybe parking")


pytestmark_loader = pytest.mark.skipif(
    not DEFAULT_CSV.exists(),
    reason=f"Toronto CSV not present at {DEFAULT_CSV}; run python data/download.py toronto",
)


@pytest.fixture(scope="module")
def clean() -> pd.DataFrame:
    return load_toronto()


@pytestmark_loader
class TestLoadToronto:
    def test_scraped_html_row_is_dropped(self, clean: pd.DataFrame) -> None:
        assert not clean["property_type"].str.contains("<", regex=False).any()
        assert not clean["description"].astype(str).str.contains("<!DOCTYPE", case=False).any()

    def test_only_in_scope_property_types_survive(self, clean: pd.DataFrame) -> None:
        assert set(clean["property_type"]) <= set(PROPERTY_TYPES)

    def test_bed_counts_are_consistent(self, clean: pd.DataFrame) -> None:
        assert (clean["beds_total"] == clean["beds_above"] + clean["beds_below"]).all()
        assert clean["beds_above"].ge(0).all()
        assert clean["beds_below"].ge(0).all()

    def test_sqft_midpoint_sits_inside_its_range(self, clean: pd.DataFrame) -> None:
        known = clean.dropna(subset=["sqft_min", "sqft_max", "sqft_mid"])
        assert known["sqft_min"].le(known["sqft_mid"]).all()
        assert known["sqft_mid"].le(known["sqft_max"]).all()

    def test_missing_sqft_is_null_across_all_three_columns(self, clean: pd.DataFrame) -> None:
        """A missing range must not become a zero that the model would trust."""
        missing = clean["sqft_mid"].isna()
        assert clean.loc[missing, ["sqft_min", "sqft_max"]].isna().all().all()
        assert missing.any(), "the raw data has N/A sq ft rows, so some must survive as null"

    def test_required_fields_are_never_null(self, clean: pd.DataFrame) -> None:
        required = [
            "mls",
            "sold_price",
            "list_price",
            "property_type",
            "beds_above",
            "beds_below",
            "baths",
            "parking",
            "lat",
            "long",
        ]
        assert clean[required].notna().all().all()

    def test_one_row_per_listing(self, clean: pd.DataFrame) -> None:
        assert not clean["mls"].duplicated().any()

    def test_prices_are_positive_whole_dollars(self, clean: pd.DataFrame) -> None:
        assert clean["sold_price"].gt(0).all()
        assert clean["list_price"].gt(0).all()
        assert clean["sold_price"].dtype.kind in "iu"
