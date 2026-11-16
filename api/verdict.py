"""The verdict: is the asking price a good deal against the fair value range?

The model gives a point estimate and a range (the 10th to 90th percentile,
widened so it holds the real sold price about 80% of the time). The range is
what makes a verdict honest: a house asking 3% over the estimate is well inside
normal error, not overpriced. So the labels are cut by the range, not by a
fixed percentage:

    asking below the range            Great deal
    inside the range, below estimate  Good
    inside the range, at or above     Fair
    asking above the range            Overpriced

All money is integer cents. Floats are refused: a dollar amount passed as a
float would look plausible and be off by a factor of 100.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Verdict:
    label: str
    gap_cents: int      # asking - fair value; negative means asking below fair value
    gap_share: float    # gap as a fraction of fair value


def verdict(asking_cents: int, low_cents: int, fair_cents: int, high_cents: int) -> Verdict:
    values = (asking_cents, low_cents, fair_cents, high_cents)
    if not all(type(v) is int for v in values):
        raise TypeError("money must be integer cents")
    if min(values) <= 0:
        raise ValueError("prices must be positive")
    if not low_cents <= fair_cents <= high_cents:
        raise ValueError("fair value range must satisfy low <= fair <= high")

    if asking_cents < low_cents:
        label = "Great deal"
    elif asking_cents < fair_cents:
        label = "Good"
    elif asking_cents <= high_cents:
        label = "Fair"
    else:
        label = "Overpriced"
    gap = asking_cents - fair_cents
    return Verdict(label=label, gap_cents=gap, gap_share=gap / fair_cents)
