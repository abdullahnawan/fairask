"""Fetch the newest public market statistics: CREA's HPI workbook and TRREB's
monthly Market Watch report.

Both are published every month on public pages with no login. Each page links
the newest file under a name that changes with the month
(`MLS_HPI_Oct_2026.zip`, `mw2610.pdf`), so this script reads the page, picks the
newest link, and downloads it if it is not already on disk. That is the
"scraping": one page request and one file request per source, a pause between
requests, and a User-Agent that names the project.

* **CREA HPI.** The four workbooks are extracted into `data/raw/crea_hpi/`,
  where `ml/hpi.py` already reads them. CREA names the zip for the month it was
  published, so `MLS_HPI_Oct_2026.zip` holds data through September 2026.
* **TRREB Market Watch.** The "All Home types" summary is the only table with
  the sales-to-new-listings ratio (SNLR), months of inventory, sale-to-list
  ratio and days on market for every GTA municipality and Toronto district.
  Those are what the deal report needs to call a buyer's or seller's market.

The PDF is read with `pdftotext -raw` (xpdf/poppler, bundled with Git for
Windows). Layout mode was tried first and shifts cells into neighbouring rows
wherever a cell is blank; raw mode keeps each row whole. Every parsed row is
still checked: sales x average price must reproduce the dollar volume, and a
row that fails is dropped and counted rather than trusted.

    python data/market.py      # writes data/processed/trreb_market.csv
"""

from __future__ import annotations

import re
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

from download import RAW, USER_AGENT, save

PROCESSED = RAW.parent / "processed"
OUTPUT = PROCESSED / "trreb_market.csv"

HPI_PAGE = "https://www.crea.ca/housing-market-stats/mls-home-price-index/hpi-tool/"
HPI_LINK = re.compile(r"https://www\.crea\.ca/files/mls-hpi-data/MLS_HPI_([A-Z][a-z]{2})_(\d{4})\.zip")
TRREB_PAGE = "https://trreb.ca/market-data/market-watch/"
TRREB_LINK = re.compile(r"/wp-content/files/market-stats/market-watch/mw(\d{2})(\d{2})\.pdf")

# Seconds between requests to the same site. Two sites, four requests a run:
# this is courtesy, not throttling.
PAUSE = 2.0
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# One row of the monthly "All Home types" table. Year-to-date and per-type
# tables have no SNLR or months-of-inventory column, so they never match.
ROW = re.compile(
    r"^(?P<area>[A-Za-z][A-Za-z0-9 .'&/-]*?) (?P<sales>[\d,]+) \$(?P<volume>[\d,]+) "
    r"\$(?P<average_price>[\d,]+) \$(?P<median_price>[\d,]+) (?P<new_listings>[\d,]+) "
    r"(?P<snlr>[\d.]+)% (?P<active_listings>[\d,]+) (?P<months_inventory>[\d.]+) "
    r"(?P<sp_lp>\d+)% (?P<ldom>\d+) (?P<pdom>\d+)$"
)


def get_page(url: str) -> str:
    time.sleep(PAUSE)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def newest_hpi_link(page: str) -> str | None:
    """The HPI zip for the latest month linked on CREA's page."""
    links = {m.group(0): (int(m.group(2)), MONTHS.index(m.group(1))) for m in HPI_LINK.finditer(page)}
    return max(links, key=links.get) if links else None


def newest_market_watch_link(page: str) -> str | None:
    """The Market Watch PDF for the latest month linked on TRREB's page."""
    links = {m.group(0): m.group(1) + m.group(2) for m in TRREB_LINK.finditer(page)}
    return "https://trreb.ca" + max(links, key=links.get) if links else None


def fetch_hpi() -> Path:
    """Download the newest HPI zip and extract its workbooks for ml/hpi.py."""
    url = newest_hpi_link(get_page(HPI_PAGE))
    if url is None:
        raise ValueError(f"no MLS_HPI_<Mon>_<Year>.zip link on {HPI_PAGE}; the page has changed")
    archive = RAW / "crea_hpi" / url.rsplit("/", 1)[1]
    if not archive.exists():
        time.sleep(PAUSE)
        save(url, archive)
    with zipfile.ZipFile(archive) as z:
        z.extractall(archive.parent)
    return archive


def fetch_market_watch() -> Path:
    url = newest_market_watch_link(get_page(TRREB_PAGE))
    if url is None:
        raise ValueError(f"no mwYYMM.pdf link on {TRREB_PAGE}; the page has changed")
    pdf = RAW / "trreb" / url.rsplit("/", 1)[1]
    if not pdf.exists():
        time.sleep(PAUSE)
        save(url, pdf)
    return pdf


def parse_market_watch(text: str, month: str) -> tuple[pd.DataFrame, int]:
    """Rows of the monthly summary that pass the dollar-volume check, and how
    many matched the row pattern but failed it."""
    rows = [m.groupdict() for line in text.splitlines() if (m := ROW.match(line.strip()))]
    table = pd.DataFrame(rows)
    if table.empty:
        return table, 0
    for column in table.columns.drop("area"):
        table[column] = pd.to_numeric(table[column].str.replace(",", ""))
    # The average is rounded to the dollar, so allow a cent per sale of slack.
    consistent = (table["sales"] * table["average_price"] - table["volume"]).abs() <= table["sales"]
    table = table[consistent].drop_duplicates("area").drop(columns="volume")
    table.insert(1, "month", month)
    return table.reset_index(drop=True), int((~consistent).sum())


def main() -> None:
    archive = fetch_hpi()
    print(f"CREA HPI: {archive.name} extracted into {archive.parent.relative_to(RAW.parent)}")
    print("  run python ml/hpi.py to rebuild the monthly table")

    pdf = fetch_market_watch()
    yy, mm = pdf.stem[2:4], pdf.stem[4:6]
    text = subprocess.run(
        ["pdftotext", "-raw", str(pdf), "-"], capture_output=True, check=True, text=True,
        encoding="utf-8", errors="replace",
    ).stdout
    table, dropped = parse_market_watch(text, f"20{yy}-{mm}")
    PROCESSED.mkdir(exist_ok=True)
    table.to_csv(OUTPUT, index=False)
    print(f"TRREB Market Watch {pdf.name}: {len(table)} areas -> {OUTPUT.relative_to(RAW.parent)}"
          f" ({dropped} rows failed the dollar-volume check and were dropped)")


if __name__ == "__main__":
    main()
