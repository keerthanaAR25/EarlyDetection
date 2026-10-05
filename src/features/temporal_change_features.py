"""
Temporal network change features (spec category D).

Given a merged feature table (one row per account_id x window_id,
already containing transaction/temporal/network columns from the
other three modules), compute per-account deltas between consecutive
windows an account was active in. This is the feature category the
research spec calls out as important in its own right: the system
must capture CHANGE OVER TIME, not just static per-window values.

Deltas are computed per-account across CONSECUTIVE windows the
account appears in (not necessarily consecutive window_ids — if an
account is dormant for a window it has no row that window, and the
delta is against its previous active window, which is the correct
leak-safe behaviour: we never interpolate using future information).
"""
from __future__ import annotations

import pandas as pd

# columns from the other three feature modules whose window-to-window
# change is itself informative
_DELTA_SOURCE_COLUMNS = [
    "total_degree",
    "weighted_in_degree",
    "weighted_out_degree",
    "pagerank",
    "component_size",
    "neighbor_count",
    "total_count",       # transaction_features: total transactions this window
    "total_amount",      # transaction_features
    "transaction_velocity",  # temporal_features
]


def compute_temporal_change_features(feature_table: pd.DataFrame) -> pd.DataFrame:
    """
    feature_table: merged output of transaction/temporal/network feature
    modules, must contain 'account_id', 'window_id', and the columns in
    _DELTA_SOURCE_COLUMNS (missing ones are skipped gracefully).
    Returns the same table with 'delta_<col>' columns appended.
    """
    df = feature_table.sort_values(["account_id", "window_id"]).copy()
    available_cols = [c for c in _DELTA_SOURCE_COLUMNS if c in df.columns]

    for col in available_cols:
        df[f"delta_{col}"] = df.groupby("account_id")[col].diff()

    # connectivity change: combines degree + neighbor growth into one summary signal
    if "delta_total_degree" in df.columns and "delta_neighbor_count" in df.columns:
        df["delta_connectivity"] = df["delta_total_degree"].fillna(0) + df["delta_neighbor_count"].fillna(0)

    return df


def compute_graph_level_deltas(window_summaries: list[dict]) -> pd.DataFrame:
    """
    Graph-level (not per-account) deltas: Δdensity, Δtransaction_count,
    Δamount across consecutive windows — from the per-window summaries
    already produced by scripts/build_graph.py's cumulative stats.
    window_summaries: list of dicts with at least 'window_id',
    'cumulative_n_transactions', 'cumulative_density' (see graph_ops output).
    """
    df = pd.DataFrame(window_summaries).sort_values("window_id").copy()
    for col in ["cumulative_n_transactions", "cumulative_density", "cumulative_n_nodes"]:
        if col in df.columns:
            df[f"delta_{col}"] = df[col].diff()
    return df
