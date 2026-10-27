"""Tests for the Toronto parcel join.

The geometry tests run anywhere. The rest need the 57 MB parcel download and the
cleaned sales, so they skip rather than pass when those are absent — a skip is
visible, a silent pass would not be.

The test that matters most is `test_areas_match_the_lot_sizes_quoted_in_listings`.
A geometry pipeline can be self-consistent and still wrong: the wrong projection,
a missing area correction or an off-by-one in the ring offsets all produce
plausible-looking numbers. Comparing against lot dimensions the listing agents
typed into their own descriptions is the one check that comes from outside the
pipeline.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from parcels import (
    DEFAULT_ZIP,
    TORONTO_CLEAN,
    Parcels,
    join_lots,
    point_in_rings,
    ring_area,
    to_latitude,
    to_web_mercator,
)

SQUARE = (0.0, 0.0, 10.0, 0.0, 10.0, 10.0, 0.0, 10.0)


class TestGeometry:
    def test_ring_area_of_a_square(self) -> None:
        assert ring_area(SQUARE) == 100.0

    def test_winding_direction_flips_the_sign(self) -> None:
        """Holes rely on this: a reversed ring subtracts from the one around it."""
        reversed_square = (0.0, 10.0, 10.0, 10.0, 10.0, 0.0, 0.0, 0.0)
        assert ring_area(reversed_square) == -100.0

    def test_a_hole_is_subtracted(self) -> None:
        hole = (2.0, 8.0, 8.0, 8.0, 8.0, 2.0, 2.0, 2.0)
        assert abs(ring_area(SQUARE) + ring_area(hole)) == 64.0

    def test_point_inside_and_outside(self) -> None:
        assert point_in_rings([SQUARE], 5.0, 5.0)
        assert not point_in_rings([SQUARE], 15.0, 5.0)
        assert not point_in_rings([SQUARE], 5.0, -1.0)

    def test_a_point_in_a_hole_is_outside(self) -> None:
        hole = (2.0, 8.0, 8.0, 8.0, 8.0, 2.0, 2.0, 2.0)
        assert not point_in_rings([SQUARE, hole], 5.0, 5.0)
        assert point_in_rings([SQUARE, hole], 1.0, 1.0)

    def test_projection_round_trips(self) -> None:
        latitude, longitude = 43.661896, -79.385748  # a sale in the Toronto file
        x, y = to_web_mercator(latitude, longitude)
        assert to_latitude(y) == pytest.approx(latitude)
        assert x == pytest.approx(math.radians(longitude) * 6_378_137.0)

    def test_toronto_sits_where_the_parcels_do(self) -> None:
        """A sanity check on the projection: the City's data spans roughly
        x -8.87M to -8.81M and y 5.40M to 5.44M metres."""
        x, y = to_web_mercator(43.7, -79.4)
        assert -8_870_000 < x < -8_800_000
        assert 5_400_000 < y < 5_450_000


pytestmark_data = pytest.mark.skipif(
    not DEFAULT_ZIP.exists() or not TORONTO_CLEAN.exists(),
    reason=(
        f"needs {DEFAULT_ZIP.name} (python data/download.py toronto_parcels) "
        "and data/processed/toronto_clean.csv (python ml/toronto.py)"
    ),
)


@pytest.fixture(scope="module")
def parcels() -> Parcels:
    return Parcels()


@pytest.fixture(scope="module")
def sales() -> pd.DataFrame:
    return pd.read_csv(TORONTO_CLEAN)


@pytest.fixture(scope="module")
def lots(sales: pd.DataFrame, parcels: Parcels) -> pd.DataFrame:
    return join_lots(sales, parcels)


@pytestmark_data
class TestParcelFile:
    def test_every_shape_has_an_attribute_row(self, parcels: Parcels) -> None:
        assert len(parcels) == len(parcels.feature_types) > 400_000

    def test_feature_types_are_the_documented_four(self, parcels: Parcels) -> None:
        assert set(parcels.feature_types) <= {"COMMON", "CONDO", "CORRIDOR", "RESERVE"}


@pytestmark_data
class TestJoin:
    def test_most_sales_land_inside_a_parcel(self, lots: pd.DataFrame) -> None:
        assert lots["parcel_type"].notna().mean() > 0.9

    def test_a_condo_parcel_never_becomes_a_lot(self, lots: pd.DataFrame) -> None:
        """The polygon under a condo tower is the corporation's land, shared by
        every unit in it. Reporting it as one unit's lot would be a 40,000 m2
        back garden."""
        assert lots.loc[lots["parcel_type"] == "CONDO", "lot_area_m2"].isna().all()

    def test_an_unmatched_sale_gets_no_area(self, lots: pd.DataFrame) -> None:
        unmatched = lots["parcel_type"].isna()
        assert lots.loc[unmatched, "parcel_area_m2"].isna().all()

    def test_detached_lots_are_the_right_order_of_magnitude(
        self, sales: pd.DataFrame, lots: pd.DataFrame
    ) -> None:
        """A typical Toronto detached lot is about 30 by 120 feet, 335 m2. If the
        Web Mercator area correction were dropped this median would roughly
        double, so the band is tight enough to catch that."""
        detached = lots.loc[sales["property_type"].to_numpy() == "detached", "lot_area_m2"]
        assert 300 < detached.median() < 700

    def test_semis_sit_on_smaller_lots_than_detached(
        self, sales: pd.DataFrame, lots: pd.DataFrame
    ) -> None:
        by_type = lots.assign(property_type=sales["property_type"].to_numpy()).groupby(
            "property_type"
        )["lot_area_m2"]
        assert by_type.median()["semi_detached"] < by_type.median()["detached"]

    def test_areas_match_the_lot_sizes_quoted_in_listings(
        self, sales: pd.DataFrame, lots: pd.DataFrame
    ) -> None:
        """Some agents typed the lot dimensions into the description, for example
        "an Incredible Extra Wide 55.5 X 111.5 Foot Lot". Those are independent of
        the City's polygons, so they are the ground truth for this whole file."""
        quoted = sales["description"].fillna("").str.extract(
            r"(?i)(\d{2,3}(?:\.\d+)?)\s*x\s*(\d{2,3}(?:\.\d+)?)\s*(?:foot|ft|feet)[- ]?lot"
        )
        stated_m2 = quoted[0].astype(float) * quoted[1].astype(float) * 0.09290304
        comparable = stated_m2.notna() & lots["lot_area_m2"].notna()
        assert comparable.sum() > 100

        ratio = lots.loc[comparable, "lot_area_m2"] / stated_m2[comparable]
        assert ratio.median() == pytest.approx(1.0, abs=0.05)
        assert ratio.between(0.9, 1.1).mean() > 0.8
