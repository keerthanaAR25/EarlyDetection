#!/usr/bin/env python3
"""
Train and evaluate the 3 baseline models (static graph anomaly,
behavioural ML, temporal analytical) with a strict chronological
train/val/test split.

Usage:
    python scripts/train_baselines.py
"""
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.graph.temporal_graph import TemporalGraphBuilder
from src.models.labels import build_forecast_labels, attach_labels
from src.models.data_split import chronological_split
from src.models.feature_groups import downcast_numeric
from src.models.baseline_static import StaticGraphAnomalyBaseline
from src.models.baseline_behavioural import BehaviouralMLBaseline
from src.models.baseline_temporal import TemporalAnalyticalBaseline
from src.evaluation.metrics import compute_classification_metrics


def evaluate_split(model, df, split_name, top_k):
    if len(df) == 0:
        return {"note": f"No rows in {split_name} split."}
    scores = model.predict_score(df)
    return compute_classification_metrics(df["y"].to_numpy(), scores, top_k=top_k)


def main():
    with open(ROOT / "configs" / "config.yaml") as f:
        config = yaml.safe_load(f)

    df = pd.read_csv(ROOT / "data" / "processed" / "transactions_clean.csv", parse_dates=["timestamp"], dtype={"transaction_id": str, "sender": str, "receiver": str, "scenario_id": str, "ring_id": str})
    features = downcast_numeric(pd.read_csv(ROOT / "data" / "processed" / "features.csv", dtype={"account_id": str}))

    builder = TemporalGraphBuilder(df, config["temporal"]["window_size"], config["temporal"]["step_size"])
    bounds = builder.generate_window_bounds()
    labels = build_forecast_labels(df, bounds, horizon=config["evaluation"]["forecast_horizon_windows"])
    full = attach_labels(features, labels)

    splits = chronological_split(full, config["split"]["train_fraction"], config["split"]["val_fraction"])
    train_df, val_df, test_df = splits["train"], splits["val"], splits["test"]
    print(f"Train: {len(train_df)} rows ({train_df['y'].sum()} positive), windows {splits['train_window_range']}")
    print(f"Val:   {len(val_df)} rows ({val_df['y'].sum()} positive), windows {splits['val_window_range']}")
    print(f"Test:  {len(test_df)} rows ({test_df['y'].sum()} positive), windows {splits['test_window_range']}")

    top_k = config["evaluation"]["top_k"]
    results = {}

    print("\n--- Baseline 1: Static graph anomaly (Isolation Forest, unsupervised) ---")
    b1 = StaticGraphAnomalyBaseline(random_state=config["project"]["seed"])
    b1.fit(train_df)
    results[b1.name] = {split: evaluate_split(b1, d, split, top_k) for split, d in
                         [("train", train_df), ("val", val_df), ("test", test_df)]}
    print(json.dumps(results[b1.name]["test"], indent=2, default=str))

    print("\n--- Baseline 2: Behavioural ML (Logistic Regression) ---")
    b2 = BehaviouralMLBaseline(random_state=config["project"]["seed"])
    b2.fit(train_df)
    results[b2.name] = {split: evaluate_split(b2, d, split, top_k) for split, d in
                         [("train", train_df), ("val", val_df), ("test", test_df)]}
    print(json.dumps(results[b2.name]["test"], indent=2, default=str))

    print("\n--- Baseline 3: Temporal analytical (Random Forest) ---")
    b3 = TemporalAnalyticalBaseline(random_state=config["project"]["seed"])
    b3.fit(train_df)
    results[b3.name] = {split: evaluate_split(b3, d, split, top_k) for split, d in
                         [("train", train_df), ("val", val_df), ("test", test_df)]}
    print(json.dumps(results[b3.name]["test"], indent=2, default=str))

    out_path = ROOT / "results" / "baseline_metrics.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
