#!/usr/bin/env python3
"""
Run the mandatory 6-configuration ablation study.

Usage:
    python scripts/run_ablation.py
"""
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
from src.features.pattern_indicator_features import build_pattern_indicator_features, attach_pattern_indicators
from src.evaluation.ablation import run_ablation


def main():
    with open(ROOT / "configs" / "config.yaml") as f:
        config = yaml.safe_load(f)

    df = pd.read_csv(ROOT / "data" / "processed" / "transactions_clean.csv", parse_dates=["timestamp"], dtype={"transaction_id": str, "sender": str, "receiver": str, "scenario_id": str, "ring_id": str})
    features = downcast_numeric(pd.read_csv(ROOT / "data" / "processed" / "features.csv", dtype={"account_id": str}))
    pattern_events = pd.read_csv(ROOT / "results" / "pattern_events.csv", dtype={"central_account": str})

    builder = TemporalGraphBuilder(df, config["temporal"]["window_size"], config["temporal"]["step_size"])
    bounds = builder.generate_window_bounds()
    labels = build_forecast_labels(df, bounds, horizon=config["evaluation"]["forecast_horizon_windows"])
    full = attach_labels(features, labels)

    indicator_df = build_pattern_indicator_features(pattern_events)
    full = attach_pattern_indicators(full, indicator_df)
    print(f"Attached pattern indicators: {indicator_df.shape[0]} account-window rows had pattern involvement")

    splits = chronological_split(full, config["split"]["train_fraction"], config["split"]["val_fraction"])
    train_df, test_df = splits["train"], splits["test"]
    print(f"Train: {len(train_df)} rows ({train_df['y'].sum()} positive)")
    print(f"Test:  {len(test_df)} rows ({test_df['y'].sum()} positive)")

    results = run_ablation(train_df, test_df, top_k=config["evaluation"]["top_k"], random_state=config["project"]["seed"])

    print("\nAblation results:")
    print(results.to_string(index=False))

    out_dir = ROOT / "results"
    results.to_csv(out_dir / "ablation_results.csv", index=False)

    reports_dir = ROOT / "reports" / "tables"
    reports_dir.mkdir(parents=True, exist_ok=True)
    results.to_html(reports_dir / "ablation_results.html", index=False)

    print(f"\nWrote {out_dir / 'ablation_results.csv'}")
    print(f"Wrote {reports_dir / 'ablation_results.html'}")


if __name__ == "__main__":
    main()
