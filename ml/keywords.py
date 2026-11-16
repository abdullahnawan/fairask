"""Keyword features from the free-text description of each Toronto listing.

The structured fields say how many bedrooms a house has, not whether the
basement is finished, whether there is a garage, or whether it was recently
renovated. Agents put those in the description, in a small set of stock
phrases, so a handful of regular expressions recovers them as yes/no flags.

A flag means the phrase appears, nothing more. It cannot tell "renovated
kitchen" from "renovated in 1995", and a flag that is False only means the
agent did not mention it. Both limits are real, and the flags are still worth
having: a finished basement or a garage moves a Toronto price by tens of
thousands of dollars, and nothing else in the data records either.

Year built is handled with the same care. Only an explicit statement such as
"built in 1991" or "circa 1913" becomes a year. "5 years old" is ignored: in
these descriptions it is as often the roof, furnace or fridge as the house.

    python ml/keywords.py        # writes data/processed/toronto_keywords.csv
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
TORONTO_CLEAN = REPO / "data" / "processed" / "toronto_clean.csv"
OUTPUT = REPO / "data" / "processed" / "toronto_keywords.csv"

# flag -> the phrases that set it. Matched case-insensitively.
# shortcut: a mention is taken at face value, so "renovator's dream" is kept
# out but "needs renovation" still reads as renovated. Revisit if the model
# leans on this flag.
FLAGS: dict[str, str] = {
    "basement_finished": (
        r"\bfin(?:ished)?\s+(?:bsmt|basement|lower\s+level|rec\s+room)\b"
        r"|\b(?:bsmt|basement)\s+(?:is\s+)?fin(?:ished)?\b"
    ),
    "basement_apartment": (
        r"\bin-?law\b|\bnanny\b|\b(?:bsmt|basement)\s+apa?r?t(?:ment)?\b"
        r"|\bsep(?:arate|\.)?\s+(?:entrance|entry)\b"
    ),
    "basement_walkout": r"\bwalk-?\s?out\b|\bw/o\s+(?:bsmt|basement)\b",
    "garage": r"\bgarage\b|\bgar\b",
    "renovated": r"\brenov(?!ator)|\breno\b|\bupdated\b|\bupgraded\b|\bremodel",
    "new_build": r"\bbrand\s*new\b|\bnew\s+(?:build|construction|home|house)\b|\bnever\s+lived\b",
    "pool": r"\bpool\b",
    "ravine": r"\bravine\b",
}
_FLAGS = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in FLAGS.items()}

# "built in 1991", "constructed 2005", "circa 1913". Three centuries, because
# Toronto has Victorian housing stock and 2020s builds.
_YEAR = r"((?:18|19|20)\d{2})"
_BUILT = re.compile(
    rf"\b(?:built|constructed)\s+(?:in\s+)?{_YEAR}\b|\bcirca\s+{_YEAR}\b", re.IGNORECASE
)


def flags(text: str) -> dict[str, bool]:
    """One boolean per entry in FLAGS, for a single description."""
    text = str(text)
    return {name: bool(pattern.search(text)) for name, pattern in _FLAGS.items()}


def stated_year_built(text: str) -> int | None:
    """The year an agent explicitly wrote as the build year, or None.

    "Brand new garage built 2018" would wrongly read as the house. There are
    too few such sentences to be worth a parser; the limit is stated here.
    """
    match = _BUILT.search(str(text))
    if not match:
        return None
    return int(match.group(1) or match.group(2))


def keyword_features(sales: pd.DataFrame) -> pd.DataFrame:
    """mls plus one column per flag and year_built_stated."""
    descriptions = sales["description"].fillna("").astype(str)
    out = pd.DataFrame({"mls": sales["mls"].to_numpy()})
    for name, pattern in _FLAGS.items():
        out[name] = descriptions.str.contains(pattern).to_numpy()
    out["year_built_stated"] = descriptions.map(stated_year_built).astype("Int64").to_numpy()
    return out


def main() -> None:
    if not TORONTO_CLEAN.exists():
        raise FileNotFoundError(f"{TORONTO_CLEAN} not found. Run: python ml/toronto.py")

    sales = pd.read_csv(TORONTO_CLEAN)
    features = keyword_features(sales)
    features.to_csv(OUTPUT, index=False)

    print(f"{len(features):,} listings -> {OUTPUT.relative_to(REPO)}\n")
    share = features[list(FLAGS)].mean().sort_values(ascending=False)
    for name, value in share.items():
        print(f"  {name:20} {value:6.1%}")
    print(
        f"\nyear built stated: {features['year_built_stated'].notna().sum():,} "
        f"({features['year_built_stated'].notna().mean():.1%})"
    )


if __name__ == "__main__":
    main()
