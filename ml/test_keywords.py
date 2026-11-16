"""Tests for the description keyword features.

The parsers are pure and always run. The coverage test needs the cleaned
Toronto table, so it skips rather than passes when that is absent.
"""

from __future__ import annotations

import pandas as pd
import pytest

from keywords import (
    FLAGS,
    TORONTO_CLEAN,
    flags,
    keyword_features,
    stated_year_built,
)


class TestFlags:
    def test_every_flag_is_present_and_false_for_an_empty_description(self) -> None:
        result = flags("")
        assert set(result) == set(FLAGS)
        assert not any(result.values())

    @pytest.mark.parametrize(
        "text, flag",
        [
            ("Finished Bsmt With Rec Room", "basement_finished"),
            ("Basement Is Finished", "basement_finished"),
            ("Fin Lower Level", "basement_finished"),
            ("Separate Entrance To In-Law Suite", "basement_apartment"),
            ("Bsmt Apt With Own Kitchen", "basement_apartment"),
            ("Sep. Entry", "basement_apartment"),
            ("Walk-Out Basement To Deck", "basement_walkout"),
            ("Walkout To Yard", "basement_walkout"),
            ("Double Car Garage", "garage"),
            ("Attached Gar W/ Opener", "garage"),
            ("Renovated Top To Bottom", "renovated"),
            ("Updated Windows", "renovated"),
            ("Brand New Never Lived In", "new_build"),
            ("New Build By Award Winning Builder", "new_build"),
            ("Inground Pool", "pool"),
            ("Backing Onto Ravine", "ravine"),
        ],
    )
    def test_phrase_sets_its_flag(self, text: str, flag: str) -> None:
        assert flags(text)[flag] is True

    def test_renovators_dream_is_not_renovated(self) -> None:
        """A renovator's dream is an unrenovated house that needs work."""
        assert flags("Renovator's Dream On A Quiet Street")["renovated"] is False

    def test_matching_is_case_insensitive(self) -> None:
        assert flags("GARAGE")["garage"] and flags("garage")["garage"]

    def test_word_boundaries_hold(self) -> None:
        """'garden' must not light the garage flag through 'gar'."""
        assert flags("Lovely Garden")["garage"] is False
        assert flags("Carpool Lane")["pool"] is False


class TestStatedYearBuilt:
    def test_built_in(self) -> None:
        assert stated_year_built("Detached Brick 2-Storey Built In 1991") == 1991

    def test_built_without_in(self) -> None:
        assert stated_year_built("Custom Home Built 2016") == 2016

    def test_circa(self) -> None:
        assert stated_year_built("Gorgeous 3 Storey Home, Circa 1913") == 1913

    def test_constructed(self) -> None:
        assert stated_year_built("Constructed In 2005") == 2005

    def test_a_year_alone_is_not_a_build_year(self) -> None:
        """'Roof 2015' or 'Taxes 2019' say nothing about when it was built."""
        assert stated_year_built("New Roof 2015, Taxes 2019") is None

    def test_absent(self) -> None:
        assert stated_year_built("Bright And Spacious") is None


def test_keyword_features_shape() -> None:
    sales = pd.DataFrame(
        {"mls": ["A", "B"], "description": ["Finished Bsmt, Built In 1991", None]}
    )
    out = keyword_features(sales)
    assert list(out["mls"]) == ["A", "B"]
    assert out.loc[0, "basement_finished"] and not out.loc[1, "basement_finished"]
    assert out.loc[0, "year_built_stated"] == 1991
    assert pd.isna(out.loc[1, "year_built_stated"])


@pytest.mark.skipif(not TORONTO_CLEAN.exists(), reason="run python ml/toronto.py first")
def test_coverage_on_the_real_data_is_in_a_sane_band() -> None:
    """Pins the band seen on the first run, so a regex edit that silently
    matches everything or nothing is caught."""
    out = keyword_features(pd.read_csv(TORONTO_CLEAN))
    assert len(out) == 14_892
    share = out[list(FLAGS)].mean()
    assert 0.05 < share["basement_finished"] < 0.20
    assert 0.25 < share["renovated"] < 0.50
    assert share["ravine"] < 0.05
    assert 50 < out["year_built_stated"].notna().sum() < 200
