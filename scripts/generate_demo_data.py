#!/usr/bin/env python3
"""
Generate the synthetic DEMO dataset so the pipeline can run without
AMLSim or Elliptic first.

Usage:
    python scripts/generate_demo_data.py
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.demo_generator import DemoDataGenerator  # noqa: E402


def main():
    config_path = ROOT / "configs" / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    seed = config.get("project", {}).get("seed", 42)
    out_dir = ROOT / config.get("dataset", {}).get("demo", {}).get("path", "data/demo")

    gen = DemoDataGenerator(
        n_normal_accounts=150,
        n_rings=6,
        simulation_days=30,
        normal_tx_per_day=60,
        seed=seed,
    )
    df, ground_truth = gen.write(out_dir)

    print(f"Wrote {len(df):,} transactions to {out_dir}/transactions.csv")
    print(f"Embedded {len(ground_truth)} ring scenario(s):")
    for g in ground_truth:
        print(f"  {g['ring_id']}: {len(g['accounts'])} accounts, "
              f"observable_time={g['observable_time']} "
              f"stages={[s['stage_name'] for s in g['stages']]}")
    print(f"\nGround truth: {out_dir}/ring_ground_truth.json")
    print(f"Account list: {out_dir}/accounts.csv")
    print("\nThis is DEMO / SYNTHETIC data — see data/demo/README.md")


if __name__ == "__main__":
    main()
