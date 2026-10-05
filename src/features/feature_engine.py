"""
Feature Engine — orchestrates transaction, temporal, network, and
temporal-change features into one per-(account_id, window_id) table.

This is the single entry point everything downstream (pattern
detection, ring candidates, the early-warning model) reads features
from, so no other module should recompute these independently.
"""
from __future__ import annotations

import networkx as nx
import pandas as pd

from src.graph.temporal_graph import TemporalGraphBuilder
from src.features.transaction_features import compute_transaction_features
from src.features.temporal_features import TemporalFeatureComputer
from src.features.network_features import compute_network_features
from src.features.temporal_change_features import compute_temporal_change_features


class FeatureEngine:
    def __init__(
        self,
        df: pd.DataFrame,
        window_size: str = "1d",
        step_size: str = "1d",
        betweenness_sample_k: int | None = None,
    ):
        self.df = df
        self.builder = TemporalGraphBuilder(df, window_size=window_size, step_size=step_size)
        self.all_bounds = self.builder.generate_window_bounds()
        self.betweenness_sample_k = betweenness_sample_k

    def build(self) -> pd.DataFrame:
        per_window_tables = []

        # Grow ONE persistent cumulative graph incrementally, adding each
        # window's own edges once, rather than rebuilding the full
        # cumulative graph from scratch at every window (found necessary
        # at real AMLSim scale: rebuilding from scratch scales as
        # O(windows x total_edges), which measured at 7s per snapshot at
        # window 600 of a 720-window real run — infeasible in aggregate.
        # Incremental growth is O(total_edges) overall, each edge added
        # exactly once across the whole run).
        cumulative_G = nx.MultiDiGraph()
        temporal_computer = TemporalFeatureComputer(self.df)

        import time as _time
        _t_start = _time.time()
        for bounds in self.all_bounds:
            if bounds.window_id % 50 == 0:
                print(f"  [FeatureEngine] window {bounds.window_id}/{len(self.all_bounds)} "
                      f"({_time.time() - _t_start:.0f}s elapsed, {cumulative_G.number_of_nodes()} nodes so far)",
                      flush=True)
            window_df = self.df[(self.df["timestamp"] >= bounds.start) & (self.df["timestamp"] < bounds.end)]
            tx_feat = compute_transaction_features(window_df, bounds.window_id)
            temp_feat = temporal_computer.compute_for_window(
                bounds.window_id, bounds.start, bounds.end, self.all_bounds
            )

            if not window_df.empty:
                cumulative_G.add_nodes_from(pd.concat([window_df["sender"], window_df["receiver"]]).unique())
                new_edges = [
                    (sender, receiver, tx_id, {
                        "transaction_id": tx_id, "amount": amount, "timestamp": timestamp,
                        "label": label, "scenario_id": scenario_id, "ring_id": ring_id,
                    })
                    for sender, receiver, tx_id, amount, timestamp, label, scenario_id, ring_id in zip(
                        window_df["sender"], window_df["receiver"], window_df["transaction_id"],
                        window_df["amount"], window_df["timestamp"], window_df["label"],
                        window_df["scenario_id"], window_df["ring_id"],
                    )
                ]
                cumulative_G.add_edges_from(new_edges)

            net_feat = compute_network_features(cumulative_G, bounds.window_id, betweenness_sample_k=self.betweenness_sample_k)

            merged = net_feat  # network features cover every account seen so far
            if not tx_feat.empty:
                merged = merged.merge(tx_feat, on=["window_id", "account_id"], how="left")
            if not temp_feat.empty:
                merged = merged.merge(temp_feat, on=["window_id", "account_id"], how="left")

            per_window_tables.append(merged)

        full_table = pd.concat(per_window_tables, ignore_index=True) if per_window_tables else pd.DataFrame()
        if full_table.empty:
            return full_table

        # accounts with no transaction activity in a given window (present only
        # because they're structurally in the cumulative graph) get 0s, not NaN,
        # for count/amount columns — they were simply inactive that window.
        zero_fill_cols = [c for c in full_table.columns if c.endswith(("_count", "_amount")) and c != "component_size"]
        full_table[zero_fill_cols] = full_table[zero_fill_cols].fillna(0)

        full_table = compute_temporal_change_features(full_table)
        return full_table
