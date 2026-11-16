"""Why the model values a house the way it does, in dollars.

The model predicts log(fair value / benchmark) as a sum of SHAP values, one per
feature, plus a base value. In log space those add up exactly; in dollars they
multiply, so a single feature cannot be given an exact additive share. Each one
is reported as what it is worth on its own terms:

    dollars = fair_value * (1 - exp(-shap))

"Without this feature's push, the estimate would be this much lower." A positive
number means the feature raised the value. The deal report turns these into
plain language ("+$38k: third bathroom").

    python ml/explain.py        # explains the first sale in the model table
"""

from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap

REPO = Path(__file__).resolve().parent.parent
MODELS = REPO / "ml" / "models"


def load(models: Path = MODELS) -> tuple[lgb.Booster, dict]:
    """The point model and its feature spec, as written by ml/train.py."""
    path = models / "adjustment.txt"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run: python ml/train.py")
    spec = json.loads((models / "features.json").read_text(encoding="utf-8"))
    return lgb.Booster(model_file=str(path)), spec


def prepare(rows: pd.DataFrame, spec: dict) -> pd.DataFrame:
    """Feature frame in training order, categoricals fixed to training levels."""
    X = rows.reindex(columns=spec["features"]).copy()
    for column, levels in spec["categories"].items():
        X[column] = pd.Categorical(X[column], categories=levels)
    return X


def contributions(
    booster: lgb.Booster, X: pd.DataFrame, benchmark: float, top: int = 5
) -> pd.DataFrame:
    """Top features for one listing, largest dollar effect first."""
    if len(X) != 1:
        raise ValueError("explain one listing at a time")
    explainer = shap.TreeExplainer(booster)
    phi = np.asarray(explainer.shap_values(X))[0]
    base = float(np.ravel(explainer.expected_value)[0])
    value = benchmark * np.exp(base + phi.sum())
    out = pd.DataFrame(
        {
            "feature": X.columns,
            "value": X.iloc[0].astype(object).to_numpy(),
            "shap": phi,
            "dollars": value * (1 - np.exp(-phi)),
        }
    )
    out = out[out["shap"] != 0]
    return out.reindex(out["dollars"].abs().sort_values(ascending=False).index).head(top)


def main() -> None:
    from dataset import OUTPUT as MODEL_TABLE

    booster, spec = load()
    row = pd.read_csv(MODEL_TABLE).iloc[[0]]
    benchmark = float(row["benchmark_then"].iloc[0])
    print(
        f"sale {row['mls'].iloc[0]}: sold ${row['sold_price'].iloc[0]:,.0f}, "
        f"benchmark ${benchmark:,.0f}"
    )
    table = contributions(booster, prepare(row, spec), benchmark)
    for _, r in table.iterrows():
        print(f"  {r['dollars']:+12,.0f}  {r['feature']} = {r['value']}")


if __name__ == "__main__":
    main()
