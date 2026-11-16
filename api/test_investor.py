"""Tests for the investor view. Money is integer cents."""

from __future__ import annotations

import pandas as pd
import pytest

from investor import cmhc_rent, investor_view

RENTS = pd.DataFrame(
    {
        "centre": ["Toronto CMA"] * 4 + ["Kitchener-Cambridge-Waterloo CMA"] * 2,
        "survey": ["2025-10"] * 6,
        "bedrooms": ["Studio", "1 Bedroom", "2 Bedroom", "3 Bedroom +", "Studio", "2 Bedroom"],
        "rent": pd.array([1708, 2073, 2547, 2893, None, 2111], dtype="Int64"),
        "reliability": ["a", "a", "a", "a", None, "a"],
    }
)


class TestRentLookup:
    @pytest.mark.parametrize(("bedrooms", "rent"), [(0, 1708), (1, 2073), (2, 2547), (3, 2893), (5, 2893)])
    def test_bedrooms_map_to_cmhc_groups(self, bedrooms: int, rent: int) -> None:
        assert cmhc_rent(RENTS, "Greater Toronto", bedrooms).rent_cents == rent * 100

    def test_gta_regions_share_the_toronto_cma(self) -> None:
        for region in ("Mississauga", "Oakville-Milton"):
            assert cmhc_rent(RENTS, region, 2).rent_cents == 2547_00

    def test_waterloo_region_uses_kcw(self) -> None:
        rent = cmhc_rent(RENTS, "Cambridge", 2)
        assert (rent.rent_cents, rent.centre, rent.survey) == (2111_00, "Kitchener-Cambridge-Waterloo CMA", "2025-10")

    def test_suppressed_or_unknown_is_none(self) -> None:
        assert cmhc_rent(RENTS, "Kitchener-Waterloo", 0) is None
        assert cmhc_rent(RENTS, "Ottawa", 2) is None


class TestInvestorView:
    def test_yield_and_cash_flow(self) -> None:
        view = investor_view(
            price_cents=600_000_00, rent_cents=2_547_00, mortgage_payment_cents=2_800_00,
            property_tax_cents=300_00, condo_fees_cents=500_00, insurance_cents=50_00,
        )
        assert view.gross_yield == pytest.approx(2_547 * 12 / 600_000)
        assert view.monthly_costs_cents == 3_650_00
        assert view.cash_flow_cents == 2_547_00 - 3_650_00     # negative: costs more than it earns

    def test_maintenance_and_vacancy_come_off_the_rent(self) -> None:
        view = investor_view(
            price_cents=500_000_00, rent_cents=2_000_00, mortgage_payment_cents=1_000_00,
            vacancy_share=0.05, maintenance_share=0.05,
        )
        # 5% + 5% of 2,000 = 200 set aside.
        assert view.cash_flow_cents == 2_000_00 - 1_000_00 - 200_00

    def test_money_must_be_cents(self) -> None:
        with pytest.raises(TypeError):
            investor_view(price_cents=500_000.0, rent_cents=2_000_00, mortgage_payment_cents=0)  # type: ignore[arg-type]

    def test_price_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            investor_view(price_cents=0, rent_cents=2_000_00, mortgage_payment_cents=0)
