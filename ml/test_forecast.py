"""Tests for the HPI forecast backtest: the features only look backwards, the
baselines do what they say, and a perfectly predictable series scores zero."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from forecast import FEATURES, backtest, examples, log_prices, scores


def hpi(prices: dict[str, list[float]], start: str = "2010-01-01") -> pd.DataFrame:
    months = pd.date_range(start, periods=len(next(iter(prices.values()))), freq="MS")
    return pd.DataFrame([
        {"region": region, "property_type": "Composite", "month": m, "benchmark_price": p}
        for region, series in prices.items() for m, p in zip(months, series)
    ])


def test_features_only_use_the_past() -> None:
    """Changing a price after the origin must not change that origin's features."""
    base = [100.0 + i for i in range(60)]
    later = base[:40] + [999.0] * 20
    a = examples(log_prices(hpi({"A": base})), 3).set_index("month")
    b = examples(log_prices(hpi({"A": later})), 3).set_index("month")
    origin = a.index[a.index < pd.Timestamp("2010-01-01") + pd.DateOffset(months=40)].max()
    assert np.allclose(a.loc[origin, FEATURES].to_numpy(float), b.loc[origin, FEATURES].to_numpy(float))


def test_seasonal_naive_repeats_last_years_change() -> None:
    # Prices rise 10% every March and are flat otherwise.
    prices, p = [], 100.0
    for i in range(48):
        if i % 12 == 2:
            p *= 1.10
        prices.append(p)
    table = examples(log_prices(hpi({"A": prices})), 3)
    row = table[table["month"] == pd.Timestamp("2012-01-01")].iloc[0]
    assert row["last_year"] == pytest.approx(np.log(1.10))
    assert row["target"] == pytest.approx(np.log(1.10))


def test_steady_growth_is_learned_exactly(monkeypatch: pytest.MonkeyPatch) -> None:
    import forecast
    monkeypatch.setattr(forecast, "FIRST_ORIGIN", pd.Timestamp("2013-01-01"))
    # 1% a month, with a little noise so the scaler has variance to work with.
    rng = np.random.default_rng(0)
    prices = 100 * np.exp(np.cumsum(0.01 + rng.normal(0, 1e-4, 72)))
    out = backtest(examples(log_prices(hpi({"A": list(prices), "B": list(prices * 2)})), 3))
    result = scores(out)
    assert result["naive"]["mape"] == pytest.approx(1 - np.exp(-0.03), rel=0.05)  # misses 3 months of growth
    assert result["ridge"]["mape"] < 0.002


def test_training_never_sees_the_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    """If a future target leaked in, a shock right after the origin would be predicted."""
    import forecast
    monkeypatch.setattr(forecast, "FIRST_ORIGIN", pd.Timestamp("2013-01-01"))
    prices = [100.0] * 50 + [200.0] * 22
    out = backtest(examples(log_prices(hpi({"A": prices, "B": prices})), 3))
    before_shock = out[out["month"] == pd.Timestamp("2010-01-01") + pd.DateOffset(months=47)]
    assert (before_shock["ridge"].abs() < 0.05).all()
