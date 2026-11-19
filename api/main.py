"""FastAPI app: POST /evaluate turns one listing into a deal report.

    uvicorn main:app --app-dir api --reload

Money in and out is integer cents; shares (rates, vacancy) are fractions, so
5% is 0.05. Anything the engine refuses (a float price, a down payment under
the minimum, a rate given as 5 instead of 0.05) comes back as a 422.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from context import area_market, hpi_context, red_flags
from finance import cmhc_premium, land_transfer_tax, minimum_down_payment, monthly_payment, stress_test
from investor import cmhc_rent, investor_view
from valuation import SQFT_PER_M2, value
from verdict import verdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ml"))
from adjust import HPI_TYPE, load_hpi_table  # noqa: E402
from keywords import FLAGS, flags  # noqa: E402

PROCESSED = Path(__file__).resolve().parent.parent / "data" / "processed"

# City -> CREA HPI region. The townships of Waterloo Region follow Kitchener-
# Waterloo, except North Dumfries, which borders and trades with Cambridge.
CITY_REGION = {
    "Toronto": "Greater Toronto", "Brampton": "Greater Toronto", "Caledon": "Greater Toronto",
    "Vaughan": "Greater Toronto", "Markham": "Greater Toronto", "Richmond Hill": "Greater Toronto",
    "Aurora": "Greater Toronto", "Newmarket": "Greater Toronto", "Pickering": "Greater Toronto",
    "Ajax": "Greater Toronto", "Whitby": "Greater Toronto", "Oshawa": "Greater Toronto",
    "Mississauga": "Mississauga", "Oakville": "Oakville-Milton", "Milton": "Oakville-Milton",
    "Kitchener": "Kitchener-Waterloo", "Waterloo": "Kitchener-Waterloo",
    "Woolwich": "Kitchener-Waterloo", "Wilmot": "Kitchener-Waterloo",
    "Wellesley": "Kitchener-Waterloo", "Cambridge": "Cambridge", "North Dumfries": "Cambridge",
}
TRAINED_REGIONS = {"Greater Toronto"}

Cents = Annotated[int, Field(strict=True, ge=0)]
BASEMENT_FLAGS = {"finished": "basement_finished", "apartment": "basement_apartment",
                  "walkout": "basement_walkout"}


class Listing(BaseModel):
    asking_cents: Annotated[int, Field(strict=True, gt=0)]
    city: Literal[tuple(CITY_REGION)]  # type: ignore[valid-type]
    district: str | None = Field(None, description="TRREB area, e.g. 'Toronto C01'")
    neighbourhood: str | None = Field(None, description="City of Toronto neighbourhood, for location")
    lat: float | None = Field(None, ge=42, le=45)
    long: float | None = Field(None, ge=-81.5, le=-78)
    property_type: Literal[tuple(HPI_TYPE)]  # type: ignore[valid-type]
    beds_above: int = Field(ge=0, le=20)
    beds_below: int = Field(0, ge=0, le=10)
    baths: float = Field(ge=0, le=20)
    sqft: int | None = Field(None, gt=0, le=20_000)
    lot_sqft: int | None = Field(None, gt=0, le=2_000_000)
    year_built: int | None = Field(None, ge=1800, le=2030)
    parking: int | None = Field(None, ge=0, le=20)
    basement: Literal["none", "unfinished", "finished", "apartment", "walkout"] | None = None
    garage: bool | None = None
    description: str = Field("", max_length=10_000)
    days_on_market: int | None = Field(None, ge=0)
    original_list_cents: Cents | None = None
    # cost to own
    down_payment_cents: Cents | None = None
    mortgage_rate: float = Field(ge=0, lt=0.25)
    amortization_years: int = Field(25, ge=5, le=30)
    first_time_buyer: bool = False
    monthly_income_cents: Cents | None = None
    monthly_debt_cents: Cents = 0
    monthly_property_tax_cents: Cents = 0
    monthly_heat_cents: Cents = 0
    monthly_condo_fees_cents: Cents = 0
    monthly_rent_cents: Cents | None = Field(None, description="Overrides the CMHC estimate")


app = FastAPI(title="FairAsk")


@lru_cache(maxsize=1)
def tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (load_hpi_table(), pd.read_csv(PROCESSED / "trreb_market.csv"),
            pd.read_csv(PROCESSED / "cmhc_rents.csv"))


@lru_cache(maxsize=1)
def neighbourhoods() -> pd.DataFrame:
    """Median sale location of each Toronto neighbourhood in the training data."""
    table = pd.read_csv(PROCESSED / "model_table.csv", usecols=["source", "district", "lat", "long"])
    return table[table["source"] == "toronto"].groupby("district")[["lat", "long"]].median()


def location(listing: Listing) -> tuple[float | None, float | None]:
    if listing.lat is not None and listing.long is not None:
        return listing.lat, listing.long
    if listing.city == "Toronto" and listing.neighbourhood in neighbourhoods().index:
        lat, long = neighbourhoods().loc[listing.neighbourhood]
        return float(lat), float(long)
    return None, None


def model_features(listing: Listing, region: str) -> dict:
    found = flags(listing.description)
    lat, long = location(listing)
    if listing.basement in BASEMENT_FLAGS:
        found[BASEMENT_FLAGS[listing.basement]] = True
    if listing.garage is not None:
        found["garage"] = listing.garage
    return {
        "property_type": listing.property_type, "region": region,
        "beds_above": listing.beds_above, "beds_below": listing.beds_below, "baths": listing.baths,
        "sqft_mid": listing.sqft, "lat": lat, "long": long, "parking": listing.parking, "year_built": listing.year_built,
        # Lot size was only trained on freehold homes; a condo's parcel is the whole building.
        "lot_area_m2": (listing.lot_sqft / SQFT_PER_M2
                        if listing.lot_sqft and listing.property_type in ("detached", "semi_detached")
                        else None),
        **{name: found[name] for name in FLAGS},
    }


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/options")
def options() -> dict:
    """Choices for the form's dropdowns."""
    return {
        "cities": list(CITY_REGION),
        "property_types": list(HPI_TYPE),
        "neighbourhoods": neighbourhoods().index.tolist(),
        "districts": tables()[1]["area"].tolist(),
    }


@app.post("/evaluate")
def evaluate(listing: Listing) -> dict:
    hpi, trreb, rents = tables()
    region = CITY_REGION[listing.city]
    asking = listing.asking_cents
    valuation = value(model_features(listing, region), hpi)
    deal = verdict(asking, valuation.low_cents, valuation.fair_cents, valuation.high_cents)
    area = listing.district or ("City of Toronto" if listing.city == "Toronto" else listing.city)
    market = area_market(trreb, area)
    rent = cmhc_rent(rents, region, listing.beds_above + listing.beds_below)
    rent_cents = listing.monthly_rent_cents or (rent.rent_cents if rent else None)
    try:  # the finance rules refuse some inputs (down payment under the minimum)
        down = listing.down_payment_cents
        down = minimum_down_payment(asking) if down is None else down
        premium = cmhc_premium(asking, down, listing.amortization_years)
        principal = asking - down + premium
        payment = monthly_payment(principal, listing.mortgage_rate, listing.amortization_years)
        stress = None
        if listing.monthly_income_cents:
            stress = stress_test(principal, listing.mortgage_rate, listing.amortization_years,
                                 listing.monthly_income_cents, listing.monthly_property_tax_cents,
                                 listing.monthly_heat_cents, listing.monthly_debt_cents)

        investor = None if rent_cents is None else investor_view(
            asking, rent_cents, payment, listing.monthly_property_tax_cents,
            listing.monthly_condo_fees_cents)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    notes = []
    # Training sales without coordinates were all in Brampton, so elsewhere a
    # missing location drags the estimate towards Brampton prices.
    if location(listing)[0] is None and listing.city != "Brampton":
        notes.append("No location given, so the model cannot use the strongest feature. "
                     "Pick a neighbourhood (Toronto) for a better estimate.")
    if region not in TRAINED_REGIONS:
        notes.append(f"The model was trained and tested on GTA sales only. Its accuracy in "
                     f"{listing.city} has not been measured.")
    return {
        "valuation": asdict(valuation),
        "verdict": asdict(deal),
        "price_per_sqft_cents": asking // listing.sqft if listing.sqft else None,
        "fair_per_sqft_cents": valuation.fair_cents // listing.sqft if listing.sqft else None,
        "market": {
            "hpi": asdict(hpi_context(hpi, region, HPI_TYPE[listing.property_type])),
            "area": asdict(market) if market else None,
        },
        "costs": {
            "down_payment_cents": down,
            "cmhc_premium_cents": premium,
            "mortgage_cents": principal,
            "monthly_payment_cents": payment,
            "land_transfer_tax_cents": land_transfer_tax(asking, listing.city == "Toronto",
                                                         listing.first_time_buyer),
            "stress_test": asdict(stress) if stress else None,
        },
        "investor": None if investor is None else {
            **asdict(investor),
            "rent_source": "you" if listing.monthly_rent_cents else asdict(rent),
        },
        "red_flags": red_flags(asking, valuation.low_cents, valuation.fair_cents,
                               valuation.high_cents, listing.days_on_market,
                               market.avg_days_on_market if market else None,
                               listing.original_list_cents),
        "notes": notes,
    }
