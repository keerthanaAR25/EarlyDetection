#!/usr/bin/env python3
"""
Run pattern detectors one at a time, accumulating results in a partial
JSON file. Mirrors scripts/extract_features_chunked.py's checkpoint
approach for the same reason: the full 8-detector set at real AMLSim
scale exceeds a single command's time limit in this environment.

Usage:
    python scripts/detect_patterns_chunked.py --detector fan_in_out
    python scripts/detect_patterns_chunked.py --detector layering
    python scripts/detect_patterns_chunked.py --detector split_merge
    python scripts/detect_patterns_chunked.py --detector rapid_pass_through
    python scripts/detect_patterns_chunked.py --detector repeated_intermediary
    python scripts/detect_patterns_chunked.py --detector circular_flow
    python scripts/detect_patterns_chunked.py --detector escalating_connectivity
    python scripts/detect_patterns_chunked.py --finalize
"""
import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.graph.temporal_graph import TemporalGraphBuilder
from src.patterns.fan_in import detect_fan_in
from src.patterns.fan_out import detect_fan_out
from src.patterns.layering import detect_layering
from src.patterns.split_merge import detect_split_merge
from src.patterns.circular_flow import detect_circular_flow
from src.patterns.repeated_intermediary import detect_repeated_intermediary
from src.patterns.rapid_pass_through import detect_rapid_pass_through
from src.patterns.escalating_connectivity import detect_escalating_connectivity
from src.patterns.pattern_engine import PatternEngine

PARTIAL_DIR = ROOT / "results" / "_pattern_chunks"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--detector", type=str, default=None)
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()

    with open(ROOT / "configs" / "config.yaml") as f:
        config = yaml.safe_load(f)
    pcfg = config.get("patterns", {})

    if args.finalize:
        _finalize()
        return

    df = pd.read_csv(ROOT / "data" / "processed" / "transactions_clean.csv", parse_dates=["timestamp"], dtype={"transaction_id": str, "sender": str, "receiver": str, "scenario_id": str, "ring_id": str})
    df["scenario_id"] = df["scenario_id"].fillna("")
    df["ring_id"] = df["ring_id"].fillna("")

    builder = TemporalGraphBuilder(df, config["temporal"]["window_size"], config["temporal"]["step_size"])
    bounds = builder.generate_window_bounds()

    PARTIAL_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    events = []

    if args.detector == "fan_in_out":
        fan_in_cfg = pcfg.get("fan_in", {})
        fan_out_cfg = pcfg.get("fan_out", {})
        for b in bounds:
            window_df = df[(df["timestamp"] >= b.start) & (df["timestamp"] < b.end)]
            events += detect_fan_in(window_df, b.window_id, min_senders=fan_in_cfg.get("min_senders", 4))
            events += detect_fan_out(window_df, b.window_id, min_receivers=fan_out_cfg.get("min_receivers", 4))

    elif args.detector == "layering":
        cfg = pcfg.get("layering", {})
        events = detect_layering(
            df, bounds, min_hops=cfg.get("min_hops", 3), max_hops=cfg.get("max_hops", 6),
            max_hop_gap_hours=PatternEngine._hours(cfg.get("max_hop_gap_hours", 24)),
        )

    elif args.detector == "split_merge":
        cfg = pcfg.get("split_merge", {})
        events = detect_split_merge(df, bounds, max_time_window=cfg.get("max_time_window", "2d"))

    elif args.detector == "rapid_pass_through":
        cfg = pcfg.get("rapid_pass_through", {})
        events = detect_rapid_pass_through(df, bounds, max_hold_time_hours=cfg.get("max_hold_time_hours", 6))

    elif args.detector == "repeated_intermediary":
        rpt_cfg = pcfg.get("rapid_pass_through", {})
        ri_cfg = pcfg.get("repeated_intermediary", {})
        events = detect_repeated_intermediary(
            df, bounds, max_hold_time_hours=rpt_cfg.get("max_hold_time_hours", 6),
            min_pass_through_count=ri_cfg.get("min_pass_through_count", 3),
        )

    elif args.detector == "circular_flow":
        candidate_accounts = set()
        for f in PARTIAL_DIR.glob("*.json"):
            with open(f) as fh:
                for e in json.load(fh):
                    candidate_accounts.update(e["accounts"])
        cfg = pcfg.get("circular_flow", {})
        events = detect_circular_flow(
            df, bounds, max_cycle_length=cfg.get("max_cycle_length", 6),
            max_duration_days=cfg.get("max_duration_days", 7),
            candidate_start_accounts=candidate_accounts if candidate_accounts else None,
        )

    elif args.detector == "escalating_connectivity":
        features_path = ROOT / "data" / "processed" / "features.csv"
        feature_table = pd.read_csv(features_path) if features_path.exists() else None
        events = detect_escalating_connectivity(feature_table) if feature_table is not None else []

    else:
        raise ValueError(f"Unknown detector '{args.detector}'")

    elapsed = time.time() - t0
    print(f"{args.detector}: {len(events)} events in {elapsed:.1f}s")

    with open(PARTIAL_DIR / f"{args.detector}.json", "w") as f:
        json.dump([e.to_dict() for e in events], f, default=str)
    print(f"Saved to {PARTIAL_DIR / (args.detector + '.json')}")


def _finalize():
    all_events = []
    for f in sorted(PARTIAL_DIR.glob("*.json")):
        with open(f) as fh:
            all_events.extend(json.load(fh))

    out_dir = ROOT / "results"
    with open(out_dir / "pattern_events.json", "w") as f:
        json.dump(all_events, f, indent=2, default=str)
    pd.DataFrame(all_events).to_csv(out_dir / "pattern_events.csv", index=False)

    from collections import Counter
    counts = Counter(e["pattern_type"] for e in all_events)
    print(f"FINALIZED: {len(all_events)} total pattern events")
    for pt, c in sorted(counts.items()):
        print(f"  {pt}: {c}")
    print(f"Wrote {out_dir / 'pattern_events.json'}")
    print(f"Wrote {out_dir / 'pattern_events.csv'}")


if __name__ == "__main__":
    main()
