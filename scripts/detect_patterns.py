#!/usr/bin/env python3
"""
Run all 8 fund-flow pattern detectors over the cleaned dataset and
write results/pattern_events.csv (+ .json for the full evidence).

Usage:
    python scripts/detect_patterns.py
"""
import json
import sys
import time
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.graph.temporal_graph import TemporalGraphBuilder
from src.patterns.pattern_engine import PatternEngine


def main():
    with open(ROOT / "configs" / "config.yaml") as f:
        config = yaml.safe_load(f)

    clean_path = ROOT / "data" / "processed" / "transactions_clean.csv"
    features_path = ROOT / "data" / "processed" / "features.csv"
    if not clean_path.exists():
        raise FileNotFoundError(f"{clean_path} not found — run scripts/prepare_data.py first.")

    df = pd.read_csv(clean_path, parse_dates=["timestamp"])
    df["scenario_id"] = df["scenario_id"].fillna("")
    df["ring_id"] = df["ring_id"].fillna("")

    feature_table = None
    if features_path.exists():
        feature_table = pd.read_csv(features_path)
    else:
        print("Note: features.csv not found — escalating_connectivity detector will be skipped. "
              "Run scripts/extract_features.py first for full coverage.")

    window_size = config["temporal"]["window_size"]
    step_size = config["temporal"]["step_size"]
    builder = TemporalGraphBuilder(df, window_size=window_size, step_size=step_size)
    bounds = builder.generate_window_bounds()

    print("Running pattern engine (8 detectors)...")
    t0 = time.time()
    engine = PatternEngine(df, bounds, config, feature_table=feature_table)
    events = engine.run()
    elapsed = time.time() - t0

    events_df = PatternEngine.events_to_dataframe(events)
    out_dir = ROOT / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    events_df.to_csv(out_dir / "pattern_events.csv", index=False)
    with open(out_dir / "pattern_events.json", "w") as f:
        json.dump([e.to_dict() for e in events], f, indent=2, default=str)

    from collections import Counter
    counts = Counter(e.pattern_type for e in events)

    print(f"Elapsed: {elapsed:.1f}s")
    print(f"Total pattern events: {len(events)}")
    for pt, c in sorted(counts.items()):
        print(f"  {pt}: {c}")
    print(f"\nWrote {out_dir / 'pattern_events.csv'}")
    print(f"Wrote {out_dir / 'pattern_events.json'}")


if __name__ == "__main__":
    main()
