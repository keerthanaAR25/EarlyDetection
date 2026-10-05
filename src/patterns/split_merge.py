"""
Split-merge: A splits funds to >=2 accounts (B, C, ...), which later
send funds on to a common destination D within max_time_window of the
split — the classic diamond shape used to break up a large transfer
into smaller, less conspicuous pieces before recombining it.

Implementation note: the original merge-candidate lookup re-scanned
the ENTIRE dataframe (`df[df["sender"].isin(split_targets) & ...]`)
inside a loop running once per (sender, anchor-transaction) pair —
at real-data scale (197,905 rows, thousands of active senders) this
did not finish within this environment's time limit. Rewritten to
pre-group transactions by sender ONCE (a dict lookup, same pattern
used in layering.py and circular_flow.py) so each merge-candidate
lookup is a handful of dict lookups + small-frame filters instead of
a full-dataframe scan.
"""
from __future__ import annotations

import pandas as pd

from src.patterns.base import PatternEvent
from src.graph.temporal_graph import _parse_offset


def detect_split_merge(df: pd.DataFrame, window_bounds: list, max_time_window: str = "2d") -> list[PatternEvent]:
    if df.empty:
        return []

    window_td = _parse_offset(max_time_window)
    events = []

    df_by_sender = {sender: group.sort_values("timestamp") for sender, group in df.groupby("sender")}

    for sender, split_group in df_by_sender.items():
        for i in range(len(split_group)):
            anchor_time = split_group.iloc[i]["timestamp"]
            window_rows = split_group[
                (split_group["timestamp"] >= anchor_time) & (split_group["timestamp"] < anchor_time + window_td)
            ]
            split_targets = window_rows["receiver"].unique()
            if len(split_targets) < 2:
                continue

            # merge-candidate lookup: only the (few) split targets' own
            # transaction frames, not the whole dataset
            merge_frames = [df_by_sender[t] for t in split_targets if t in df_by_sender]
            if not merge_frames:
                continue
            candidates_all = pd.concat(merge_frames, ignore_index=True)
            merge_candidates = candidates_all[
                (candidates_all["timestamp"] >= anchor_time) & (candidates_all["timestamp"] < anchor_time + window_td * 2)
            ]
            if merge_candidates.empty:
                continue

            merge_by_dest = merge_candidates.groupby("receiver")["sender"].nunique()
            merged_destinations = merge_by_dest[merge_by_dest >= 2]
            if merged_destinations.empty:
                continue

            dest = merged_destinations.idxmax()
            merge_rows = merge_candidates[merge_candidates["receiver"] == dest]

            all_tx_ids = list(window_rows["transaction_id"]) + list(merge_rows["transaction_id"])
            all_accounts = [sender] + list(split_targets) + [dest]
            strength = min(1.0, len(split_targets) / 4.0)

            events.append(
                PatternEvent(
                    pattern_type="split_merge",
                    window_id=_first_matching_window(anchor_time, window_bounds),
                    timestamp=anchor_time.isoformat(),
                    central_account=sender,
                    accounts=list(dict.fromkeys(all_accounts)),
                    transaction_ids=list(dict.fromkeys(all_tx_ids)),
                    pattern_strength=round(float(strength), 4),
                    evidence={
                        "split_targets": list(split_targets),
                        "merge_destination": dest,
                        "n_split_paths": int(len(split_targets)),
                    },
                )
            )
            break  # one split-merge event per (sender, anchor cluster) is enough

    return events


def _first_matching_window(ts: pd.Timestamp, window_bounds: list) -> int:
    for b in window_bounds:
        if b.start <= ts < b.end:
            return b.window_id
    return window_bounds[-1].window_id if window_bounds else 0
