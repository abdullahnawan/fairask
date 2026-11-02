"""Tests for the Brampton sold dataset cleaner.

This file is a PDF extraction and is considerably dirtier than the Toronto one,
so most of these tests pin down a specific defect found in the raw data.
"""

from __future__ import annotations

import pandas as pd
import pytest

from brampton import (
    DEFAULT_CSV,
    PROPERTY_TYPES,
    SOLD_WINDOW,
    is_well_formed_price,
    load_brampton,
    parse_price,
)


class TestParsePrice:
    def test_normal_price(self) -> None:
        assert parse_price("$599,000") == 599000

    def test_misplaced_commas_still_give_the_right_number(self) -> None:
        """The extraction emitted '$4,49,000' for $449,000. Stripping every
        separator recovers the same digits, which its well-formed twin confirms."""
        assert parse_price("$4,49,000") == 449000
        assert parse_price("  $7,39,900  ") == 739900

    def test_surrounding_whitespace(self) -> None:
        assert parse_price("   $450,000 ") == 450000

    def test_no_digits_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_price("$")


class TestIsWellFormedPrice:
    def test_canadian_grouping_is_well_formed(self) -> None:
        assert is_well_formed_price("$449,000")
        assert is_well_formed_price("$1,099,999")
        assert is_well_formed_price("  $799,000  ")

    def test_misgrouped_commas_are_not(self) -> None:
        assert not is_well_formed_price("$4,49,000")
        assert not is_well_formed_price("$7,39,900")


pytestmark_loader = pytest.mark.skipif(
    not DEFAULT_CSV.exists(),
    reason=f"Brampton CSV not present at {DEFAULT_CSV}; run python data/download.py brampton",
)


@pytest.fixture(scope="module")
def clean() -> pd.DataFrame:
    return load_brampton()


@pytestmark_loader
class TestLoadBrampton:
    def test_only_in_scope_property_types_survive(self, clean: pd.DataFrame) -> None:
        assert set(clean["property_type"]) <= set(PROPERTY_TYPES)

    def test_no_duplicate_extraction_of_the_same_listing(self, clean: pd.DataFrame) -> None:
        """An MLS number may legitimately repeat only when the rows are
        different addresses — that is a bad MLS read, not a duplicate row."""
        shared = clean[clean["mls"].duplicated(keep=False)]
        for _, group in shared.groupby("mls"):
            addresses = group["street_number"].astype(str) + " " + group["street_name"]
            assert addresses.nunique() == len(group), f"duplicate rows for {group['mls'].iloc[0]}"

    def test_bed_counts_are_consistent(self, clean: pd.DataFrame) -> None:
        assert (clean["beds_total"] == clean["beds_above"] + clean["beds_below"]).all()

    def test_prices_are_positive_whole_dollars(self, clean: pd.DataFrame) -> None:
        assert clean["sold_price"].gt(0).all()
        assert clean["sold_price"].dtype.kind in "iu"
        assert clean["list_price"].dtype.kind in "iu"

    def test_digit_dropping_price_errors_are_removed(self, clean: pd.DataFrame) -> None:
        """Two raw rows sold at a tenth of list; those are extraction errors."""
        ratio = clean["sold_price"] / clean["list_price"]
        assert ratio.between(0.5, 2.0).all()

    def test_sold_dates_fall_inside_the_documented_window(self, clean: pd.DataFrame) -> None:
        start, end = SOLD_WINDOW
        assert clean["sold_date"].between(pd.Timestamp(start), pd.Timestamp(end)).all()

    def test_a_home_cannot_sell_before_it_was_listed(self, clean: pd.DataFrame) -> None:
        assert (clean["sold_date"] >= clean["contract_date"]).all()
        assert clean["days_on_market"].ge(0).all()

    def test_required_fields_are_never_null(self, clean: pd.DataFrame) -> None:
        required = [
            "mls",
            "sold_price",
            "list_price",
            "property_type",
            "beds_above",
            "beds_below",
            "baths",
            "sold_date",
            "contract_date",
        ]
        assert clean[required].notna().all().all()

    def test_square_footage_and_coordinates_are_absent_not_invented(
        self, clean: pd.DataFrame
    ) -> None:
        """This source has neither. They must not appear as zeros."""
        assert "sqft_mid" not in clean.columns
        assert "lat" not in clean.columns
