#!/usr/bin/env python3
"""
Checkpointed feature extraction for real-data scale runs.

A single command in this environment has a hard time limit, and true
background processes were found not to persist across separate tool
invocations here — so for a 720-window real AMLSim run (verified to
take several minutes even after the FeatureEngine optimizations),
this script processes a bounded chunk of windows per invocation,
saves progress, and resumes on the next call. Re-run it repeatedly
until it reports "COMPLETE".

Usage:
    python scripts/extract_features_chunked.py [--chunk-size 80]
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
from src.features.transaction_features import compute_transaction_features
from src.features.temporal_features import TemporalFeatureComputer
from src.features.network_features import compute_network_features
from src.features.temporal_change_features import compute_temporal_change_features

CHECKPOINT_PATH = ROOT / "data" / "processed" / "_feature_extraction_checkpoint.json"
PARTIAL_PATH = ROOT / "data" / "processed" / "_feature_extraction_partial.csv"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunk-size", type=int, default=80)
    args = parser.parse_args()

    with open(ROOT / "configs" / "config.yaml") as f:
        config = yaml.safe_load(f)

    df = pd.read_csv(ROOT / "data" / "processed" / "transactions_clean.csv", parse_dates=["timestamp"], dtype={"transaction_id": str, "sender": str, "receiver": str, "scenario_id": str, "ring_id": str})
    df["scenario_id"] = df["scenario_id"].fillna("")
    df["ring_id"] = df["ring_id"].fillna("")

    builder = TemporalGraphBuilder(df, config["temporal"]["window_size"], config["temporal"]["step_size"])
    all_bounds = builder.generate_window_bounds()
    betweenness_k = config.get("performance", {}).get("betweenness_sample_k")

    checkpoint = {"last_completed_window": -1}
    if CHECKPOINT_PATH.exists():
        with open(CHECKPOINT_PATH) as f:
            checkpoint = json.load(f)

    start_window = checkpoint["last_completed_window"] + 1
    if start_window >= len(all_bounds):
        print("COMPLETE: all windows already processed.")
        _finalize()
        return

    end_window = min(start_window + args.chunk_size, len(all_bounds))
    print(f"Resuming from window {start_window}, processing through window {end_window - 1} "
          f"(of {len(all_bounds)} total)")

    t0 = time.time()
    history_df = df[df["timestamp"] < all_bounds[start_window].start] if start_window > 0 else df.iloc[0:0]
    cumulative_G = builder._build_graph_from_rows(history_df)
    temporal_computer = TemporalFeatureComputer(df)
    print(f"  Rebuilt state for resume in {time.time() - t0:.1f}s "
          f"({cumulative_G.number_of_nodes()} nodes, {cumulative_G.number_of_edges()} edges)")

    per_window_tables = []
    t_chunk_start = time.time()
    for bounds in all_bounds[start_window:end_window]:
        window_df = df[(df["timestamp"] >= bounds.start) & (df["timestamp"] < bounds.end)]

        tx_feat = compute_transaction_features(window_df, bounds.window_id)
        temp_feat = temporal_computer.compute_for_window(bounds.window_id, bounds.start, bounds.end, all_bounds)

        if not window_df.empty:
            cumulative_G.add_nodes_from(pd.concat([window_df["sender"], window_df["receiver"]]).unique())
            new_edges = [
                (s, r, tid, {"transaction_id": tid, "amount": a, "timestamp": t, "label": l, "scenario_id": sc, "ring_id": rid})
                for s, r, tid, a, t, l, sc, rid in zip(
                    window_df["sender"], window_df["receiver"], window_df["transaction_id"], window_df["amount"],
                    window_df["timestamp"], window_df["label"], window_df["scenario_id"], window_df["ring_id"],
                )
            ]
            cumulative_G.add_edges_from(new_edges)

        net_feat = compute_network_features(cumulative_G, bounds.window_id, betweenness_sample_k=betweenness_k)

        merged = net_feat
        if not tx_feat.empty:
            merged = merged.merge(tx_feat, on=["window_id", "account_id"], how="left")
        if not temp_feat.empty:
            merged = merged.merge(temp_feat, on=["window_id", "account_id"], how="left")
        per_window_tables.append(merged)

        if bounds.window_id % 20 == 0:
            print(f"    window {bounds.window_id} done ({time.time() - t_chunk_start:.0f}s into this chunk)", flush=True)

    chunk_table = pd.concat(per_window_tables, ignore_index=True) if per_window_tables else pd.DataFrame()

    if PARTIAL_PATH.exists():
        chunk_table.to_csv(PARTIAL_PATH, mode="a", header=False, index=False)
    else:
        chunk_table.to_csv(PARTIAL_PATH, index=False)

    checkpoint["last_completed_window"] = end_window - 1
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump(checkpoint, f)

    elapsed = time.time() - t_chunk_start
    print(f"Chunk done in {elapsed:.1f}s. Checkpoint saved at window {end_window - 1}.")

    if end_window >= len(all_bounds):
        print("COMPLETE: all windows processed.")
        _finalize()
    else:
        print(f"Run again to continue from window {end_window}.")


def _finalize():
    full_table = pd.read_csv(PARTIAL_PATH)
    zero_fill_cols = [c for c in full_table.columns if c.endswith(("_count", "_amount")) and c != "component_size"]
    full_table[zero_fill_cols] = full_table[zero_fill_cols].fillna(0)
    full_table = compute_temporal_change_features(full_table)

    out_path = ROOT / "data" / "processed" / "features.csv"
    full_table.to_csv(out_path, index=False)
    print(f"Final feature table: {full_table.shape[0]:,} rows x {full_table.shape[1]} columns")
    print(f"Wrote {out_path}")

    CHECKPOINT_PATH.unlink(missing_ok=True)
    PARTIAL_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
