"""Fan-out: one sender -> many distinct receivers within a short window."""
from __future__ import annotations

import pandas as pd

from src.patterns.base import PatternEvent


def detect_fan_out(window_df: pd.DataFrame, window_id: int, min_receivers: int = 4) -> list[PatternEvent]:
    events = []
    if window_df.empty:
        return events

    grouped = window_df.groupby("sender")
    for sender, group in grouped:
        receivers = group["receiver"].unique()
        if len(receivers) < min_receivers:
            continue

        amounts = group["amount"]
        strength = min(1.0, len(receivers) / (min_receivers * 2))

        events.append(
            PatternEvent(
                pattern_type="fan_out",
                window_id=window_id,
                timestamp=group["timestamp"].min().isoformat(),
                central_account=sender,
                accounts=[sender] + list(receivers),
                transaction_ids=list(group["transaction_id"]),
                pattern_strength=round(float(strength), 4),
                evidence={
                    "n_receivers": int(len(receivers)),
                    "total_amount": float(amounts.sum()),
                    "mean_amount": float(amounts.mean()),
                    "amount_std": float(amounts.std()) if len(amounts) > 1 else 0.0,
                    "time_span_seconds": float((group["timestamp"].max() - group["timestamp"].min()).total_seconds()),
                },
            )
        )
    return events
