"""Building footprint area for each Toronto sale, from StatCan's building outlines.

29.9% of Toronto listings carry no square-footage bucket. Statistics Canada's
Open Database of Buildings has the outline of every Toronto building, so the
ground-floor area of a house can be measured even when the agent left the size
blank. The footprint goes to the model as its own feature. Turning it into a
square-footage estimate (footprint x a ratio per property type) was tried and
made the model worse, so that estimate is only measured here, not written out.

What the source does and does not give, measured 2026-11-16:

* Toronto rows carry **no sq_ft and no floors** (all ".."). Only the outline,
  an address on about 70% of them, and a `height` whose median is 4.1 m. That
  is too low for a two-storey house, so it is not used as a storey count.
* The geometry is EPSG:3347, Statistics Canada Lambert. It is conformal, not
  equal-area, and at Toronto's latitude it stretches lengths by k = 1.024, so
  every area is divided by k^2 (about 4.9%).

A sale is matched to a building by exact address first, then by the building
whose outline contains the sale's coordinates. Where an address has several
outlines (house plus garage), the largest is taken. Only detached and
semi-detached sales get a footprint: a condo or townhouse block's outline is
the whole building, not the unit, which is the same rule as lot size.

The estimate is approximate twice over, because the listing buckets it is
calibrated against are themselves ranges. Its error against those buckets is
measured on held-out districts and printed, so the claim stays checkable.

    python ml/footprints.py     # writes data/processed/toronto_footprints.csv
"""

from __future__ import annotations

import math
import sqlite3
import struct
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from parcels import point_in_rings, ring_area

REPO = Path(__file__).resolve().parent.parent
ODB_DIR = REPO / "data" / "raw" / "statcan_odb"
# StatCan's Ontario parts 1 and 2 hold every Toronto building; part 3 holds none.
GEOPACKAGES = tuple(ODB_DIR / f"ODB_v3_ON_{n}.gpkg" for n in (1, 2))
TORONTO_CLEAN = REPO / "data" / "processed" / "toronto_clean.csv"
OUTPUT = REPO / "data" / "processed" / "toronto_footprints.csv"

SQFT_PER_M2 = 10.763910
ESTIMATED_TYPES = ("detached", "semi_detached")

# EPSG:3347, Lambert conformal conic with two standard parallels on GRS80.
_A = 6_378_137.0
_E = math.sqrt(2 / 298.257222101 - (1 / 298.257222101) ** 2)
_LAT0, _LON0 = math.radians(63.390675), math.radians(-91.86666666666666)
_LAT1, _LAT2 = math.radians(49.0), math.radians(77.0)
_X0, _Y0 = 6_200_000.0, 3_000_000.0


def _m(phi: float) -> float:
    return math.cos(phi) / math.sqrt(1 - (_E * math.sin(phi)) ** 2)


def _t(phi: float) -> float:
    s = _E * math.sin(phi)
    return math.tan(math.pi / 4 - phi / 2) / ((1 - s) / (1 + s)) ** (_E / 2)


_N = (math.log(_m(_LAT1)) - math.log(_m(_LAT2))) / (math.log(_t(_LAT1)) - math.log(_t(_LAT2)))
_F = _m(_LAT1) / (_N * _t(_LAT1) ** _N)
_R0 = _A * _F * _t(_LAT0) ** _N


def to_statcan_lambert(lat: float, lon: float) -> tuple[float, float]:
    """Degrees -> EPSG:3347 metres."""
    r = _A * _F * _t(math.radians(lat)) ** _N
    theta = _N * (math.radians(lon) - _LON0)
    return _X0 + r * math.sin(theta), _Y0 + _R0 - r * math.cos(theta)


def scale_factor(lat: float) -> float:
    """How much the projection stretches a length at this latitude."""
    phi = math.radians(lat)
    return _A * _F * _N * _t(phi) ** _N / (_A * _m(phi))


def polygon_rings(blob: bytes) -> list[tuple[float, ...]]:
    """Rings of a GeoPackage (Multi)Polygon, each a flat x, y, x, y, ... tuple."""
    envelope = (blob[3] >> 1) & 0b111
    at = 8 + {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[envelope]
    rings: list[tuple[float, ...]] = []

    def polygon(at: int, order: str) -> int:
        (ring_count,) = struct.unpack_from(order + "I", blob, at)
        at += 4
        for _ in range(ring_count):
            (points,) = struct.unpack_from(order + "I", blob, at)
            rings.append(struct.unpack_from(f"{order}{2 * points}d", blob, at + 4))
            at += 4 + 16 * points
        return at

    order = "<" if blob[at] == 1 else ">"
    (kind,) = struct.unpack_from(order + "I", blob, at + 1)
    if kind == 3:
        polygon(at + 5, order)
    elif kind == 6:
        (count,) = struct.unpack_from(order + "I", blob, at + 5)
        at += 9
        for _ in range(count):
            order = "<" if blob[at] == 1 else ">"
            at = polygon(at + 5, order)
    else:
        raise ValueError(f"expected a polygon or multipolygon, got WKB type {kind}")
    return rings


# k varies by under 0.1% between Toronto's north and south edges, so one
# correction at the city's centre latitude serves every building.
TORONTO_AREA_SCALE = scale_factor(43.7) ** 2


def footprint_m2(blob: bytes) -> float:
    """Ground area in square metres, with the Lambert stretch removed."""
    return abs(sum(ring_area(ring) for ring in polygon_rings(blob))) / TORONTO_AREA_SCALE


def extract(paths: tuple[Path, ...] = GEOPACKAGES) -> None:
    """Unzip each GeoPackage next to its download; SQLite cannot read a zip."""
    for path in paths:
        if path.exists():
            continue
        archive = path.with_suffix(".zip")
        if not archive.exists():
            raise FileNotFoundError(
                f"{archive} not found. Run: python data/download.py statcan_odb_on_1 statcan_odb_on_2"
            )
        with zipfile.ZipFile(archive) as z:
            z.extract(path.name, path.parent)


def match_footprints(sales: pd.DataFrame, paths: tuple[Path, ...] = GEOPACKAGES) -> pd.Series:
    """Footprint in m2 of each sale's building, NaN where none was found."""
    extract(paths)
    wanted = sales["address"].str.upper().str.strip()
    wanted_set = set(wanted)
    by_address: dict[str, float] = {}
    connections = []
    for path in paths:
        con = sqlite3.connect(path)
        connections.append((con, path.stem))
        query = f'select upper(trim(address)), geom from "{path.stem}" where csdname = ? and address <> ?'
        for address, blob in con.execute(query, ("Toronto", "..")):
            if address in wanted_set:
                by_address[address] = max(footprint_m2(blob), by_address.get(address, 0.0))

    found = wanted.map(by_address)
    for i in np.flatnonzero(found.isna().to_numpy()):
        lat, lon = sales["lat"].iat[i], sales["long"].iat[i]
        if pd.isna(lat):
            continue
        x, y = to_statcan_lambert(lat, lon)
        for con, table in connections:
            query = (
                f'select o.geom from "{table}" o join "rtree_{table}_geom" r on r.id = o.fid '
                "where r.minx <= ? and r.maxx >= ? and r.miny <= ? and r.maxy >= ?"
            )
            hits = [b for (b,) in con.execute(query, (x, x, y, y))
                    if point_in_rings(polygon_rings(b), x, y)]
            if hits:
                found.iat[i] = max(footprint_m2(b) for b in hits)
                break
    for con, _ in connections:
        con.close()
    return found


def fit_ratios(table: pd.DataFrame) -> pd.Series:
    """Median floor-area / footprint ratio per property type, from known rows."""
    known = table.dropna(subset=["sqft_mid", "footprint_sqft"])
    return (known["sqft_mid"] / known["footprint_sqft"]).groupby(known["property_type"]).median()


def holdout_error(table: pd.DataFrame) -> pd.DataFrame:
    """Fit ratios on half the districts, score the estimate on the other half."""
    known = table.dropna(subset=["sqft_mid", "footprint_sqft"])
    known = known[known["property_type"].isin(ESTIMATED_TYPES)]
    districts = pd.Series(known["city_district"].unique())
    held = set(districts.sample(frac=0.5, random_state=0))
    test = known["city_district"].isin(held)
    ratios = fit_ratios(known[~test])
    estimate = known.loc[test, "footprint_sqft"] * known.loc[test, "property_type"].map(ratios)
    ape = (estimate - known.loc[test, "sqft_mid"]).abs() / known.loc[test, "sqft_mid"]
    return ape.groupby(known.loc[test, "property_type"]).agg(["count", "median", "mean"])


def main() -> None:
    if not TORONTO_CLEAN.exists():
        raise FileNotFoundError(f"{TORONTO_CLEAN} not found. Run: python ml/toronto.py")
    sales = pd.read_csv(TORONTO_CLEAN)
    sales["footprint_m2"] = match_footprints(sales)
    sales.loc[~sales["property_type"].isin(ESTIMATED_TYPES), "footprint_m2"] = np.nan
    sales["footprint_sqft"] = sales["footprint_m2"] * SQFT_PER_M2

    sales[["mls", "footprint_m2"]].round({"footprint_m2": 1}).to_csv(OUTPUT, index=False)
    ratios = fit_ratios(sales[sales["property_type"].isin(ESTIMATED_TYPES)])

    freehold = sales["property_type"].isin(ESTIMATED_TYPES)
    print(f"{len(sales):,} sales -> {OUTPUT.relative_to(REPO)}")
    print(f"detached/semi with a footprint: {sales.loc[freehold, 'footprint_m2'].notna().sum():,} "
          f"of {freehold.sum():,}")
    print("\nfloor area / footprint, fitted ratio:", ratios.round(2).to_dict())
    print("\nestimate vs listing bucket midpoint, held-out districts (APE):")
    print(holdout_error(sales).round(3).to_string())


if __name__ == "__main__":
    main()
