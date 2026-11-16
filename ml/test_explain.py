"""Tests for per-listing explanations, on a small model trained here so they run
without the real data or saved models."""

from __future__ import annotations

import json

import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest
import shap

from explain import contributions, load, prepare


@pytest.fixture(scope="module")
def model(tmp_path_factory) -> tuple[lgb.Booster, dict]:
    """Price premium driven by baths only; 'noise' carries nothing."""
    rng = np.random.default_rng(0)
    X = pd.DataFrame({"baths": rng.integers(1, 5, 2000), "noise": rng.normal(size=2000)})
    y = 0.1 * (X["baths"] - 2)
    booster = lgb.LGBMRegressor(n_estimators=50, verbose=-1).fit(X, y).booster_
    folder = tmp_path_factory.mktemp("models")
    booster.save_model(folder / "adjustment.txt")
    spec = {"features": ["baths", "noise"], "categories": {}}
    (folder / "features.json").write_text(json.dumps(spec), encoding="utf-8")
    return load(folder)


def test_extra_bathrooms_explain_a_premium_in_dollars(model) -> None:
    booster, spec = model
    X = prepare(pd.DataFrame({"baths": [4], "noise": [0.0]}), spec)
    out = contributions(booster, X, benchmark=1_000_000)
    assert out.iloc[0]["feature"] == "baths"
    assert out.iloc[0]["dollars"] > 0


def test_shap_values_add_up_to_the_prediction(model) -> None:
    """The log-space contributions must reconstruct what the model predicts."""
    booster, spec = model
    X = prepare(pd.DataFrame({"baths": [1], "noise": [0.3]}), spec)
    explainer = shap.TreeExplainer(booster)
    total = np.asarray(explainer.shap_values(X))[0].sum() + np.ravel(explainer.expected_value)[0]
    assert total == pytest.approx(booster.predict(X)[0], abs=1e-6)


def test_one_listing_at_a_time(model) -> None:
    booster, spec = model
    X = prepare(pd.DataFrame({"baths": [1, 2], "noise": [0.0, 0.0]}), spec)
    with pytest.raises(ValueError):
        contributions(booster, X, benchmark=1)


def test_missing_model_says_how_to_make_it(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="train.py"):
        load(tmp_path)
