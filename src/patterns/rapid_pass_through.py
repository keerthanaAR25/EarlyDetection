
"""
Rapid pass-through: an account receives funds and forwards them again
within max_hold_time_hours — the "mule account" signature.

Implementation note (found necessary at real-data scale and with
real-data timestamp granularity):
  - The original per-row Python loop took 68s on 197,905 real
    transactions and — more importantly — found ZERO events, because
    this dataset's timestamps are daily-only (verified in the dataset
    audit: every transaction sits at exactly 00:00:00). A same-day
    in/out pair has IDENTICAL timestamps, which a strict `out > in`
    comparison always excludes; a next-day pair is already a 24-hour
    gap, at or beyond any sub-day threshold. The detector was
    structurally blind at this granularity, not just slow.
  - Rewritten with pd.merge_asof (vectorized, C-level nearest-match
    join) instead of a per-row Python loop, and `allow_exact_matches=True`
    so a same-calendar-day in/out pair counts as a valid candidate —
    the correct reading of "rapid" when intra-day ordering isn't
    observable in the source data. This is a documented interpretation
    for daily-granularity data, not an assumption that would hold at
    finer granularity (the demo dataset, with sub-day jitter, is
    unaffected and continues to use `max_hold_time_hours` as originally
    designed).
"""
from __future__ import annotations

import pandas as pd

from src.patterns.base import PatternEvent


def _window_id_for_timestamp(ts: pd.Timestamp, window_bounds: list) -> int:
    for b in window_bounds:
        if b.start <= ts < b.end:
            return b.window_id
    return window_bounds[-1].window_id if window_bounds else 0


def detect_rapid_pass_through(
    df: pd.DataFrame,
    window_bounds: list,
    max_hold_time_hours: float = 6,
) -> list[PatternEvent]:
    if df.empty:
        return []

    incoming = df[["receiver", "sender", "amount", "timestamp", "transaction_id"]].rename(
        columns={"receiver": "account", "sender": "in_sender", "amount": "in_amount",
                  "timestamp": "in_timestamp", "transaction_id": "in_tx_id"}
    ).sort_values("in_timestamp")

    outgoing = df[["sender", "receiver", "amount", "timestamp", "transaction_id"]].rename(
        columns={"sender": "account", "receiver": "out_receiver", "amount": "out_amount",
                  "timestamp": "out_timestamp", "transaction_id": "out_tx_id"}
    ).sort_values("out_timestamp")

    matched = pd.merge_asof(
        incoming, outgoing,
        left_on="in_timestamp", right_on="out_timestamp", by="account",
        direction="forward", allow_exact_matches=True,
        tolerance=pd.Timedelta(hours=max_hold_time_hours),
    )
    matched = matched.dropna(subset=["out_tx_id"])
    # merge_asof's nearest-forward match can pair the SAME transaction with
    # itself if an account both sends and receives in one row (shouldn't
    # happen given schema, but guard explicitly) or pair an incoming leg
    # with an outgoing leg that is actually an unrelated earlier transfer
    # reused across multiple incoming rows — dedupe to the first incoming
    # match per (account, out_tx_id) pair to avoid double-counting one
    # outgoing transaction as the destination of several incoming ones.
    matched = matched[matched["in_tx_id"] != matched["out_tx_id"]]
    matched = matched.drop_duplicates(subset=["account", "out_tx_id"], keep="first")

    events = []
    for row in matched.itertuples(index=False):
        hold_time_hours = (row.out_timestamp - row.in_timestamp).total_seconds() / 3600.0
        strength = max(0.0, min(1.0, 1 - hold_time_hours / max(max_hold_time_hours, 1e-9)))
        events.append(
            PatternEvent(
                pattern_type="rapid_pass_through",
                window_id=_window_id_for_timestamp(row.out_timestamp, window_bounds),
                timestamp=row.in_timestamp.isoformat(),
                central_account=row.account,
                accounts=[row.in_sender, row.account, row.out_receiver],
                transaction_ids=[row.in_tx_id, row.out_tx_id],
                pattern_strength=round(float(strength), 4),
                evidence={
                    "hold_time_hours": float(hold_time_hours),
                    "in_amount": float(row.in_amount),
                    "out_amount": float(row.out_amount),
                    "amount_retention_ratio": float(row.out_amount / row.in_amount) if row.in_amount else 0.0,
                },
            )
        )
    return events
