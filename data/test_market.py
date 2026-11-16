"""Tests for the market-data scraper: link picking and the Market Watch parser.

No network. The page and PDF text are small inline samples in the shape the
real ones had on 2026-11-16.
"""

from __future__ import annotations

from market import newest_hpi_link, newest_market_watch_link, parse_market_watch

HPI_PAGE = """
<a href="https://www.crea.ca/files/mls-hpi-data/MLS_HPI_Sep_2026.zip">old</a>
<a href="https://www.crea.ca/files/mls-hpi-data/MLS_HPI_Oct_2026.zip">Download</a>
<a href="https://www.crea.ca/files/mls-hpi-data/MLS_HPI_Dec_2025.zip">older</a>
"""

TRREB_PAGE = """
<a href="/wp-content/files/market-stats/market-watch/mw2608pdf">broken link on the real page</a>
<a href="/wp-content/files/market-stats/market-watch/mw2610.pdf">October</a>
<a href="/wp-content/files/market-stats/market-watch/mw2609.pdf">September</a>
<a href="/wp-content/files/market-stats/market-watch/Simcoe_County_mw2611.pdf">not the GTA report</a>
"""

PDF_TEXT = """
All Home types, October 2026
Sales Dollar Volume Average Price Median Price New Listings SNLR Trend Active Listings
Brampton 435 $358,954,453 $825,183 $800,000 960 35.9% 1,617 4.6 98% 30 51
Toronto E01 63 $77,859,400 $1,235,863 $1,115,000 144 47.9% 155 2.4 106% 13 17
Clarington 111 $9,061,000 $742,452 $680,000 314 41.8% 467 3.2 99% 25 43
Brampton 4,037 $3,536,071,303 $875,916 $830,000 11,493 97% 31 51
"""


def test_newest_hpi_is_by_date_not_page_order() -> None:
    assert newest_hpi_link(HPI_PAGE).endswith("MLS_HPI_Oct_2026.zip")


def test_newest_market_watch_skips_broken_and_regional_links() -> None:
    url = newest_market_watch_link(TRREB_PAGE)
    assert url == "https://trreb.ca/wp-content/files/market-stats/market-watch/mw2610.pdf"


def test_no_link_means_none() -> None:
    assert newest_hpi_link("<html></html>") is None
    assert newest_market_watch_link("<html></html>") is None


def test_parser_keeps_consistent_rows_and_drops_a_shifted_one() -> None:
    """Clarington carries Brock's dollar volume, the error layout mode made."""
    table, dropped = parse_market_watch(PDF_TEXT, "2026-10")
    assert list(table["area"]) == ["Brampton", "Toronto E01"]
    assert dropped == 1
    brampton = table.iloc[0]
    assert (brampton["snlr"], brampton["months_inventory"], brampton["sp_lp"]) == (35.9, 4.6, 98)
    assert brampton["active_listings"] == 1617 and brampton["month"] == "2026-10"


def test_year_to_date_rows_never_match() -> None:
    """The YTD table has no SNLR column; mixing it in would double-count."""
    table, _ = parse_market_watch(PDF_TEXT, "2026-10")
    assert (table["sales"] != 4037).all()
