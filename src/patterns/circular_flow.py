"""
Circular flow: A -> B -> ... -> A, where hop timestamps strictly
increase (a real temporal cycle, not just a structural one) and the
whole cycle closes within max_duration_days.

Uses a depth-bounded DFS that only follows edges forward in time —
this is what distinguishes a genuine circular fund flow from two
coincidentally-connected static graph edges.
"""
from __future__ import annotations

import pandas as pd

from src.patterns.base import PatternEvent


def _window_id_for_timestamp(ts: pd.Timestamp, window_bounds: list) -> int:
    for b in window_bounds:
        if b.start <= ts < b.end:
            return b.window_id
    return window_bounds[-1].window_id if window_bounds else 0


def detect_circular_flow(
    df: pd.DataFrame,
    window_bounds: list,
    max_cycle_length: int = 6,
    max_duration_days: float = 7,
    candidate_start_accounts: set | None = None,
    max_branching: int = 5,
) -> list[PatternEvent]:
    """
    candidate_start_accounts: if given, only start the search from
    transactions sent by one of these accounts. Cycle search on a
    dense real-world graph is combinatorially expensive (this bit
    Phase 5's naive full-graph cycle enumeration); scoping starts to
    accounts already flagged as suspicious by other detectors (fan-in
    hubs, layering starts, etc.) keeps this tractable without
    sacrificing the cycles that actually matter for ring evidence.
    max_branching: cap on next-hop candidates explored per DFS node
    (earliest-first) — a documented heuristic bound, not exhaustive
    search, for the same tractability reason.
    """
    if df.empty:
        return []

    df_by_sender = {
        sender: group.sort_values("timestamp")[["timestamp", "receiver", "amount", "transaction_id"]]
        for sender, group in df.groupby("sender")
    }

    events = []
    found_cycles: set = set()

    start_rows = df if candidate_start_accounts is None else df[df["sender"].isin(candidate_start_accounts)]

    for row in start_rows.itertuples(index=False):
        deadline = row.timestamp + pd.Timedelta(days=max_duration_days)
        # DFS stack: (current_account, current_time, path_accounts, path_tx_ids, path_amounts)
        stack = [(row.receiver, row.timestamp, [row.sender, row.receiver], [row.transaction_id], [row.amount])]

        while stack:
            current_account, current_time, path_accounts, path_tx_ids, path_amounts = stack.pop()

            if len(path_accounts) > max_cycle_length:
                continue

            candidates = df_by_sender.get(current_account)
            if candidates is None:
                continue

            next_hops = candidates[(candidates["timestamp"] > current_time) & (candidates["timestamp"] <= deadline)]
            next_hops = next_hops.sort_values("timestamp").head(max_branching)
            for _, nxt in next_hops.iterrows():
                if nxt["receiver"] == row.sender and len(path_accounts) >= 2:
                    # cycle closes back to the start
                    key = tuple(sorted(path_tx_ids + [nxt["transaction_id"]]))
                    if key in found_cycles:
                        continue
                    found_cycles.add(key)

                    all_tx_ids = path_tx_ids + [nxt["transaction_id"]]
                    all_accounts = path_accounts + [row.sender]
                    duration_hours = (nxt["timestamp"] - row.timestamp).total_seconds() / 3600.0
                    strength = min(1.0, 1.0 / len(all_accounts) * 3)  # shorter cycles score higher

                    events.append(
                        PatternEvent(
                            pattern_type="circular_flow",
                            window_id=_window_id_for_timestamp(nxt["timestamp"], window_bounds),
                            timestamp=row.timestamp.isoformat(),
                            central_account=row.sender,
                            accounts=list(dict.fromkeys(all_accounts)),
                            transaction_ids=all_tx_ids,
                            pattern_strength=round(float(strength), 4),
                            evidence={
                                "cycle_length": len(all_accounts) - 1,
                                "duration_hours": float(duration_hours),
                                "start_amount": float(row.amount),
                                "closing_amount": float(nxt["amount"]),
                            },
                        )
                    )
                elif nxt["receiver"] not in path_accounts:
                    # continue the DFS deeper
                    stack.append(
                        (
                            nxt["receiver"],
                            nxt["timestamp"],
                            path_accounts + [nxt["receiver"]],
                            path_tx_ids + [nxt["transaction_id"]],
                            path_amounts + [nxt["amount"]],
                        )
                    )

    return events
