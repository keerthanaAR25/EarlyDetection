"""
Layering: A -> B -> C -> D ... where each hop follows the previous one
quickly (within max_hop_gap_hours) and moves roughly the same amount
onward (within amount_tolerance) — the classic "rapid pass-through
chain" signature, as opposed to two unrelated transactions that happen
to share an account.

Approach: greedy chain extension from every transaction — at each hop,
follow the EARLIEST qualifying onward transaction from the current
receiver. This is a documented approximation (not exhaustive search
over all branching paths, which would be combinatorially expensive on
dense graphs); it reliably finds a chain when one exists, which is
sufficient for a flagging/evidence system, but a more exhaustive
search could find additional or longer alternative chains.

Chains are deduplicated: transactions already consumed by a chain
found from an earlier start are skipped, so one underlying flow
doesn't emit an event once per hop.
"""
from __future__ import annotations

import pandas as pd

from src.patterns.base import PatternEvent


def _window_id_for_timestamp(ts: pd.Timestamp, window_bounds: list) -> int:
    for b in window_bounds:
        if b.start <= ts < b.end:
            return b.window_id
    return window_bounds[-1].window_id if window_bounds else 0


def _extend_chain(df_by_sender: dict, start_row, max_hops: int, max_hop_gap_hours: float, amount_tolerance: float):
    chain_accounts = [start_row.sender, start_row.receiver]
    chain_tx_ids = [start_row.transaction_id]
    chain_amounts = [start_row.amount]
    chain_times = [start_row.timestamp]

    current_account = start_row.receiver
    current_amount = start_row.amount
    current_time = start_row.timestamp

    for _ in range(max_hops - 1):
        candidates = df_by_sender.get(current_account)
        if candidates is None or candidates.empty:
            break

        gap_limit = current_time + pd.Timedelta(hours=max_hop_gap_hours)
        eligible = candidates[
            (candidates["timestamp"] > current_time)
            & (candidates["timestamp"] <= gap_limit)
            & (candidates["amount"] >= current_amount * (1 - amount_tolerance))
            & (candidates["amount"] <= current_amount * 1.05)
            & (~candidates["receiver"].isin(chain_accounts))
        ]
        if eligible.empty:
            break

        nxt = eligible.iloc[0]
        chain_accounts.append(nxt["receiver"])
        chain_tx_ids.append(nxt["transaction_id"])
        chain_amounts.append(nxt["amount"])
        chain_times.append(nxt["timestamp"])
        current_account, current_amount, current_time = nxt["receiver"], nxt["amount"], nxt["timestamp"]

    return chain_accounts, chain_tx_ids, chain_amounts, chain_times


def detect_layering(
    df: pd.DataFrame,
    window_bounds: list,
    min_hops: int = 3,
    max_hops: int = 6,
    max_hop_gap_hours: float = 24,
    amount_tolerance: float = 0.3,
) -> list[PatternEvent]:
    if df.empty:
        return []

    df_by_sender = {
        sender: group.sort_values("timestamp")[["timestamp", "receiver", "amount", "transaction_id"]]
        for sender, group in df.groupby("sender")
    }

    events = []
    used_tx_ids: set = set()

    for row in df.itertuples(index=False):
        if row.transaction_id in used_tx_ids:
            continue

        accounts, tx_ids, amounts, times = _extend_chain(
            df_by_sender, row, max_hops, max_hop_gap_hours, amount_tolerance
        )
        n_hops = len(tx_ids)
        if n_hops < min_hops:
            continue

        used_tx_ids.update(tx_ids)
        strength = min(1.0, (n_hops - min_hops + 1) / (max_hops - min_hops + 1))

        events.append(
            PatternEvent(
                pattern_type="layering",
                window_id=_window_id_for_timestamp(times[-1], window_bounds),
                timestamp=times[0].isoformat(),
                central_account=accounts[0],
                accounts=accounts,
                transaction_ids=tx_ids,
                pattern_strength=round(float(strength), 4),
                evidence={
                    "n_hops": n_hops,
                    "start_amount": float(amounts[0]),
                    "end_amount": float(amounts[-1]),
                    "amount_retention_ratio": float(amounts[-1] / amounts[0]) if amounts[0] else 0.0,
                    "total_duration_hours": float((times[-1] - times[0]).total_seconds() / 3600.0),
                },
            )
        )

    return events
