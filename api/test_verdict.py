"""Tests for the verdict: asking price against the fair value range.

Money is in integer cents, as everywhere in the API.
"""

from __future__ import annotations

import pytest

from verdict import Verdict, verdict

# A $1,000,000 estimate with a range of $900,000 to $1,100,000.
LOW, FAIR, HIGH = 900_000_00, 1_000_000_00, 1_100_000_00


@pytest.mark.parametrize(
    ("asking", "label"),
    [
        (850_000_00, "Great deal"),   # below the whole range
        (899_999_99, "Great deal"),
        (900_000_00, "Good"),         # the low end is still inside the range
        (999_999_99, "Good"),         # below the estimate
        (1_000_000_00, "Fair"),       # exactly the estimate
        (1_100_000_00, "Fair"),       # the high end is still inside the range
        (1_100_000_01, "Overpriced"), # above the whole range
    ],
)
def test_label_follows_the_range(asking: int, label: str) -> None:
    assert verdict(asking, LOW, FAIR, HIGH).label == label


def test_gap_is_asking_minus_fair_value() -> None:
    result = verdict(950_000_00, LOW, FAIR, HIGH)
    assert result == Verdict(label="Good", gap_cents=-50_000_00, gap_share=-0.05)


def test_overpriced_gap_is_positive() -> None:
    result = verdict(1_210_000_00, LOW, FAIR, HIGH)
    assert result.gap_cents == 210_000_00
    assert result.gap_share == pytest.approx(0.21)


@pytest.mark.parametrize(
    ("asking", "low", "fair", "high"),
    [
        (0, LOW, FAIR, HIGH),            # no price
        (-1, LOW, FAIR, HIGH),
        (FAIR, FAIR, LOW, HIGH),         # range out of order
        (FAIR, LOW, HIGH, FAIR),
        (FAIR, 0, FAIR, HIGH),           # non-positive estimate
    ],
)
def test_bad_inputs_are_refused(asking: int, low: int, fair: int, high: int) -> None:
    with pytest.raises(ValueError):
        verdict(asking, low, fair, high)


def test_floats_are_refused() -> None:
    """Dollars as floats would pass a sanity check and be wrong by 100x."""
    with pytest.raises(TypeError):
        verdict(1_000_000.0, LOW, FAIR, HIGH)  # type: ignore[arg-type]
