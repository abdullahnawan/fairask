"""Download public source data into data/raw/.

    python data/download.py            # every source that is missing
    python data/download.py toronto    # just one

Where a source lives in a git repo the URL pins a commit, so the download is
byte-identical no matter when it runs. That is what makes a training run
reproducible, and it is why no checksum is recorded for those: the commit hash
already fixes the content.

The City of Toronto open-data endpoint offers no such pin. It serves whatever
the dataset was last refreshed to, so SOURCES.md records the refresh date and
byte count of the copy this project was built against, and a later download may
legitimately differ.

Sources needing a login or a licence click cannot be automated. They are listed
as manual in SOURCES.md, with the path to save them to.
"""

from __future__ import annotations

import shutil
import sys
import urllib.request
from pathlib import Path

RAW = Path(__file__).resolve().parent / "raw"

# name -> (url, path under data/raw/)
# shortcut: plain file downloads only. Add per-source handling when a source
# needs Kaggle credentials, an API query or archive extraction.
SOURCES: dict[str, tuple[str, str]] = {
    "toronto": (
        "https://raw.githubusercontent.com/slavaspirin/Toronto-housing-price-prediction/"
        "3b0c48df241c349419f9787591b7cb55e2e1a84c/houses.csv",
        "toronto_sales/houses.csv",
    ),
    "brampton": (
        "https://raw.githubusercontent.com/AndrewTymkiv/real_estate_analysis/"
        "9512ffe712bae19a4138409ca39bf90c0f8c24b6/Resources/Sold_homes_combined_final.csv",
        "brampton_sales/Sold_homes_combined_final.csv",
    ),
    "toronto_parcels": (
        "https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/"
        "1acaa8b0-f235-4df6-8305-02025ccdeb07/resource/"
        "d9a29cdd-6434-4b12-96f7-0d3071873d05/download/property_bnds_gcc_wgs84.zip",
        "toronto_parcels/property_bnds_gcc_wgs84.zip",
    ),
    # Two files because the City splits the series; both are needed for a
    # full 2000-onward view of new builds.
    "toronto_permits_2000_2016": (
        "https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/"
        "9e42a85b-180f-4dc5-b0d7-d46661a6c0ec/resource/"
        "c647bdae-0127-425e-86e6-2d88ff0e2adf/download/export_202507081211.csv",
        "toronto_permits/cleared_permits_2000_2016.csv",
    ),
    "toronto_permits_2017": (
        "https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/"
        "9e42a85b-180f-4dc5-b0d7-d46661a6c0ec/resource/"
        "b41c3e9e-4d2d-4b09-a789-9569d8da407c/download/cleared-building-permits-since-2017.csv",
        "toronto_permits/cleared_permits_since_2017.csv",
    ),
    # StatCan splits Ontario into three parts; which holds Toronto is not
    # documented, so all three are fetched.
    "statcan_odb_on_1": (
        "https://www150.statcan.gc.ca/pub/34-26-0001/2018001/zip/ODB_v3_ON_1.zip",
        "statcan_odb/ODB_v3_ON_1.zip",
    ),
    "statcan_odb_on_2": (
        "https://www150.statcan.gc.ca/pub/34-26-0001/2018001/zip/ODB_v3_ON_2.zip",
        "statcan_odb/ODB_v3_ON_2.zip",
    ),
    "statcan_odb_on_3": (
        "https://www150.statcan.gc.ca/pub/34-26-0001/2018001/zip/ODB_v3_ON_3.zip",
        "statcan_odb/ODB_v3_ON_3.zip",
    ),
}


# Identifies the project to site operators; some servers refuse Python's default.
USER_AGENT = "FairAsk/0.1 (portfolio project; https://github.com/abdullahnawan/fairask)"


def save(url: str, dest: Path) -> Path:
    """Download url to dest, refusing an HTML page in place of the data file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Download to a partial name first so an interrupted run never leaves a
    # truncated file that the next run would accept as complete.
    partial = dest.with_name(dest.name + ".partial")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=300) as response, open(partial, "wb") as out:
            # A server can answer 200 with an outage or login page. Saving that as
            # the data file hides the failure until something tries to parse it.
            if response.headers.get_content_type() == "text/html":
                raise ValueError(f"{url}: server returned an HTML page, not the data file")
            shutil.copyfileobj(response, out)
        partial.replace(dest)
    finally:
        partial.unlink(missing_ok=True)
    return dest


def fetch(name: str) -> Path:
    """Download one source unless it is already on disk. Returns its path."""
    url, relative = SOURCES[name]
    dest = RAW / relative
    if dest.exists():
        print(f"{name}: already have {relative}")
        return dest

    print(f"{name}: downloading {url}")
    save(url, dest)
    print(f"{name}: saved {relative} ({dest.stat().st_size:,} bytes)")
    return dest


def main(names: list[str]) -> int:
    unknown = sorted(set(names) - set(SOURCES))
    if unknown:
        print(f"unknown source: {', '.join(unknown)}", file=sys.stderr)
        print(f"available: {', '.join(SOURCES)}", file=sys.stderr)
        return 1
    for name in names or SOURCES:
        fetch(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
