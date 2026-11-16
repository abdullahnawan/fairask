"""Train the adjustment model and measure it against the benchmark-only baseline.

The model predicts log(sold / benchmark): how far a house sits from the typical
home of its type, given its features. Fair value is benchmark * exp(prediction).
Two quantile models at the 10th and 90th percentile give the range around it.

How the numbers are measured, because that is what makes them worth quoting:

* **Holdout by location, never at random.** Rows are grouped by district
  (Toronto city district, Brampton community) and split into five folds, so a
  held-out sale is always in a district the model never saw. A random split
  would let the model memorise a street and look better than it is.
* **Every number is out-of-fold.** Each sale is predicted by a model that did
  not train on its district. The five sets of predictions are pooled and scored
  once, so the headline MAE is over all 16,030 sales, not an average of five.
* **No tuning against the holdout.** Parameters are fixed up front. They are
  surely not optimal; they are also not fitted to the test set.
* **The baseline is "every house is worth its benchmark".** The model has to
  beat that, in dollars, or it has learned nothing the HPI did not already say.

The caveats that travel with the results: Toronto sale months are assumed, not
recorded (ml/adjust.py), and Brampton has none of the Toronto-only features.
Accuracy here is GTA accuracy. Nothing has been measured in Waterloo Region.

    python ml/train.py        # writes ml/results/<date>_n<rows>_eval.{json,md}
                              # and ml/models/*.txt (gitignored)
"""

from __future__ import annotations

import json
import zlib
from datetime import date
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap
from sklearn.model_selection import GroupKFold

from dataset import CATEGORICAL, FEATURES, OUTPUT as MODEL_TABLE

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "ml" / "results"
MODELS = REPO / "ml" / "models"

FOLDS = 5
# Fixed before any run and not tuned against the holdout. Small leaves and a
# low rate because 16k rows is not many for a tree ensemble.
PARAMS = dict(
    n_estimators=600,
    learning_rate=0.03,
    num_leaves=31,
    min_child_samples=30,
    subsample=0.8,
    subsample_freq=1,
    colsample_bytree=0.8,
    reg_lambda=1.0,
    random_state=0,
    verbose=-1,
)
QUANTILES = (0.1, 0.9)
COVERAGE = QUANTILES[1] - QUANTILES[0]


def fair_value(benchmark: np.ndarray, log_ratio: np.ndarray) -> np.ndarray:
    """Undo the target: a predicted log ratio back to dollars."""
    return benchmark * np.exp(log_ratio)


def metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    """MAE in dollars, MAPE and median APE as fractions of the sold price."""
    error = np.abs(predicted - actual)
    ape = error / actual
    return {
        "mae": float(error.mean()),
        "mape": float(ape.mean()),
        "median_ape": float(np.median(ape)),
    }


def conformal_margin(y: np.ndarray, low: np.ndarray, high: np.ndarray) -> float:
    """How far to widen [low, high] (log space) so it holds COVERAGE of y.

    Quantile models trained on other districts come out too narrow on a new
    one. Conformalised quantile regression fixes that with one number: the
    COVERAGE quantile of how far each true value fell outside its own range
    (negative when inside). Adding it to both ends restores the promise.
    """
    scores = np.maximum(low - y, y - high)
    level = min(1.0, np.ceil((len(scores) + 1) * COVERAGE) / len(scores))
    return float(np.quantile(scores, level, method="higher"))


def calibrated_coverage(
    y: np.ndarray, low: np.ndarray, high: np.ndarray, districts: pd.Series
) -> float:
    """Coverage after widening, measured honestly: the margin is fitted on one
    half of the districts and scored on the other, then the halves swap."""
    # crc32, not hash(): Python salts str hashes per process, which would make
    # the halves, and so the reported coverage, change on every run.
    half = districts.map(lambda d: zlib.crc32(str(d).encode()) % 2).to_numpy()
    hits = []
    for fit_half in (0, 1):
        fit_rows, score_rows = half == fit_half, half != fit_half
        margin = conformal_margin(y[fit_rows], low[fit_rows], high[fit_rows])
        inside = (low[score_rows] - margin <= y[score_rows]) & (y[score_rows] <= high[score_rows] + margin)
        hits.append(inside)
    return float(np.concatenate(hits).mean())


def features(table: pd.DataFrame) -> pd.DataFrame:
    """The feature frame, with categoricals typed so LightGBM treats them as such."""
    X = table[FEATURES].copy()
    for column in CATEGORICAL:
        X[column] = X[column].astype("category")
    return X


def fit(X: pd.DataFrame, y: pd.Series, **extra) -> lgb.LGBMRegressor:
    return lgb.LGBMRegressor(**PARAMS, **extra).fit(X, y)


def cross_validate(table: pd.DataFrame) -> pd.DataFrame:
    """Out-of-fold predictions for every row: point, p10 and p90, in dollars."""
    X, y = features(table), table["target"]
    out = pd.DataFrame(index=table.index, columns=["pred", "p10", "p90"], dtype=float)
    for train_idx, test_idx in GroupKFold(FOLDS).split(X, y, groups=table["district"]):
        X_train, y_train, X_test = X.iloc[train_idx], y.iloc[train_idx], X.iloc[test_idx]
        benchmark = table["benchmark_then"].to_numpy()[test_idx]
        out.iloc[test_idx, 0] = fair_value(benchmark, fit(X_train, y_train).predict(X_test))
        for column, alpha in zip(("p10", "p90"), QUANTILES):
            model = fit(X_train, y_train, objective="quantile", alpha=alpha)
            out.loc[out.index[test_idx], column] = fair_value(benchmark, model.predict(X_test))
    return out


def evaluate(table: pd.DataFrame, oof: pd.DataFrame) -> dict:
    """Score the pooled out-of-fold predictions against the baseline."""
    actual = table["sold_price"].to_numpy()
    baseline = table["benchmark_then"].to_numpy()
    result = {
        "baseline": metrics(actual, baseline),
        "model": metrics(actual, oof["pred"].to_numpy()),
        "by_source": {},
        "range": {
            "coverage_p10_p90": float(
                ((oof["p10"] <= actual) & (actual <= oof["p90"])).mean()
            ),
            "median_width_share_of_price": float(
                np.median((oof["p90"] - oof["p10"]) / actual)
            ),
        },
    }
    log_actual = table["target"].to_numpy()
    log_low = np.log(oof["p10"].to_numpy() / baseline)
    log_high = np.log(oof["p90"].to_numpy() / baseline)
    result["range"]["coverage_after_calibration"] = calibrated_coverage(
        log_actual, log_low, log_high, table["district"]
    )
    result["range"]["margin_log"] = conformal_margin(log_actual, log_low, log_high)
    for source, rows in table.groupby("source").groups.items():
        rows = np.asarray(rows)
        result["by_source"][source] = {
            "n": int(len(rows)),
            "baseline": metrics(actual[rows], baseline[rows]),
            "model": metrics(actual[rows], oof["pred"].to_numpy()[rows]),
        }
    return result


def explain(model: lgb.LGBMRegressor, X: pd.DataFrame, sample: int = 2000) -> pd.Series:
    """Mean absolute SHAP value per feature, in log-ratio units, on a sample."""
    rows = X.sample(min(sample, len(X)), random_state=0)
    values = shap.TreeExplainer(model).shap_values(rows)
    return pd.Series(np.abs(values).mean(axis=0), index=X.columns).sort_values(ascending=False)


def write_results(table: pd.DataFrame, scores: dict, importance: pd.Series) -> Path:
    stem = f"{date.today():%Y-%m-%d}_n{len(table)}_eval"
    RESULTS.mkdir(exist_ok=True)
    report = {
        "date": f"{date.today():%Y-%m-%d}",
        "rows": int(len(table)),
        "rows_by_source": table["source"].value_counts().to_dict(),
        "holdout": f"GroupKFold({FOLDS}) by district, pooled out-of-fold",
        "features": FEATURES,
        "params": PARAMS,
        "scores": scores,
        "shap_mean_abs": importance.round(4).to_dict(),
        "caveats": [
            "Toronto sale months are assumed to be 2019-06 (ml/adjust.py), not recorded.",
            "Brampton rows lack sqft, coordinates, parking, lot, keywords and year built.",
            "Measured on GTA sales. Nothing here is Waterloo Region accuracy.",
            "Parameters are fixed, not tuned.",
        ],
    }
    (RESULTS / f"{stem}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    def row(name: str, s: dict) -> str:
        return (
            f"| {name} | ${s['baseline']['mae']:,.0f} | {s['baseline']['mape']:.1%} "
            f"| ${s['model']['mae']:,.0f} | {s['model']['mape']:.1%} | {s['model']['median_ape']:.1%} |"
        )

    lines = [
        f"# Evaluation {report['date']}, {report['rows']:,} sales",
        "",
        f"Holdout: {report['holdout']}. Baseline = CREA benchmark for region, type and month.",
        "",
        "| Rows | Baseline MAE | Baseline MAPE | Model MAE | Model MAPE | Model median APE |",
        "|---|---|---|---|---|---|",
        row("All", scores),
        *(row(source, s) for source, s in scores["by_source"].items()),
        "",
        f"Range: the raw p10 to p90 quantile models contain the sold price "
        f"{scores['range']['coverage_p10_p90']:.1%} of the time against a target of "
        f"{COVERAGE:.0%}; median raw width is "
        f"{scores['range']['median_width_share_of_price']:.0%} of the sold price. "
        f"After conformal widening (margin {scores['range']['margin_log']:.3f} in log units, "
        f"fitted on half the districts and scored on the other half) coverage is "
        f"{scores['range']['coverage_after_calibration']:.1%}.",
        "",
        "Top features by mean |SHAP| (log-ratio units):",
        "",
        *(f"- {name}: {value:.3f}" for name, value in importance.head(10).items()),
        "",
        "Caveats:",
        *(f"- {c}" for c in report["caveats"]),
        "",
    ]
    (RESULTS / f"{stem}.md").write_text("\n".join(lines), encoding="utf-8")
    return RESULTS / f"{stem}.md"


def main() -> None:
    if not MODEL_TABLE.exists():
        raise FileNotFoundError(f"{MODEL_TABLE} not found. Run: python ml/dataset.py")
    table = pd.read_csv(MODEL_TABLE)

    oof = cross_validate(table)
    scores = evaluate(table, oof)

    X, y = features(table), table["target"]
    final = fit(X, y)
    importance = explain(final, X)

    MODELS.mkdir(exist_ok=True)
    final.booster_.save_model(MODELS / "adjustment.txt")
    for alpha in QUANTILES:
        fit(X, y, objective="quantile", alpha=alpha).booster_.save_model(
            MODELS / f"quantile_p{int(alpha * 100)}.txt"
        )
    (MODELS / "features.json").write_text(
        json.dumps(
            {
                "features": FEATURES,
                "categories": {c: list(X[c].cat.categories) for c in CATEGORICAL},
                "range_margin_log": scores["range"]["margin_log"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    report = write_results(table, scores, importance)
    print(report.read_text(encoding="utf-8"))
    print(f"models -> {MODELS.relative_to(REPO)}/  results -> {report.relative_to(REPO)}")


if __name__ == "__main__":
    main()
