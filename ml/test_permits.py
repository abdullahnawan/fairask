"""Tests for year built from building permits.

The address parser and the join are pure and always run. The test against the
real permit files skips when they have not been downloaded.
"""

from __future__ import annotations

import pandas as pd
import pytest

from permits import PERMIT_FILES, TORONTO_CLEAN, address_key, load_permits, year_built


class TestAddressKey:
    def test_plain_street(self) -> None:
        assert address_key("38 Grenville St, Toronto , Ontario, Canada") == (
            "38", "GRENVILLE", "ST", "",
        )

    def test_long_type_is_folded_to_the_permit_abbreviation(self) -> None:
        assert address_key("2 Cabot Court") == ("2", "CABOT", "CRT", "")
        assert address_key("2 Cabot Crt") == ("2", "CABOT", "CRT", "")

    def test_direction_is_kept_so_east_and_west_stay_apart(self) -> None:
        assert address_key("1 Queen St E") == ("1", "QUEEN", "ST", "E")
        assert address_key("1 Queen St West") == ("1", "QUEEN", "ST", "W")
        assert address_key("1 Queen St E") != address_key("1 Queen St W")

    def test_a_direction_word_inside_the_name_is_not_a_direction(self) -> None:
        assert address_key("65 East Liberty St") == ("65", "EAST LIBERTY", "ST", "")

    def test_a_street_named_after_a_type_word(self) -> None:
        """Toronto has an Avenue Road; AVENUE is the name, RD is the type."""
        assert address_key("12 Avenue Rd") == ("12", "AVENUE", "RD", "")

    def test_unit_letter_in_the_number_is_kept(self) -> None:
        assert address_key("12A Elm St") == ("12A", "ELM", "ST", "")

    def test_no_number_means_no_key(self) -> None:
        assert address_key("First St, Toronto") is None
        assert address_key("380/382 Jane St") is None
        assert address_key("") is None


class TestYearBuilt:
    @pytest.fixture
    def permits(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "key": ["10|ELM|ST|", "10|ELM|ST|", "20|OAK|AVE|E"],
                "year": [2005, 2021, 2010],
                "STRUCTURE_TYPE": ["SFD - DETACHED"] * 3,
            }
        )

    def test_earliest_permit_wins_and_the_count_shows_the_rebuild(
        self, permits: pd.DataFrame
    ) -> None:
        sales = pd.DataFrame({"mls": ["A"], "address": ["10 Elm Street"]})
        out = year_built(sales, permits)
        assert out.loc[0, "year_built_permit"] == 2005
        assert out.loc[0, "new_building_permits"] == 2

    def test_no_permit_leaves_the_year_empty_not_zero(self, permits: pd.DataFrame) -> None:
        sales = pd.DataFrame({"mls": ["B", "C"], "address": ["99 Birch Rd", "First St"]})
        out = year_built(sales, permits)
        assert out["year_built_permit"].isna().all()
        assert (out["new_building_permits"] == 0).all()

    def test_direction_must_match(self, permits: pd.DataFrame) -> None:
        sales = pd.DataFrame({"mls": ["D", "E"], "address": ["20 Oak Ave E", "20 Oak Ave W"]})
        out = year_built(sales, permits)
        assert out.loc[0, "year_built_permit"] == 2010
        assert pd.isna(out.loc[1, "year_built_permit"])


@pytest.mark.skipif(
    not (all(p.exists() for p in PERMIT_FILES) and TORONTO_CLEAN.exists()),
    reason="permit files or cleaned Toronto table not present; see data/SOURCES.md",
)
class TestAgainstTheRealFiles:
    def test_match_rate_and_years_are_in_the_observed_band(self) -> None:
        """Pins the 2026-11 run: 2,302 of 14,892 sales matched, no key ambiguous.
        A parser change that merges or splits streets moves this well outside."""
        sales = pd.read_csv(TORONTO_CLEAN)
        permits = load_permits()
        assert "SFD GARAGES" not in set(permits["STRUCTURE_TYPE"])
        out = year_built(sales, permits)
        matched = out["year_built_permit"].notna().sum()
        assert 2_100 < matched < 2_600
        assert out["year_built_permit"].dropna().between(1990, 2026).all()
