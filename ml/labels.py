"""Hand-labelled listing features: make the sheet, then score extractors on it.

The keyword flags (ml/keywords.py) say a phrase appeared, not that it is true.
To know how often they are right, a person reads real descriptions and marks
each feature yes or no. Those labels are the answer key for any extractor:
the regex flags today, an LLM later.

    python ml/labels.py sheet   # data/private/feature_labels.csv, 100 blank rows
    python ml/labels.py score   # ml/results/<date>_feature_extraction_eval.{json,md}

Fill the sheet with 1 (the listing has it) or 0 (it does not, or it is not
said). The sheet holds listing text, so it stays in data/private and is never
committed; only the overall scores are written to ml/results.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from keywords import FLAGS, TORONTO_CLEAN, flags

REPO = Path(__file__).resolve().parent.parent
SHEET = REPO / "data" / "private" / "feature_labels.csv"
RESULTS = Path(__file__).resolve().parent / "results"
SAMPLE, SEED = 100, 0


def make_sheet(sales: pd.DataFrame, n: int = SAMPLE) -> pd.DataFrame:
    described = sales[sales["description"].fillna("").str.strip() != ""]
    sample = described.sample(n=n, random_state=SEED)[["mls", "description"]]
    return sample.assign(**{name: "" for name in FLAGS})


def labelled(sheet: pd.DataFrame) -> pd.DataFrame:
    """Rows where every feature is marked 0 or 1; refuses anything else."""
    marks = sheet[list(FLAGS)].astype(str).apply(lambda c: c.str.strip())
    done = marks.ne("").all(axis=1) & marks.ne("nan").all(axis=1)
    bad = ~marks[done].isin(["0", "1"]).all(axis=1)
    if bad.any():
        raise ValueError(f"labels must be 0 or 1; check rows {list(sheet.index[done][bad])}")
    return sheet[done].assign(**{name: marks.loc[done, name].eq("1") for name in FLAGS})


def score(truth: pd.DataFrame, predicted: pd.DataFrame) -> dict:
    """Accuracy over every (listing, feature) cell, plus precision and recall per feature."""
    per_feature = {}
    for name in FLAGS:
        t, p = truth[name].to_numpy(bool), predicted[name].to_numpy(bool)
        tp = int((t & p).sum())
        per_feature[name] = {
            "accuracy": float((t == p).mean()),
            "precision": tp / int(p.sum()) if p.any() else None,
            "recall": tp / int(t.sum()) if t.any() else None,
            "positives": int(t.sum()),
        }
    cells = truth[list(FLAGS)].to_numpy(bool) == predicted[list(FLAGS)].to_numpy(bool)
    return {"accuracy": float(cells.mean()), "listings": len(truth), "features": len(FLAGS),
            "per_feature": per_feature}


def regex_predictions(sheet: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([flags(text) for text in sheet["description"]], index=sheet.index)


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "sheet":
        if SHEET.exists():
            raise FileExistsError(f"{SHEET} already exists; it may hold your labels. Move it first.")
        SHEET.parent.mkdir(parents=True, exist_ok=True)
        make_sheet(pd.read_csv(TORONTO_CLEAN)).to_csv(SHEET, index=False)
        print(f"wrote {SAMPLE} blank rows -> {SHEET.relative_to(REPO)}")
    elif command == "score":
        truth = labelled(pd.read_csv(SHEET, dtype=str, keep_default_na=False))
        if truth.empty:
            raise ValueError(f"no fully labelled rows in {SHEET.relative_to(REPO)} yet")
        result = {"date": f"{date.today():%Y-%m-%d}", "regex": score(truth, regex_predictions(truth))}
        stem = f"{result['date']}_feature_extraction_eval"
        (RESULTS / f"{stem}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        r = result["regex"]
        lines = [f"# Listing feature extraction {result['date']}", "",
                 f"{r['features']} features on {r['listings']} hand-labelled Toronto listings.", "",
                 f"Regex keyword flags: {r['accuracy']:.1%} of feature cells correct.", "",
                 "| Feature | Accuracy | Precision | Recall | Listings that have it |", "|---|---|---|---|---|"]
        fmt = lambda v: "n/a" if v is None else f"{v:.0%}"  # noqa: E731
        lines += [f"| {k} | {fmt(v['accuracy'])} | {fmt(v['precision'])} | {fmt(v['recall'])} | {v['positives']} |"
                  for k, v in r["per_feature"].items()]
        (RESULTS / f"{stem}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
    else:
        raise SystemExit("usage: python ml/labels.py sheet|score")


if __name__ == "__main__":
    main()
