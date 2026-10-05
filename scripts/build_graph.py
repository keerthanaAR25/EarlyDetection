#!/usr/bin/env python3
"""
Build temporal graph snapshots (windowed + cumulative) from the
cleaned dataset and write a per-window statistics summary.

Usage:
    python scripts/build_graph.py
"""
import json
import sys
from pathlib import Path

import networkx as nx
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.graph.temporal_graph import TemporalGraphBuilder
from src.graph.graph_ops import snapshot_stats, find_cycles


def main():
    with open(ROOT / "configs" / "config.yaml") as f:
        config = yaml.safe_load(f)

    clean_path = ROOT / "data" / "processed" / "transactions_clean.csv"
    if not clean_path.exists():
        raise FileNotFoundError(f"{clean_path} not found — run scripts/prepare_data.py first.")

    df = pd.read_csv(clean_path, parse_dates=["timestamp"], dtype={"transaction_id": str, "sender": str, "receiver": str, "scenario_id": str, "ring_id": str})
    df["scenario_id"] = df["scenario_id"].fillna("")
    df["ring_id"] = df["ring_id"].fillna("")

    window_size = config["temporal"]["window_size"]
    step_size = config["temporal"]["step_size"]
    print(f"Building snapshots: window_size={window_size} step_size={step_size}")

    builder = TemporalGraphBuilder(df, window_size=window_size, step_size=step_size)
    bounds_list = builder.generate_window_bounds()
    print(f"Time range: {builder.t_min} -> {builder.t_max}")
    print(f"Total windows: {len(bounds_list)}")

    window_summaries = []
    cumulative_summaries = []

    # Incremental cumulative graph growth — rebuilding from scratch per
    # window (the original approach) was found infeasible at real
    # AMLSim scale (Phase 6/19 investigation: ~7s/rebuild x hundreds of
    # windows). Grow one persistent graph instead, exactly like
    # FeatureEngine now does.
    cumulative_G = nx.MultiDiGraph()

    for bounds in bounds_list:
        window_df = df[(df["timestamp"] >= bounds.start) & (df["timestamp"] < bounds.end)]
        Gw = builder._build_graph_from_rows(window_df)
        stats_w = snapshot_stats(Gw)

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
        stats_c = snapshot_stats(cumulative_G)

        window_summaries.append(
            {
                "window_id": bounds.window_id,
                "start": bounds.start.isoformat(),
                "end": bounds.end.isoformat(),
                "n_nodes": stats_w.n_nodes,
                "n_transactions": stats_w.n_edges,
                "total_amount": round(stats_w.total_amount, 2),
                "weakly_connected_components": stats_w.weakly_connected_components,
                "largest_wcc_size": stats_w.largest_wcc_size,
            }
        )
        cumulative_summaries.append(
            {
                "window_id": bounds.window_id,
                "end": bounds.end.isoformat(),
                "cumulative_n_nodes": stats_c.n_nodes,
                "cumulative_n_transactions": stats_c.n_edges,
                "cumulative_density": round(stats_c.density, 6),
            }
        )

    out_dir = ROOT / "reports" / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "graph_window_summary.json", "w") as f:
        json.dump(window_summaries, f, indent=2)
    with open(out_dir / "graph_cumulative_summary.json", "w") as f:
        json.dump(cumulative_summaries, f, indent=2)

    print(f"\nWrote {out_dir / 'graph_window_summary.json'}")
    print(f"Wrote {out_dir / 'graph_cumulative_summary.json'}")

    # after the loop, cumulative_G already equals the full graph — reuse it
    full_G = cumulative_G
    full_stats = snapshot_stats(full_G)
    print(f"\nFull graph: {full_stats.n_nodes} nodes, {full_stats.n_edges} transactions, "
          f"{full_stats.strongly_connected_components} SCCs "
          f"(largest SCC size={full_stats.largest_scc_size})")

    gt_path = ROOT / "data" / "demo" / "ring_ground_truth.json"
    if gt_path.exists() and config["dataset"]["active"] == "demo":
        with open(gt_path) as f:
            ground_truth = json.load(f)
        print(f"\nChecking {len(ground_truth)} demo ring(s) for a detectable cycle "
              f"in their own induced subgraph (NOT the full graph — cycle "
              f"enumeration on the full graph is combinatorially infeasible "
              f"once real background traffic is dense; this is exactly why "
              f"Phase 7's pattern engine will always operate on candidate-scoped "
              f"subgraphs, never the whole network):")
        for ring in ground_truth:
            ring_accounts = set(ring["accounts"])
            sub = full_G.subgraph(ring_accounts)
            cycles = find_cycles(sub, max_length=8)
            print(f"  {ring['ring_id']}: {len(cycles)} cycle(s) found among its "
                  f"{len(ring_accounts)} accounts -> {'YES' if cycles else 'NO'}")


if __name__ == "__main__":
    main()
