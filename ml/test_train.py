"""Tests for the pure parts of training: the metric arithmetic and the inverse
of the target. The model itself is judged by ml/results, not by a unit test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dataset import NEVER_FEATURES
from train import (
    COVERAGE,
    FEATURES,
    PARAMS,
    calibrated_coverage,
    conformal_margin,
    fair_value,
    metrics,
)


class TestMetrics:
    def test_perfect_prediction_scores_zero(self) -> None:
        actual = np.array([500_000.0, 1_000_000.0])
        assert metrics(actual, actual) == {"mae": 0.0, "mape": 0.0, "median_ape": 0.0}

    def test_mae_is_in_dollars_and_mape_is_a_fraction(self) -> None:
        actual = np.array([500_000.0, 1_000_000.0])
        predicted = np.array([550_000.0, 900_000.0])
        out = metrics(actual, predicted)
        assert out["mae"] == pytest.approx(75_000.0)
        assert out["mape"] == pytest.approx((0.10 + 0.10) / 2)
        assert out["median_ape"] == pytest.approx(0.10)

    def test_errors_are_absolute_so_over_and_under_do_not_cancel(self) -> None:
        actual = np.array([100.0, 100.0])
        assert metrics(actual, np.array([150.0, 50.0]))["mae"] == 50.0


class TestFairValue:
    def test_zero_log_ratio_is_the_benchmark(self) -> None:
        assert fair_value(np.array([800_000.0]), np.array([0.0]))[0] == 800_000.0

    def test_log_ratio_round_trips(self) -> None:
        """The target is log(sold / benchmark); fair_value must invert it."""
        benchmark, sold = np.array([800_000.0]), np.array([920_000.0])
        assert fair_value(benchmark, np.log(sold / benchmark))[0] == pytest.approx(920_000.0)


def test_training_cannot_see_a_forbidden_column() -> None:
    assert not set(FEATURES) & NEVER_FEATURES


def test_parameters_are_fixed_not_searched() -> None:
    """The results quote untuned numbers; a seed pins them."""
    assert PARAMS["random_state"] == 0
    assert "n_estimators" in PARAMS


class TestConformal:
    def test_a_range_that_already_covers_needs_no_widening(self) -> None:
        y = np.linspace(-1, 1, 101)
        margin = conformal_margin(y, y - 1.0, y + 1.0)
        assert margin < 0

    def test_a_too_narrow_range_is_widened_to_the_target(self) -> None:
        rng = np.random.default_rng(0)
        y = rng.normal(size=5000)
        low, high = np.full_like(y, -0.2), np.full_like(y, 0.2)
        margin = conformal_margin(y, low, high)
        covered = ((low - margin <= y) & (y <= high + margin)).mean()
        assert COVERAGE <= covered <= COVERAGE + 0.02

    def test_calibrated_coverage_is_scored_out_of_sample(self) -> None:
        rng = np.random.default_rng(1)
        y = rng.normal(size=4000)
        districts = pd.Series(rng.integers(0, 40, size=4000))
        coverage = calibrated_coverage(y, np.full_like(y, -0.1), np.full_like(y, 0.1), districts)
        assert abs(coverage - COVERAGE) < 0.04
