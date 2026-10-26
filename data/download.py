"""Download public source data into data/raw/.

    python data/download.py            # every source that is missing
    python data/download.py toronto    # just one

Each URL pins a git commit, so a download is byte-identical no matter when it
runs. That is what makes a training run reproducible, and it is why no checksum
is recorded here: the commit hash already fixes the content.

Sources needing a login or a licence click cannot be automated. They are listed
as manual in SOURCES.md, with the path to save them to.
"""

from __future__ import annotations

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
}


def fetch(name: str) -> Path:
    """Download one source unless it is already on disk. Returns its path."""
    url, relative = SOURCES[name]
    dest = RAW / relative
    if dest.exists():
        print(f"{name}: already have {relative}")
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"{name}: downloading {url}")
    # Download to a partial name first so an interrupted run never leaves a
    # truncated file that the next run would accept as complete.
    partial = dest.with_name(dest.name + ".partial")
    try:
        urllib.request.urlretrieve(url, partial)
        partial.replace(dest)
    finally:
        partial.unlink(missing_ok=True)
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
