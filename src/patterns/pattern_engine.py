"""
Pattern Engine — orchestrates all 8 fund-flow pattern detectors.

Fan-in and fan-out run per-window (they're inherently short-timeframe
signals). Layering, split-merge, and circular-flow run over the full
timeline once (they span multiple windows/hops by nature) and are
bucketed back into windows by their closing timestamp. Repeated
intermediary and rapid pass-through run over the full timeline.
Escalating connectivity reads the Phase 6 feature table directly.

Circular-flow search is scoped to accounts already flagged by the
other detectors (fan-in/fan-out/layering central accounts) — running
unscoped temporal-cycle search against dense real-world background
traffic is combinatorially expensive (this project already hit that
exact wall once, in Phase 5's naive full-graph cycle check).
"""
from __future__ import annotations

import pandas as pd

from src.patterns.fan_in import detect_fan_in
from src.patterns.fan_out import detect_fan_out
from src.patterns.layering import detect_layering
from src.patterns.split_merge import detect_split_merge
from src.patterns.circular_flow import detect_circular_flow
from src.patterns.repeated_intermediary import detect_repeated_intermediary
from src.patterns.rapid_pass_through import detect_rapid_pass_through
from src.patterns.escalating_connectivity import detect_escalating_connectivity


class PatternEngine:
    def __init__(self, df: pd.DataFrame, window_bounds: list, config: dict, feature_table: pd.DataFrame | None = None):
        self.df = df
        self.window_bounds = window_bounds
        self.config = config.get("patterns", {})
        self.feature_table = feature_table

    def run(self) -> list:
        events = []

        fan_in_cfg = self.config.get("fan_in", {})
        fan_out_cfg = self.config.get("fan_out", {})
        for bounds in self.window_bounds:
            window_df = self.df[(self.df["timestamp"] >= bounds.start) & (self.df["timestamp"] < bounds.end)]
            events += detect_fan_in(window_df, bounds.window_id, min_senders=fan_in_cfg.get("min_senders", 4))
            events += detect_fan_out(window_df, bounds.window_id, min_receivers=fan_out_cfg.get("min_receivers", 4))

        layering_cfg = self.config.get("layering", {})
        events += detect_layering(
            self.df,
            self.window_bounds,
            min_hops=layering_cfg.get("min_hops", 3),
            max_hops=layering_cfg.get("max_hops", 6),
            max_hop_gap_hours=self._hours(layering_cfg.get("max_hop_gap_hours", 24)),
        )

        split_merge_cfg = self.config.get("split_merge", {})
        events += detect_split_merge(
            self.df, self.window_bounds, max_time_window=split_merge_cfg.get("max_time_window", "2d")
        )

        rpt_cfg = self.config.get("rapid_pass_through", {})
        events += detect_rapid_pass_through(
            self.df, self.window_bounds, max_hold_time_hours=rpt_cfg.get("max_hold_time_hours", 6)
        )

        ri_cfg = self.config.get("repeated_intermediary", {})
        events += detect_repeated_intermediary(
            self.df,
            self.window_bounds,
            max_hold_time_hours=rpt_cfg.get("max_hold_time_hours", 6),
            min_pass_through_count=ri_cfg.get("min_pass_through_count", 3),
        )

        # Scope circular-flow search to accounts already implicated by other
        # detectors — but as PARTICIPANTS (any account in a flagged event),
        # not just central accounts. A ring's cycle typically closes back to
        # a fan-in SOURCE account, which is never itself a detector's
        # central_account (fan-in's central account is the collector it
        # sends to) — restricting to central_account alone would silently
        # miss exactly the closing hop the cycle search exists to find.
        candidate_accounts = set()
        _STRUCTURAL_PATTERN_TYPES = {
            "fan_in",
            "fan_out",
            "layering",
            "split_merge",
        }

        for e in events:
            if e.pattern_type in _STRUCTURAL_PATTERN_TYPES:
                candidate_accounts.update(e.accounts)
        cf_cfg = self.config.get("circular_flow", {})
        events += detect_circular_flow(
            self.df,
            self.window_bounds,
            max_cycle_length=cf_cfg.get("max_cycle_length", 6),
            max_duration_days=cf_cfg.get("max_duration_days", 7),
            candidate_start_accounts=candidate_accounts if candidate_accounts else None,
        )

        if self.feature_table is not None:
            events += detect_escalating_connectivity(self.feature_table)

        return events

    @staticmethod
    def _hours(spec) -> float:
        if isinstance(spec, (int, float)):
            return float(spec)
        return pd.Timedelta(spec).total_seconds() / 3600.0

    @staticmethod
    def events_to_dataframe(events: list) -> pd.DataFrame:
        if not events:
            return pd.DataFrame(
                columns=["pattern_type", "window_id", "timestamp", "central_account", "accounts",
                         "transaction_ids", "pattern_strength", "evidence"]
            )
        return pd.DataFrame([e.to_dict() for e in events])
