#!/usr/bin/env python3
"""
Build the full per-account per-window feature table (transaction +
temporal + network + Δ features) from the cleaned dataset.

Usage:
    python scripts/extract_features.py
"""
import sys
import time
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.features.feature_engine import FeatureEngine


def main():
    with open(ROOT / "configs" / "config.yaml") as f:
        config = yaml.safe_load(f)

    clean_path = ROOT / "data" / "processed" / "transactions_clean.csv"
    if not clean_path.exists():
        raise FileNotFoundError(f"{clean_path} not found — run scripts/prepare_data.py first.")

    df = pd.read_csv(clean_path, parse_dates=["timestamp"])
    df["scenario_id"] = df["scenario_id"].fillna("")
    df["ring_id"] = df["ring_id"].fillna("")

    window_size = config["temporal"]["window_size"]
    step_size = config["temporal"]["step_size"]
    betweenness_k = config.get("performance", {}).get("betweenness_sample_k")

    print(f"Building features: window_size={window_size} step_size={step_size} betweenness_sample_k={betweenness_k}")
    t0 = time.time()
    engine = FeatureEngine(df, window_size=window_size, step_size=step_size, betweenness_sample_k=betweenness_k)
    table = engine.build()
    elapsed = time.time() - t0

    out_path = ROOT / "data" / "processed" / "features.csv"
    table.to_csv(out_path, index=False)

    print(f"Elapsed: {elapsed:.1f}s")
    print(f"Feature table shape: {table.shape[0]:,} rows x {table.shape[1]} columns")
    print(f"Columns: {list(table.columns)}")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
