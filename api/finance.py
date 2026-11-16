"""Cost-to-own maths for an Ontario home purchase: land transfer tax, minimum
down payment, CMHC insurance, the mortgage payment and the stress test.

Money is integer cents throughout. Tax brackets and premiums are applied with
Decimal and rounded half-up to the cent once, at the end, so no float error
reaches a dollar figure. Interest rates are plain fractions (0.05 is 5%).

Rules as published, checked 2026-11-16:

* **Ontario LTT** (ontario.ca, "Calculating land transfer tax"): marginal
  brackets, 2.5% band for land with one or two single-family residences.
  First-time buyer refund up to $4,000 ("Land transfer tax refunds for
  first-time homebuyers").
* **Toronto MLTT** (toronto.ca, "MLTT rates and fees"): the Ontario brackets
  to $3M, then 4.40% / 5.45% / 6.50% / 7.55% / 8.60% bands effective
  1 April 2026. First-time purchaser rebate up to $4,475 ("MLTT rebate
  opportunities"). The page calls the rates graduated; they are applied
  marginally, like the provincial ones they mirror.
* **Minimum down payment** (canada.ca, FCAC "Down payment"): 5% of the first
  $500,000, 10% of the rest up to $1.5M, 20% from $1.5M. Below 20% down the
  mortgage must be insured, and insurance stops at a $1.5M price (raised from
  $1M on 15 Dec 2024; the FCAC page still carries the old $1M line).
* **CMHC premiums** (cmhc-schl.gc.ca, "Premium information for homeowner and
  small rental loans"): by loan-to-value, 2.80% to 85%, 3.10% to 90%, 4.00% to
  95%, plus 0.20% for amortization beyond 25 years.
* **Canadian fixed-rate payments** compound semi-annually (Interest Act), so the
  monthly rate is (1 + r/2)^(1/6) - 1, not r/12.
* **Stress test** (OSFI B-20 minimum qualifying rate): the greater of the
  contract rate + 2% or 5.25%. Debt service limits GDS 39% and TDS 44% are
  CMHC's for insured loans; lenders use the same numbers for most others.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# Upper bound in dollars (None = no limit) -> marginal rate.
Brackets = tuple[tuple[int | None, str], ...]

ONTARIO_LTT: Brackets = (
    (55_000, "0.005"), (250_000, "0.01"), (400_000, "0.015"), (2_000_000, "0.02"), (None, "0.025"),
)
TORONTO_MLTT: Brackets = (
    (55_000, "0.005"), (250_000, "0.01"), (400_000, "0.015"), (2_000_000, "0.02"),
    (3_000_000, "0.025"), (4_000_000, "0.044"), (5_000_000, "0.0545"),
    (10_000_000, "0.065"), (20_000_000, "0.0755"), (None, "0.086"),
)
ONTARIO_FIRST_TIME_REFUND_CENTS = 4_000_00
TORONTO_FIRST_TIME_REBATE_CENTS = 4_475_00

INSURED_PRICE_LIMIT_CENTS = 1_500_000_00
# Highest loan-to-value -> premium on the loan. Above 80% LTV only: at 20% down
# or more insurance is not required, so no premium is charged.
CMHC_PREMIUMS = ((Decimal("0.85"), Decimal("0.028")), (Decimal("0.90"), Decimal("0.031")),
                 (Decimal("0.95"), Decimal("0.04")))
LONG_AMORTIZATION_SURCHARGE = Decimal("0.002")
# 30 years only for first-time buyers and new builds; 25 for everyone else.
MAX_INSURED_AMORTIZATION = 30

QUALIFYING_FLOOR = 0.0525
QUALIFYING_BUFFER = 0.02
GDS_LIMIT, TDS_LIMIT = 0.39, 0.44


def _cents(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _require_cents(*values: int) -> None:
    if not all(type(v) is int for v in values):
        raise TypeError("money must be integer cents")
    if min(values) < 0:
        raise ValueError("money cannot be negative")


def _bracket_tax(price_cents: int, brackets: Brackets) -> int:
    tax, lower = Decimal(0), 0
    for upper, rate in brackets:
        top = price_cents if upper is None else min(price_cents, upper * 100)
        if top > lower:
            tax += (top - lower) * Decimal(rate)
        if upper is None or price_cents <= upper * 100:
            break
        lower = upper * 100
    return _cents(tax)


def ontario_ltt(price_cents: int, first_time: bool = False) -> int:
    _require_cents(price_cents)
    tax = _bracket_tax(price_cents, ONTARIO_LTT)
    return max(0, tax - ONTARIO_FIRST_TIME_REFUND_CENTS) if first_time else tax


def toronto_mltt(price_cents: int, first_time: bool = False) -> int:
    _require_cents(price_cents)
    tax = _bracket_tax(price_cents, TORONTO_MLTT)
    return max(0, tax - TORONTO_FIRST_TIME_REBATE_CENTS) if first_time else tax


def land_transfer_tax(price_cents: int, in_toronto: bool, first_time: bool = False) -> int:
    """Everything a buyer pays on closing: Ontario's tax, plus Toronto's inside the city."""
    tax = ontario_ltt(price_cents, first_time)
    return tax + toronto_mltt(price_cents, first_time) if in_toronto else tax


def minimum_down_payment(price_cents: int) -> int:
    _require_cents(price_cents)
    if price_cents >= INSURED_PRICE_LIMIT_CENTS:
        return _cents(price_cents * Decimal("0.20"))
    first = min(price_cents, 500_000_00)
    return _cents(first * Decimal("0.05") + (price_cents - first) * Decimal("0.10"))


def cmhc_premium(price_cents: int, down_cents: int, amortization_years: int = 25) -> int:
    """Insurance premium added to the mortgage; 0 at 20% down or more."""
    _require_cents(price_cents, down_cents)
    if down_cents < minimum_down_payment(price_cents):
        raise ValueError("down payment is below the minimum down payment for this price")
    loan = price_cents - down_cents
    ltv = Decimal(loan) / Decimal(price_cents)
    if ltv <= Decimal("0.80"):
        return 0
    if amortization_years > MAX_INSURED_AMORTIZATION:
        raise ValueError(f"insured mortgages cannot be amortized over {MAX_INSURED_AMORTIZATION} years")
    rate = next(premium for limit, premium in CMHC_PREMIUMS if ltv <= limit)
    if amortization_years > 25:
        rate += LONG_AMORTIZATION_SURCHARGE
    return _cents(loan * rate)


def monthly_payment(principal_cents: int, annual_rate: float, amortization_years: int) -> int:
    """Blended monthly payment on a Canadian fixed-rate mortgage."""
    _require_cents(principal_cents)
    n = amortization_years * 12
    if annual_rate == 0:
        return _cents(Decimal(principal_cents) / n)
    i = (1 + annual_rate / 2) ** (1 / 6) - 1
    return _cents(Decimal(principal_cents * i / (1 - (1 + i) ** -n)))


def qualifying_rate(contract_rate: float) -> float:
    return max(contract_rate + QUALIFYING_BUFFER, QUALIFYING_FLOOR)


@dataclass(frozen=True)
class StressTest:
    qualifying_rate: float
    qualifying_payment_cents: int
    gds: float   # housing costs / gross income
    tds: float   # housing costs + other debts / gross income
    passes: bool


def stress_test(
    principal_cents: int,
    contract_rate: float,
    amortization_years: int,
    monthly_income_cents: int,
    monthly_property_tax_cents: int,
    monthly_heat_cents: int,
    monthly_debt_cents: int = 0,
) -> StressTest:
    """Would a lender approve this mortgage at the qualifying rate?

    principal_cents is the whole loan, including any CMHC premium added to it.
    """
    _require_cents(monthly_income_cents, monthly_property_tax_cents, monthly_heat_cents, monthly_debt_cents)
    if monthly_income_cents == 0:
        raise ValueError("income must be positive")
    rate = qualifying_rate(contract_rate)
    payment = monthly_payment(principal_cents, rate, amortization_years)
    housing = payment + monthly_property_tax_cents + monthly_heat_cents
    gds = housing / monthly_income_cents
    tds = (housing + monthly_debt_cents) / monthly_income_cents
    return StressTest(rate, payment, gds, tds, passes=gds <= GDS_LIMIT and tds <= TDS_LIMIT)
