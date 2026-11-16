"""Tests for the model table.

The coalescing rule and the target are pure and always run. The build against
the real processed tables skips when they are absent.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from adjust import TORONTO_ASSUMED_MONTH
from dataset import FEATURES, INPUTS, NEVER_FEATURES, build, coalesce_year_built


class TestCoalesceYearBuilt:
    def frame(self, permit=None, stated=None) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "year_built_permit": pd.array([permit], dtype="Int64"),
                "year_built_stated": pd.array([stated], dtype="Int64"),
            }
        )

    def test_a_permit_before_the_sale_wins(self) -> None:
        assert coalesce_year_built(self.frame(permit=2005, stated=1990)).iloc[0] == 2005

    def test_a_permit_after_the_sale_is_ignored(self) -> None:
        """A 2022 rebuild says nothing about the house sold in 2019."""
        out = coalesce_year_built(self.frame(permit=2022, stated=1990))
        assert out.iloc[0] == 1990

    def test_nothing_known_stays_empty(self) -> None:
        assert pd.isna(coalesce_year_built(self.frame()).iloc[0])


def test_no_feature_is_on_the_forbidden_list() -> None:
    """list_price and the answer itself can never reach the model."""
    assert not set(FEATURES) & NEVER_FEATURES
    assert "list_price" in NEVER_FEATURES


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    return build()


@pytest.mark.skipif(
    not all(path.exists() for path in INPUTS.values()),
    reason="processed tables not present; run the ml/ scripts first",
)
class TestBuildOnTheRealTables:
    def test_one_row_per_sale_from_both_sources(self, table: pd.DataFrame) -> None:
        """Brampton MLS numbers legitimately repeat for different addresses (a
        misread in the PDF extraction, see ml/brampton.py), so uniqueness is
        only asserted where the source guarantees it."""
        assert table["source"].value_counts().to_dict() == {"toronto": 14_892, "brampton": 1_138}
        toronto = table.loc[table["source"] == "toronto", "mls"]
        assert not toronto.duplicated().any()

    def test_target_is_the_log_ratio_to_the_benchmark(self, table: pd.DataFrame) -> None:
        expected = np.log(table["sold_price"] / table["benchmark_then"])
        assert np.allclose(table["target"], expected)
        assert table["target"].notna().all()
        # A house exactly at its benchmark scores zero; most sit within +/-70%.
        assert table["target"].abs().median() < 0.7

    def test_brampton_has_no_toronto_only_features(self, table: pd.DataFrame) -> None:
        brampton = table[table["source"] == "brampton"]
        assert brampton[["sqft_mid", "lat", "lot_area_m2", "year_built"]].isna().all().all()
        assert brampton["beds_above"].notna().all()

    def test_year_built_never_postdates_the_assumed_sale(self, table: pd.DataFrame) -> None:
        assert table["year_built"].dropna().le(TORONTO_ASSUMED_MONTH.year).all()
