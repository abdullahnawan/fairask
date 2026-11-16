"""Tests for the cost-to-own maths. Money is integer cents.

Expected values are worked by hand from the published rules (sources in
api/finance.py), not taken from running the code.
"""

from __future__ import annotations

import pytest

from finance import (
    cmhc_premium,
    land_transfer_tax,
    minimum_down_payment,
    monthly_payment,
    ontario_ltt,
    qualifying_rate,
    stress_test,
    toronto_mltt,
)

DOLLAR = 100


class TestLandTransferTax:
    @pytest.mark.parametrize(
        ("price", "tax"),
        [
            (55_000, 275),            # 0.5% band only
            (250_000, 2_225),         # 275 + 1,950
            (368_000, 3_995),         # where the first-time refund covers it all
            (500_000, 6_475),         # 275 + 1,950 + 2,250 + 2,000
            (1_000_000, 16_475),
            (2_500_000, 48_975),      # 36,475 + 2.5% of 500,000
        ],
    )
    def test_ontario_brackets_are_marginal(self, price: int, tax: int) -> None:
        assert ontario_ltt(price * DOLLAR) == tax * DOLLAR

    def test_ontario_first_time_refund_is_capped_at_4000(self) -> None:
        assert ontario_ltt(368_000 * DOLLAR, first_time=True) == 0
        assert ontario_ltt(500_000 * DOLLAR, first_time=True) == (6_475 - 4_000) * DOLLAR

    def test_toronto_matches_ontario_up_to_3_million(self) -> None:
        for price in (300_000, 1_000_000, 3_000_000):
            assert toronto_mltt(price * DOLLAR) == ontario_ltt(price * DOLLAR)

    def test_toronto_luxury_bands_from_april_2026(self) -> None:
        # Up to $3M: 61,475. Then 4.40% of the next $500,000 = 22,000.
        assert toronto_mltt(3_500_000 * DOLLAR) == 83_475 * DOLLAR
        # 61,475 + 44,000 + 54,500 + 5.45%... up to $5M, then 6.50% of $1M.
        assert toronto_mltt(6_000_000 * DOLLAR) == (61_475 + 44_000 + 54_500 + 65_000) * DOLLAR

    def test_toronto_first_time_rebate_is_capped_at_4475(self) -> None:
        assert toronto_mltt(1_000_000 * DOLLAR, first_time=True) == (16_475 - 4_475) * DOLLAR

    def test_toronto_buyer_pays_both(self) -> None:
        """The well-known figure: $32,950 on a $1M Toronto home, $24,475 for a first-time buyer."""
        assert land_transfer_tax(1_000_000 * DOLLAR, in_toronto=True) == 32_950 * DOLLAR
        assert land_transfer_tax(1_000_000 * DOLLAR, in_toronto=True, first_time=True) == 24_475 * DOLLAR
        assert land_transfer_tax(1_000_000 * DOLLAR, in_toronto=False) == 16_475 * DOLLAR


class TestDownPaymentAndInsurance:
    @pytest.mark.parametrize(
        ("price", "minimum"),
        [
            (400_000, 20_000),        # 5%
            (500_000, 25_000),
            (600_000, 35_000),        # 5% of 500k + 10% of 100k
            (1_499_999, 124_999.9),   # still the tiered rule
            (1_500_000, 300_000),     # 20% from $1.5M
        ],
    )
    def test_minimum_down_payment(self, price: int, minimum: float) -> None:
        assert minimum_down_payment(price * DOLLAR) == round(minimum * DOLLAR)

    def test_premium_by_loan_to_value(self) -> None:
        # 5% down on $500k: loan 475,000 at 95% LTV, 4.00%.
        assert cmhc_premium(500_000 * DOLLAR, 25_000 * DOLLAR) == 19_000 * DOLLAR
        # 10% down: loan 450,000 at 90% LTV, 3.10%.
        assert cmhc_premium(500_000 * DOLLAR, 50_000 * DOLLAR) == 13_950 * DOLLAR
        # 15% down: loan 425,000 at 85% LTV, 2.80%.
        assert cmhc_premium(500_000 * DOLLAR, 75_000 * DOLLAR) == 11_900 * DOLLAR

    def test_no_premium_at_20_percent_down(self) -> None:
        assert cmhc_premium(500_000 * DOLLAR, 100_000 * DOLLAR) == 0

    def test_30_year_amortization_adds_020(self) -> None:
        assert cmhc_premium(500_000 * DOLLAR, 25_000 * DOLLAR, amortization_years=30) == 19_950 * DOLLAR

    def test_insured_amortization_over_30_years_is_refused(self) -> None:
        with pytest.raises(ValueError, match="30 years"):
            cmhc_premium(500_000 * DOLLAR, 25_000 * DOLLAR, amortization_years=35)
        # Uninsured at 20% down: any amortization the lender agrees to.
        assert cmhc_premium(500_000 * DOLLAR, 100_000 * DOLLAR, amortization_years=35) == 0

    def test_below_minimum_down_is_refused(self) -> None:
        with pytest.raises(ValueError, match="minimum down payment"):
            cmhc_premium(600_000 * DOLLAR, 30_000 * DOLLAR)


class TestMortgage:
    def test_payment_uses_semi_annual_compounding(self) -> None:
        """$500,000 at 5% over 25 years is $2,908.02 in Canada (monthly
        compounding would give $2,922.95)."""
        assert monthly_payment(500_000 * DOLLAR, 0.05, 25) == 2_908_02

    def test_zero_rate_is_straight_division(self) -> None:
        assert monthly_payment(300_000 * DOLLAR, 0.0, 25) == 1_000 * DOLLAR

    @pytest.mark.parametrize(("contract", "qualifying"), [(0.0299, 0.0525), (0.0325, 0.0525), (0.0479, 0.0679)])
    def test_qualifying_rate_is_the_greater_of_floor_or_plus_2(self, contract: float, qualifying: float) -> None:
        assert qualifying_rate(contract) == pytest.approx(qualifying)

    def test_stress_test_uses_the_qualifying_payment(self) -> None:
        result = stress_test(
            principal_cents=500_000 * DOLLAR, contract_rate=0.0525, amortization_years=25,
            monthly_income_cents=12_000 * DOLLAR, monthly_property_tax_cents=400 * DOLLAR,
            monthly_heat_cents=100 * DOLLAR, monthly_debt_cents=500 * DOLLAR,
        )
        assert result.qualifying_rate == pytest.approx(0.0725)
        assert result.qualifying_payment_cents == 3_579_59
        assert result.gds == pytest.approx((3_579.59 + 400 + 100) / 12_000)
        assert result.tds == pytest.approx((3_579.59 + 400 + 100 + 500) / 12_000)
        assert result.passes  # GDS 34.0% <= 39%, TDS 38.2% <= 44%

    def test_stress_test_fails_on_low_income(self) -> None:
        result = stress_test(500_000 * DOLLAR, 0.0525, 25, 8_000 * DOLLAR, 400 * DOLLAR, 100 * DOLLAR)
        assert not result.passes


def test_money_must_be_integer_cents() -> None:
    with pytest.raises(TypeError):
        ontario_ltt(500_000.0)  # type: ignore[arg-type]
