#!/usr/bin/env python3
"""
Run the preprocessing pipeline over the active dataset:
    load -> validate -> parse timestamps -> drop unusable rows ->
    handle amounts -> flag self-transactions -> deduplicate ->
    sort chronologically -> preserve labels -> save

Usage:
    python scripts/prepare_data.py
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.demo_adapter import DemoAdapter
from src.data.amlsim_adapter import AMLSimAdapter
from src.data.elliptic_adapter import EllipticAdapter
from src.preprocessing.cleaning import DataPreprocessor


def load_active_dataset(config: dict):
    active = config["dataset"]["active"]
    if active == "demo":
        adapter = DemoAdapter(ROOT / config["dataset"]["demo"]["path"])
    elif active == "amlsim":
        adapter = AMLSimAdapter(ROOT / config["dataset"]["amlsim"]["raw_path"])
    elif active == "elliptic":
        adapter = EllipticAdapter(ROOT / config["dataset"]["elliptic"]["raw_path"])
    else:
        raise ValueError(f"Unknown dataset.active='{active}' in config.yaml")
    return active, adapter.load()


def main():
    with open(ROOT / "configs" / "config.yaml") as f:
        config = yaml.safe_load(f)

    active, raw_df = load_active_dataset(config)
    print(f"Loaded '{active}' dataset: {len(raw_df):,} raw rows")

    pre = DataPreprocessor(raw_df, dataset_label=active)
    clean_df, log = pre.run()

    out_dir = ROOT / "data" / "processed"
    result = pre.write(clean_df, log, out_dir)

    print(f"\nPreprocessing steps:")
    for step in log:
        marker = "→" if step.rows_affected == 0 else "⚠"
        print(f"  {marker} {step.step}: {step.rows_before:,} -> {step.rows_after:,} "
              f"(removed {step.rows_affected:,})  | {step.reason[:80]}")

    print(f"\nFinal clean dataset: {len(clean_df):,} rows "
          f"({len(raw_df) - len(clean_df):,} removed of {len(raw_df):,} raw)")
    print(f"Wrote {result['clean_path']}")
    print(f"Wrote {result['log_path']}")


if __name__ == "__main__":
    main()
