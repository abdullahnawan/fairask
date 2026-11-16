"""Tests for the footprint geometry: projection, WKB parsing and area.

The projection is checked against properties that define a two-standard-
parallel Lambert projection, so no reference library is needed.
"""

from __future__ import annotations

import sqlite3
import struct

import numpy as np
import pandas as pd
import pytest

from footprints import (
    GEOPACKAGES,
    TORONTO_AREA_SCALE,
    TORONTO_CLEAN,
    footprint_m2,
    holdout_error,
    polygon_rings,
    scale_factor,
    to_statcan_lambert,
)


def gpkg(wkb: bytes) -> bytes:
    """Wrap WKB in a GeoPackage header with no envelope."""
    return b"GP" + bytes([0, 0b00000001]) + struct.pack("<i", 3347) + wkb


def square_wkb(side: float, multi: bool = False) -> bytes:
    ring = [(0, 0), (side, 0), (side, side), (0, side), (0, 0)]
    poly = struct.pack("<BII", 1, 3, 1) + struct.pack("<I", len(ring))
    poly += b"".join(struct.pack("<dd", x, y) for x, y in ring)
    return struct.pack("<BII", 1, 6, 1) + poly if multi else poly


class TestProjection:
    def test_the_origin_maps_to_the_false_origin(self) -> None:
        x, y = to_statcan_lambert(63.390675, -91.86666666666666)
        assert x == pytest.approx(6_200_000.0, abs=1e-3)
        assert y == pytest.approx(3_000_000.0, abs=1e-3)

    def test_scale_is_exact_on_both_standard_parallels(self) -> None:
        assert scale_factor(49.0) == pytest.approx(1.0, abs=1e-9)
        assert scale_factor(77.0) == pytest.approx(1.0, abs=1e-9)

    def test_toronto_lies_outside_the_parallels_so_area_is_inflated(self) -> None:
        """About 4.9% at 43.7N. Skipping the correction overstates every house."""
        assert 1.04 < TORONTO_AREA_SCALE < 1.06


class TestGeometry:
    def test_polygon_and_multipolygon_parse_to_the_same_ring(self) -> None:
        single = polygon_rings(gpkg(square_wkb(10)))
        assert single == polygon_rings(gpkg(square_wkb(10, multi=True)))

    def test_area_is_corrected_for_the_projection(self) -> None:
        assert footprint_m2(gpkg(square_wkb(10))) == pytest.approx(100 / TORONTO_AREA_SCALE)

    def test_a_point_geometry_is_refused(self) -> None:
        with pytest.raises(ValueError, match="WKB type 1"):
            polygon_rings(gpkg(struct.pack("<BIdd", 1, 1, 0.0, 0.0)))


def test_holdout_error_is_scored_on_unseen_districts() -> None:
    table = pd.DataFrame(
        {
            "property_type": ["detached"] * 40,
            "city_district": [f"D{i % 10}" for i in range(40)],
            "footprint_sqft": [1000.0] * 40,
            "sqft_mid": [1500.0] * 40,
        }
    )
    assert holdout_error(table).loc["detached", "median"] == pytest.approx(0.0)


@pytest.mark.skipif(
    not (all(p.exists() for p in GEOPACKAGES) and TORONTO_CLEAN.exists()),
    reason="StatCan GeoPackages or cleaned Toronto table not present",
)
def test_sale_points_land_on_their_own_building() -> None:
    """Pins the 2026-11-16 check: a sale with the same address as an ODB building
    projects to within metres of it. A wrong projection parameter puts it km off."""
    sales = pd.read_csv(TORONTO_CLEAN, usecols=["address", "lat", "long"])
    sales["key"] = sales["address"].str.upper().str.strip()
    table = GEOPACKAGES[1].stem
    con = sqlite3.connect(GEOPACKAGES[1])
    rows = con.execute(
        f'select upper(trim(o.address)), (r.minx + r.maxx) / 2, (r.miny + r.maxy) / 2 '
        f'from "{table}" o join "rtree_{table}_geom" r on r.id = o.fid '
        "where o.csdname = ? and o.address <> ? limit 100000",
        ("Toronto", ".."),
    ).fetchall()
    con.close()
    joined = sales.merge(pd.DataFrame(rows, columns=["key", "cx", "cy"]), on="key")
    assert len(joined) > 1000
    xy = np.array([to_statcan_lambert(a, b) for a, b in zip(joined["lat"], joined["long"])])
    distance = np.hypot(xy[:, 0] - joined["cx"], xy[:, 1] - joined["cy"])
    assert np.median(distance) < 15
