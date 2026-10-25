"""Train the ranking model, compare it with the rule-based baseline, and save the artifacts.

Usage: python -m smart_reconcile_ml.train --data data/generated/v1 --out models/latest
"""

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from .dataset import build_groups
from .feedback import load_feedback_groups
from .generator import load
from .matching import FEATURES, baseline_score

PARAMS = {
    "objective": "lambdarank",
    "metric": "map",
    "eval_at": [1, 3],
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_data_in_leaf": 20,
    "feature_fraction": 0.9,
    "lambdarank_truncation_level": 10,
    "verbose": -1,
    "seed": 7,
}
THRESHOLD = 0.8


def _sorted(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(["line_id"], kind="stable").reset_index(drop=True)


def _dataset(df: pd.DataFrame) -> lgb.Dataset:
    groups = df.groupby("line_id", sort=False).size().to_numpy()
    return lgb.Dataset(
        df[FEATURES].to_numpy(float),
        label=df["label"].to_numpy(),
        group=groups,
        feature_name=FEATURES,
        free_raw_data=False,
    )


def ranking_metrics(df: pd.DataFrame, score_col: str, lines: pd.DataFrame) -> dict:
    """Top-1, Top-3 and MRR over matched lines. Lines whose true set is not a candidate count as misses."""
    ranked = df.assign(rank=df.groupby("line_id")[score_col].rank(ascending=False, method="first"))
    true_rank = ranked[ranked["label"] == 1].set_index("line_id")["rank"]
    matched = lines[lines["has_match"]]
    r = matched["line_id"].map(true_rank)
    return {
        "top1": float((r == 1).mean()),
        "top3": float((r <= 3).mean()),
        "mrr": float((1 / r).fillna(0).mean()),
        "n_lines": int(len(matched)),
    }


def top_summary(df: pd.DataFrame, lines: pd.DataFrame) -> pd.DataFrame:
    """Per line: top score, margin to the second, and whether the top candidate is right."""
    out = []
    for line_id, g in df.groupby("line_id", sort=False):
        s = g["score"].to_numpy()
        order = np.argsort(-s)
        out.append(
            {
                "line_id": line_id,
                "top": s[order[0]],
                "margin": s[order[0]] - s[order[1]] if len(s) > 1 else 5.0,
                "correct": int(g["label"].to_numpy()[order[0]] == 1),
            }
        )
    out = pd.DataFrame(out)
    no_cands = lines.loc[~lines["line_id"].isin(out["line_id"]), ["line_id"]]
    return out, no_cands


def train(data_dir: Path, out: Path, feedback_dir: Path | None = None, rounds: int = 1000) -> dict:
    cache = data_dir / "candidates.parquet"
    if cache.exists():
        cands, lines = pd.read_parquet(cache), pd.read_parquet(data_dir / "lines.parquet")
    else:
        cands, lines = build_groups(load(data_dir))
        cands.to_parquet(cache)
        lines.to_parquet(data_dir / "lines.parquet")
    cands = cands.merge(lines[["line_id", "split"]], on="line_id")
    has_pos = cands.groupby("line_id")["label"].transform("max") == 1

    train_df = _sorted(cands[(cands["split"] == "train") & has_pos])
    n_feedback = 0
    if feedback_dir:
        fb = load_feedback_groups(feedback_dir, start_id=int(cands["line_id"].max()) + 1)
        n_feedback = fb["line_id"].nunique() if len(fb) else 0
        train_df = _sorted(pd.concat([train_df, fb], ignore_index=True)) if n_feedback else train_df
    valid_df = _sorted(cands[(cands["split"] == "valid") & has_pos])
    booster = lgb.train(
        PARAMS,
        _dataset(train_df),
        num_boost_round=rounds,
        valid_sets=[_dataset(valid_df)],
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )

    results = {}
    for split in ("valid", "test"):
        df = cands[cands["split"] == split].copy()
        df["score"] = booster.predict(df[FEATURES].to_numpy(float), num_iteration=booster.best_iteration)
        df["baseline"] = [baseline_score(r) for r in df[FEATURES].to_dict("records")]
        split_lines = lines[lines["split"] == split]
        results[split] = {
            "model": ranking_metrics(df, "score", split_lines),
            "baseline": ranking_metrics(df, "baseline", split_lines),
            "candidate_recall": float(split_lines.loc[split_lines["has_match"], "found"].mean()),
        }
        results[split]["by_kind"] = {
            kind: {"model": ranking_metrics(df, "score", kl), "baseline": ranking_metrics(df, "baseline", kl)}
            for kind, kl in split_lines[split_lines["has_match"]].groupby("kind")
        }
        results[split]["_scored"] = df

    # Confidence: logistic regression on (top score, margin), fitted on validation lines, unmatched included.
    tops, _ = top_summary(results["valid"]["_scored"], lines[lines["split"] == "valid"])
    calib = LogisticRegression().fit(tops[["top", "margin"]], tops["correct"])
    calibration = {"intercept": float(calib.intercept_[0]), "coef": [float(c) for c in calib.coef_[0]]}

    test_tops, no_cands = top_summary(results["test"]["_scored"], lines[lines["split"] == "test"])
    test_tops["confidence"] = calib.predict_proba(test_tops[["top", "margin"]])[:, 1]
    n_test_lines = len(test_tops) + len(no_cands)
    above = test_tops[test_tops["confidence"] >= THRESHOLD]
    results["test"]["threshold"] = {
        "threshold": THRESHOLD,
        "coverage": float(len(above) / n_test_lines),
        "precision": float(above["correct"].mean()) if len(above) else 0.0,
    }
    for split in ("valid", "test"):
        del results[split]["_scored"]

    importance = dict(zip(FEATURES, booster.feature_importance("gain").round(1).tolist(), strict=True))
    version = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(out / "model.txt"), num_iteration=booster.best_iteration)
    meta = {
        "version": version,
        "features": FEATURES,
        "calibration": calibration,
        "params": PARAMS,
        "best_iteration": booster.best_iteration,
        "feedback_lines": int(n_feedback),
        "metrics": results,
        "feature_importance_gain": importance,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    _log_mlflow(meta, out)
    return meta


def _log_mlflow(meta: dict, out: Path) -> None:
    """Log to MLflow when it is installed. Tracking URI comes from MLFLOW_TRACKING_URI."""
    try:
        import mlflow
    except ImportError:
        return
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db"))
    mlflow.set_experiment("smart-reconcile")
    with mlflow.start_run(run_name=meta["version"]):
        mlflow.log_params({k: str(v) for k, v in meta["params"].items()})
        mlflow.log_param("best_iteration", meta["best_iteration"])
        for split in ("valid", "test"):
            for who in ("model", "baseline"):
                for k, v in meta["metrics"][split][who].items():
                    mlflow.log_metric(f"{split}_{who}_{k}", v)
        for k, v in meta["metrics"]["test"]["threshold"].items():
            mlflow.log_metric(f"test_threshold_{k}", v)
        mlflow.log_artifact(str(out / "meta.json"))
        import lightgbm as lgb
        import mlflow.lightgbm

        mlflow.lightgbm.log_model(
            lgb.Booster(model_file=str(out / "model.txt")), name="model", registered_model_name="smart-reconcile-ranker"
        )


def print_report(meta: dict) -> None:
    t = meta["metrics"]["test"]
    print(f"\nTest set ({t['model']['n_lines']} matched lines), candidate recall {t['candidate_recall']:.3f}")
    print(f"{'':10}{'Top-1':>8}{'Top-3':>8}{'MRR':>8}")
    for who in ("baseline", "model"):
        m = t[who]
        print(f"{who:10}{m['top1']:8.3f}{m['top3']:8.3f}{m['mrr']:8.3f}")
    for kind, v in t["by_kind"].items():
        print(
            f"  {kind:9} n={v['model']['n_lines']:4}  baseline top1 {v['baseline']['top1']:.3f}  "
            f"model top1 {v['model']['top1']:.3f}"
        )
    th = t["threshold"]
    print(
        f"Confidence >= {th['threshold']}: coverage {th['coverage']:.3f} of all lines, precision {th['precision']:.3f}"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/generated/v1"))
    parser.add_argument("--out", type=Path, default=Path("models/latest"))
    parser.add_argument("--feedback", type=Path, default=None, help="directory of feedback files from the service")
    args = parser.parse_args(argv)
    print_report(train(args.data, args.out, args.feedback))


if __name__ == "__main__":
    main()
