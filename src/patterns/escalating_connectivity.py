"""
Escalating connectivity: an account whose connectivity (degree +
neighbor growth) increases for several consecutive windows — read
directly from the Δ-features the feature engine already computes
(Phase 6), rather than recomputing degree changes independently.
"""
from __future__ import annotations

import pandas as pd

from src.patterns.base import PatternEvent


def _maybe_emit(events, account, group, run_start, run_end, min_consecutive_increases, min_total_delta):
    if run_start is not None and (run_end - run_start) >= min_consecutive_increases:
        run = group.iloc[run_start:run_end]
        total_delta = run["delta_connectivity"].fillna(0).sum()
        if total_delta >= min_total_delta:
            strength = min(1.0, total_delta / (min_total_delta * 3))
            events.append(
                PatternEvent(
                    pattern_type="escalating_connectivity",
                    window_id=int(run.iloc[-1]["window_id"]),
                    timestamp=f"window_{int(run.iloc[0]['window_id'])}_to_{int(run.iloc[-1]['window_id'])}",
                    central_account=account,
                    accounts=[account],
                    transaction_ids=[],
                    pattern_strength=round(float(strength), 4),
                    evidence={
                        "n_consecutive_windows": int(run_end - run_start),
                        "total_connectivity_delta": float(total_delta),
                        "start_window": int(run.iloc[0]["window_id"]),
                        "end_window": int(run.iloc[-1]["window_id"]),
                    },
                )
            )
    return None


def detect_escalating_connectivity(
    feature_table: pd.DataFrame,
    min_consecutive_increases: int = 2,
    min_total_delta: float = 3.0,
) -> list[PatternEvent]:
    if feature_table.empty or "delta_connectivity" not in feature_table.columns:
        return []

    events = []
    df = feature_table.sort_values(["account_id", "window_id"])

    for account, group in df.groupby("account_id"):
        group = group.reset_index(drop=True)
        deltas = group["delta_connectivity"].fillna(0).to_numpy()

        run_start = None
        for i, d in enumerate(deltas):
            if d > 0:
                if run_start is None:
                    run_start = i
            else:
                _maybe_emit(events, account, group, run_start, i, min_consecutive_increases, min_total_delta)
                run_start = None
        _maybe_emit(events, account, group, run_start, len(deltas), min_consecutive_increases, min_total_delta)

    return events
