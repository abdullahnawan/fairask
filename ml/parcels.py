"""Measure each Toronto sale's lot from the City's property boundary polygons.

The sold dataset has no lot size, which is one of the biggest drivers of what a
detached house is worth. The City publishes every parcel boundary in Toronto, so
the lot can be recovered: project the sale's latitude and longitude into the
same coordinate system as the parcels, find the polygon it falls inside, and
measure that polygon.

Two things this file has to get right, and a test pins each:

* **The published attributes do not include an area.** The dataset ships only
  OBJECTID and a feature type, so the area is computed from the ring geometry
  with the shoelace formula rather than read from a column.
* **The file is in Web Mercator, which exaggerates area.** At Toronto's latitude
  a square metre of ground measures about 1.9 m2 on the projection, so every
  area is scaled by cos(latitude)^2 to undo it. Skipping that step would roughly
  double every lot.

Feature type decides whether the polygon is a lot at all. A CONDO parcel is the
land owned by a condominium corporation and shared by every unit in the
building, so its area belongs to no one unit; those rows get a parcel area but
no lot size. COMMON parcels are ordinary subdivision lots.

Reading the shapefile straight out of the zip keeps this to the standard library
plus numpy, and avoids unpacking an untrusted archive onto disk.

    python ml/parcels.py        # writes data/processed/toronto_lots.csv
"""

from __future__ import annotations

import math
import struct
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DEFAULT_ZIP = REPO / "data" / "raw" / "toronto_parcels" / "property_bnds_gcc_wgs84.zip"
TORONTO_CLEAN = REPO / "data" / "processed" / "toronto_clean.csv"
OUTPUT = REPO / "data" / "processed" / "toronto_lots.csv"

SHP_MEMBER = "PROPERTY_BOUNDARIES_WGS84.shp"
DBF_MEMBER = "PROPERTY_BOUNDARIES_WGS84.dbf"

EARTH_RADIUS_M = 6_378_137.0  # the sphere EPSG:3857 is defined on
# Parcels are tens of metres across, so a cell this size holds a handful of them.
CELL_M = 500.0
# A condominium's parcel is shared by every unit in it, so it is not a lot.
LOT_FEATURE_TYPE = "COMMON"


def to_web_mercator(lat: float, lon: float) -> tuple[float, float]:
    """Degrees -> EPSG:3857 metres, the projection the City publishes in."""
    x = math.radians(lon) * EARTH_RADIUS_M
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * EARTH_RADIUS_M
    return x, y


def to_latitude(y: float) -> float:
    """EPSG:3857 northing -> degrees, for the area correction."""
    return math.degrees(2 * math.atan(math.exp(y / EARTH_RADIUS_M)) - math.pi / 2)


def ring_area(ring: tuple[float, ...]) -> float:
    """Signed shoelace area of one ring, given as x, y, x, y, ... coordinates.

    The sign carries the winding direction, which is how a hole cancels against
    the outer ring it sits in.
    """
    total = 0.0
    previous_x, previous_y = ring[-2], ring[-1]
    for i in range(0, len(ring), 2):
        x, y = ring[i], ring[i + 1]
        total += previous_x * y - x * previous_y
        previous_x, previous_y = x, y
    return total / 2


def point_in_rings(rings: list[tuple[float, ...]], x: float, y: float) -> bool:
    """Crossing-number test across every ring, so a point in a hole is outside."""
    inside = False
    for ring in rings:
        previous_x, previous_y = ring[-2], ring[-1]
        for i in range(0, len(ring), 2):
            edge_x, edge_y = ring[i], ring[i + 1]
            if (edge_y > y) != (previous_y > y):
                crossing = (previous_x - edge_x) * (y - edge_y) / (previous_y - edge_y) + edge_x
                if x < crossing:
                    inside = not inside
            previous_x, previous_y = edge_x, edge_y
    return inside


class Parcels:
    """Every Toronto parcel, with a grid index over their bounding boxes.

    The polygons stay as raw shapefile bytes and are decoded one at a time, so
    the whole city costs about 100 MB of memory instead of a parsed copy.
    """

    def __init__(self, path: Path = DEFAULT_ZIP) -> None:
        if not path.exists():
            raise FileNotFoundError(
                f"Parcel boundaries not found at {path}. "
                "Run: python data/download.py toronto_parcels"
            )
        with zipfile.ZipFile(path) as archive:
            self._shp = archive.read(SHP_MEMBER)
            dbf = archive.read(DBF_MEMBER)

        self.feature_types = _read_feature_types(dbf)
        self._offsets, self.boxes = _read_shape_index(self._shp)
        if len(self.feature_types) != len(self._offsets):
            raise ValueError(
                f"{len(self.feature_types)} attribute rows but {len(self._offsets)} shapes"
            )

        self._origin = self.boxes[:, 0].min(), self.boxes[:, 1].min()
        self._grid = _build_grid(self.boxes, self._origin)

    def __len__(self) -> int:
        return len(self._offsets)

    def rings(self, index: int) -> list[tuple[float, ...]]:
        """The polygon's rings, each a flat x, y, x, y, ... tuple."""
        at = self._offsets[index]
        part_count, point_count = struct.unpack("<ii", self._shp[at + 36 : at + 44])
        starts = list(
            struct.unpack(f"<{part_count}i", self._shp[at + 44 : at + 44 + 4 * part_count])
        ) + [point_count]
        first = at + 44 + 4 * part_count
        flat = struct.unpack(f"<{point_count * 2}d", self._shp[first : first + 16 * point_count])
        return [flat[2 * starts[p] : 2 * starts[p + 1]] for p in range(part_count)]

    def area_m2(self, index: int) -> float:
        """Ground area in square metres, with the Web Mercator stretch removed."""
        projected = abs(sum(ring_area(ring) for ring in self.rings(index)))
        box = self.boxes[index]
        latitude = to_latitude((box[1] + box[3]) / 2)
        return projected * math.cos(math.radians(latitude)) ** 2

    def locate(self, x: float, y: float) -> int | None:
        """Index of the parcel containing a projected point, or None."""
        origin_x, origin_y = self._origin
        cell = int((x - origin_x) // CELL_M), int((y - origin_y) // CELL_M)
        for index in self._grid.get(cell, ()):
            left, bottom, right, top = self.boxes[index]
            if (
                left <= x <= right
                and bottom <= y <= top
                and point_in_rings(self.rings(index), x, y)
            ):
                return index
        return None


def _read_feature_types(dbf: bytes) -> list[str]:
    """COMMON, CONDO, CORRIDOR or RESERVE, one per shape, from the dBASE table.

    The table holds only OBJECTID (31 bytes) and F_TYPE (50), in that order,
    after the one-byte deletion flag, so the field offsets are fixed here rather
    than parsed out of the header. The record length is checked instead.
    """
    record_count, header_length, record_length = struct.unpack("<IHH", dbf[4:12])
    if record_length != 82:
        raise ValueError(f"unexpected dBASE record length {record_length}, expected 82")
    return [
        dbf[header_length + i * record_length + 32 : header_length + i * record_length + 82]
        .decode("latin-1")
        .strip()
        for i in range(record_count)
    ]


def _read_shape_index(shp: bytes) -> tuple[list[int], np.ndarray]:
    """Walk the shapefile once, recording where each polygon starts and its box."""
    offsets, boxes = [], []
    position, end = 100, len(shp)
    while position < end:
        content_words = struct.unpack(">i", shp[position + 4 : position + 8])[0]
        body = position + 8
        shape_type = struct.unpack("<i", shp[body : body + 4])[0]
        if shape_type != 5:
            raise ValueError(f"expected polygons (shape type 5), found {shape_type}")
        boxes.append(struct.unpack("<4d", shp[body + 4 : body + 36]))
        offsets.append(body)
        position = body + content_words * 2
    return offsets, np.asarray(boxes)


def _build_grid(boxes: np.ndarray, origin: tuple[float, float]) -> dict:
    origin_x, origin_y = origin
    left = ((boxes[:, 0] - origin_x) // CELL_M).astype(int)
    bottom = ((boxes[:, 1] - origin_y) // CELL_M).astype(int)
    right = ((boxes[:, 2] - origin_x) // CELL_M).astype(int)
    top = ((boxes[:, 3] - origin_y) // CELL_M).astype(int)
    grid: dict[tuple[int, int], list[int]] = {}
    for index, (x0, y0, x1, y1) in enumerate(zip(left, bottom, right, top)):
        for cell_x in range(x0, x1 + 1):
            for cell_y in range(y0, y1 + 1):
                grid.setdefault((cell_x, cell_y), []).append(index)
    return grid


def join_lots(sales: pd.DataFrame, parcels: Parcels) -> pd.DataFrame:
    """Return mls, parcel_type, parcel_area_m2 and lot_area_m2 for each sale.

    `lot_area_m2` is left empty where the point fell outside every parcel, or
    inside a condominium's shared parcel, which is not a lot.
    """
    found = [
        parcels.locate(*to_web_mercator(lat, lon))
        for lat, lon in zip(sales["lat"], sales["long"])
    ]

    lots = pd.DataFrame(
        {
            "mls": sales["mls"].to_numpy(),
            "parcel_type": [None if i is None else parcels.feature_types[i] for i in found],
            "parcel_area_m2": [
                np.nan if i is None else round(parcels.area_m2(i), 1) for i in found
            ],
        }
    )
    lots["lot_area_m2"] = lots["parcel_area_m2"].where(lots["parcel_type"] == LOT_FEATURE_TYPE)
    return lots


def main() -> None:
    if not TORONTO_CLEAN.exists():
        raise FileNotFoundError(f"{TORONTO_CLEAN} not found. Run: python ml/toronto.py")

    sales = pd.read_csv(TORONTO_CLEAN)
    parcels = Parcels()
    lots = join_lots(sales, parcels)
    lots.to_csv(OUTPUT, index=False)

    matched = lots["parcel_type"].notna().sum()
    with_lot = lots["lot_area_m2"].notna().sum()
    print(f"{len(parcels):,} parcels, {len(sales):,} sales -> {OUTPUT.relative_to(REPO)}")
    print(f"inside a parcel: {matched:,} ({matched / len(sales):.1%})")
    print(f"of those, an ownable lot: {with_lot:,} ({with_lot / len(sales):.1%})\n")
    print(pd.crosstab(sales["property_type"], lots["parcel_type"].fillna("(none)")).to_string())
    print("\nlot area m2, by property type")
    print(
        lots.assign(property_type=sales["property_type"].to_numpy())
        .groupby("property_type")["lot_area_m2"]
        .describe(percentiles=[0.5])
        .round(1)
        .to_string()
    )


if __name__ == "__main__":
    main()
