"""
Feature column groupings, matching the actual columns produced by
src/features/feature_engine.py. Centralized here so baselines and the
proposed model reference the same definitions rather than each
hard-coding its own column list.
"""

NETWORK_FEATURES = [
    "in_degree", "out_degree", "total_degree", "weighted_in_degree", "weighted_out_degree",
    "degree_ratio_out_in", "pagerank", "betweenness_centrality", "clustering_coefficient",
    "component_size", "neighbor_count", "intermediary_balance_ratio",
]

TRANSACTION_FEATURES = [
    "out_count", "out_amount", "out_amount_mean", "out_amount_median", "out_amount_std",
    "in_count", "in_amount", "in_amount_mean", "in_amount_median", "in_amount_std",
    "unique_receivers", "unique_senders", "repeated_receiver_count", "repeated_sender_count",
    "out_amount_concentration", "total_count", "total_amount", "log_total_amount",
    "amount_ratio_out_in", "unique_counterparties",
]

TEMPORAL_FEATURES = [
    "transaction_velocity", "median_time_gap_seconds", "min_time_gap_seconds", "max_time_gap_seconds",
    "burstiness", "activity_acceleration", "activity_trend_slope", "recent_vs_historical_activity",
    "activity_persistence_windows",
]

DELTA_FEATURES = [
    "delta_total_degree", "delta_weighted_in_degree", "delta_weighted_out_degree", "delta_pagerank",
    "delta_component_size", "delta_neighbor_count", "delta_total_count", "delta_total_amount",
    "delta_transaction_velocity", "delta_connectivity",
]

# Per-account-window indicator of pattern-engine involvement (Phase 7),
# joined on later by src/evaluation/ablation.py. Not part of the base
# feature engine's own output — these come from pattern_events, not
# features.csv — but grouped here so ablation configs can reference a
# single consistent list.
FUND_FLOW_FEATURES = [
    "pattern_fan_in", "pattern_fan_out", "pattern_layering", "pattern_split_merge",
    "pattern_circular_flow", "pattern_repeated_intermediary", "pattern_rapid_pass_through",
    "pattern_escalating_connectivity",
]

ALL_FEATURES = NETWORK_FEATURES + TRANSACTION_FEATURES + TEMPORAL_FEATURES + DELTA_FEATURES


def downcast_numeric(df):
    """Downcast float64 columns to float32 in place — halves memory
    footprint. Found necessary at real-data scale: loading the full
    2.69M-row real feature table at default float64 precision caused
    an OOM kill during model training in this environment's memory
    limit. Precision loss is negligible for these feature magnitudes
    and irrelevant to the classifiers used (tree-based, not sensitive
    to float32 vs float64 rounding)."""
    import pandas as pd
    for col in df.select_dtypes("float64").columns:
        df[col] = df[col].astype("float32")
    return df
