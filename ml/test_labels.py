"""Tests for the hand-label sheet and its scoring."""

from __future__ import annotations

import pandas as pd
import pytest

from keywords import FLAGS
from labels import labelled, make_sheet, score


def sheet(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([{"mls": str(i), "description": "x", **{n: "" for n in FLAGS}, **r}
                         for i, r in enumerate(rows)])


def test_the_sheet_samples_described_listings_with_blank_labels() -> None:
    sales = pd.DataFrame({"mls": range(10), "description": ["has text"] * 8 + ["", None]})
    out = make_sheet(sales, n=5)
    assert len(out) == 5 and out["description"].eq("has text").all()
    assert (out[list(FLAGS)] == "").all().all()


def test_only_fully_labelled_rows_are_scored() -> None:
    done = {n: "0" for n in FLAGS} | {"garage": "1"}
    half = {"garage": "1"}
    out = labelled(sheet([done, half]))
    assert len(out) == 1 and bool(out["garage"].iloc[0]) and not bool(out["pool"].iloc[0])


def test_a_mark_other_than_0_or_1_is_refused() -> None:
    with pytest.raises(ValueError, match="0 or 1"):
        labelled(sheet([{n: "yes" for n in FLAGS}]))


def test_score_counts_every_cell_and_each_features_precision_and_recall() -> None:
    truth = pd.DataFrame({n: [False, False] for n in FLAGS} | {"garage": [True, False]})
    guess = pd.DataFrame({n: [False, False] for n in FLAGS} | {"garage": [True, True]})
    result = score(truth, guess)
    assert result["accuracy"] == pytest.approx(15 / 16)   # one wrong cell out of 2 x 8
    assert result["per_feature"]["garage"] == {"accuracy": 0.5, "precision": 0.5, "recall": 1.0, "positives": 1}
    assert result["per_feature"]["pool"]["precision"] is None
