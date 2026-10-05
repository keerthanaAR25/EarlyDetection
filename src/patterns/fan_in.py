"""Fan-in: many distinct senders -> one receiver within a short window."""
from __future__ import annotations

import pandas as pd

from src.patterns.base import PatternEvent


def detect_fan_in(window_df: pd.DataFrame, window_id: int, min_senders: int = 4) -> list[PatternEvent]:
    events = []
    if window_df.empty:
        return events

    grouped = window_df.groupby("receiver")
    for receiver, group in grouped:
        senders = group["sender"].unique()
        if len(senders) < min_senders:
            continue

        amounts = group["amount"]
        strength = min(1.0, len(senders) / (min_senders * 2))  # saturates at 2x threshold

        events.append(
            PatternEvent(
                pattern_type="fan_in",
                window_id=window_id,
                timestamp=group["timestamp"].min().isoformat(),
                central_account=receiver,
                accounts=[receiver] + list(senders),
                transaction_ids=list(group["transaction_id"]),
                pattern_strength=round(float(strength), 4),
                evidence={
                    "n_senders": int(len(senders)),
                    "total_amount": float(amounts.sum()),
                    "mean_amount": float(amounts.mean()),
                    "amount_std": float(amounts.std()) if len(amounts) > 1 else 0.0,
                    "time_span_seconds": float((group["timestamp"].max() - group["timestamp"].min()).total_seconds()),
                },
            )
        )
    return events
