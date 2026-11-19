"""Tests for POST /evaluate. They need the trained models and processed tables,
so they skip on a fresh clone until the ml/ and data/ scripts have run."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
NEEDED = [REPO / "ml" / "models" / "adjustment.txt",
          *(REPO / "data" / "processed" / name
            for name in ("hpi_monthly.csv", "trreb_market.csv", "cmhc_rents.csv"))]
pytestmark = pytest.mark.skipif(not all(p.exists() for p in NEEDED),
                                reason="models or processed tables missing; run ml/train.py and data/market.py")

from fastapi.testclient import TestClient  # noqa: E402

from finance import land_transfer_tax  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)

TORONTO = {
    "asking_cents": 1_250_000_00, "city": "Toronto", "district": "Toronto E01", "neighbourhood": "Danforth",
    "property_type": "semi_detached", "beds_above": 3, "beds_below": 1, "baths": 2,
    "sqft": 1500, "parking": 1, "basement": "finished",
    "description": "Renovated semi with a detached garage.", "mortgage_rate": 0.045,
}


def post(**changes):
    return client.post("/evaluate", json={**TORONTO, **changes})


def test_a_toronto_listing_gets_a_full_report() -> None:
    response = post(monthly_income_cents=20_000_00)
    assert response.status_code == 200, response.text
    body = response.json()
    v = body["valuation"]
    assert 0 < v["low_cents"] <= v["fair_cents"] <= v["high_cents"]
    assert body["verdict"]["label"] in {"Great deal", "Good", "Fair", "Overpriced"}
    assert 1 <= len(v["reasons"]) <= 5
    assert all(type(r["dollars_cents"]) is int for r in v["reasons"])
    assert body["costs"]["land_transfer_tax_cents"] == land_transfer_tax(1_250_000_00, in_toronto=True)
    assert body["costs"]["cmhc_premium_cents"] > 0          # minimum down payment is under 20%
    assert body["costs"]["stress_test"]["qualifying_rate"] == pytest.approx(0.065)
    assert body["market"]["area"]["area"] == "Toronto E01"
    assert body["investor"]["rent_source"]["centre"] == "Toronto CMA"
    assert body["notes"] == []


def test_lat_and_long_are_reported_as_one_location_reason() -> None:
    texts = [r["text"] for r in post().json()["valuation"]["reasons"]]
    assert len(texts) == len(set(texts))


def test_a_neighbourhood_supplies_the_location() -> None:
    """Without one, a Toronto house is valued like the coordinate-less Brampton sales."""
    with_place = post().json()["valuation"]["fair_cents"]
    without = post(neighbourhood=None).json()
    assert without["valuation"]["fair_cents"] != with_place
    assert "Pick a neighbourhood" in without["notes"][0]


def test_options_list_the_form_choices() -> None:
    body = client.get("/options").json()
    assert "Danforth" in body["neighbourhoods"] and "Toronto E01" in body["districts"]
    assert "Kitchener" in body["cities"]


def test_waterloo_region_says_accuracy_is_unmeasured() -> None:
    body = post(city="Kitchener", district=None, neighbourhood=None).json()
    assert body["market"]["area"] is None                  # TRREB covers the GTA only
    assert not any("Pick a neighbourhood" in note for note in body["notes"])
    assert any("has not been measured" in note for note in body["notes"])
    assert body["investor"]["rent_source"]["centre"] == "Kitchener-Cambridge-Waterloo CMA"
    assert body["costs"]["land_transfer_tax_cents"] == land_transfer_tax(1_250_000_00, in_toronto=False)


def test_twenty_percent_down_has_no_insurance() -> None:
    body = post(down_payment_cents=250_000_00).json()
    assert body["costs"]["cmhc_premium_cents"] == 0
    assert body["costs"]["mortgage_cents"] == 1_000_000_00


@pytest.mark.parametrize("bad", [
    {"asking_cents": 1_250_000.5},              # dollars as a float
    {"mortgage_rate": 4.5},                     # a percentage, not a share
    {"down_payment_cents": 1_000_00},           # under the minimum down payment
    {"down_payment_cents": 2_000_000_00},       # more than the price
    {"city": "Ottawa"},
    {"property_type": "castle"},
])
def test_bad_input_is_a_422(bad: dict) -> None:
    assert post(**bad).status_code == 422
