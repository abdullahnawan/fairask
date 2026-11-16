"""Tests for the market-data scraper: link picking and the Market Watch parser.

No network. The page and PDF text are small inline samples in the shape the
real ones had on 2026-11-16.
"""

from __future__ import annotations

import pandas as pd

from market import (
    newest_cmhc_link,
    newest_hpi_link,
    newest_market_watch_link,
    parse_market_watch,
    parse_turnover_rents,
)

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


def test_newest_cmhc_workbook_drops_the_query_string() -> None:
    page = (
        'href="https://assets.cmhc-schl.gc.ca/sites/x/2024/rmr-canada-2024-en.xlsx?rev=1"'
        'href="https://assets.cmhc-schl.gc.ca/sites/x/2025/rmr-canada-2025-en.xlsx?rev=2"'
    )
    assert newest_cmhc_link(page) == "https://assets.cmhc-schl.gc.ca/sites/x/2025/rmr-canada-2025-en.xlsx"


def table_6() -> pd.DataFrame:
    """Table 6.0 in miniature, with the traps the real one has: the title also
    says "Non-turnover", the sitting-tenant block repeats the bedroom labels,
    and a suppressed value is "**". Each bedroom group is four columns:
    Oct-24 value, its grade, Oct-25 value, its grade."""
    _ = None
    return pd.DataFrame([
        ["6.0 Average Rent for Turnover and Non-turnover Units"] + [_] * 17,
        [_, _, "Turnover units"] + [_] * 11 + ["Non-turnover units", _, _, _],
        [_, _, "Studio", _, _, _, "2 Bedroom", _, _, _, "Total", _, _, _, "Studio", _, _, _],
        [_] * 18,
        ["Centre", _] + ["Oct-24", _, "Oct-25", _] * 4,
        ["Toronto CMA", _, "1,830", "a", "1,708", "a", "2,612", "a", "2,547", "a",
         "2,358", "a", "2,256", "a", "1,409", "a", "1,443", "a"],
        ["Kitchener-Cambridge-Waterloo CMA", _, "1,430", "d", "**", _, "2,137", "a", "2,111", "a",
         "2,004", "a", "1,968", "a", "1,231", "b", "1,208", "b"],
    ])


def test_turnover_rents_take_the_latest_survey_and_skip_sitting_tenants() -> None:
    rents = parse_turnover_rents(table_6())
    assert set(rents["survey"]) == {"2025-10"}
    toronto = rents[rents["centre"] == "Toronto CMA"].set_index("bedrooms")["rent"]
    assert toronto.to_dict() == {"Studio": 1708, "2 Bedroom": 2547}
    assert 1443 not in set(rents["rent"].dropna())   # the non-turnover studio


def test_suppressed_rent_is_empty_not_zero() -> None:
    rents = parse_turnover_rents(table_6())
    kcw_studio = rents[(rents["centre"] == "Kitchener-Cambridge-Waterloo CMA") & (rents["bedrooms"] == "Studio")]
    assert pd.isna(kcw_studio["rent"].iloc[0])
