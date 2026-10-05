"""
Lead-Time Engine (Phase 15) — the PRIMARY RESEARCH MODULE.

For each ring candidate:
  1. Match it to a ground-truth demo ring by account overlap.
  2. Reconstruct a CUMULATIVE risk trajectory using Phase 9's exposed
     `event_window_ids` (no need to re-run Phases 8-9).
  3. warning_time = earliest window where cumulative score crosses the
     alert threshold.
  4. observable_time = the ground-truth ring's own recorded
     observable_time, converted to a window_id.
  5. lead_time = observable_time - warning_time (positive = early).

APPROXIMATION, stated explicitly: the cumulative score recomputes
fund_flow and persistence from truncated evidence, but holds
behavioural/network at their FINAL (Phase 12) values rather than
recomputing a fully time-sliced subgraph/model score per window — a
deliberate scope trade-off, documented as a follow-up, not hidden.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.temporal.trajectory import _PATTERN_WEIGHT

_MAX_POSSIBLE_PATTERN_WEIGHT = sum(_PATTERN_WEIGHT.values())


@dataclass
class LeadTimeResult:
    candidate_ring_id: str
    matched_ground_truth_ring_id: object
    match_overlap_fraction: float
    warning_window: object
    observable_window: object
    lead_time_windows: object
    alerted: bool
    early_detection: object

    def to_dict(self) -> dict:
        return {
            "candidate_ring_id": self.candidate_ring_id,
            "matched_ground_truth_ring_id": self.matched_ground_truth_ring_id,
            "match_overlap_fraction": self.match_overlap_fraction,
            "warning_window": self.warning_window,
            "observable_window": self.observable_window,
            "lead_time_windows": self.lead_time_windows,
            "alerted": self.alerted,
            "early_detection": self.early_detection,
        }


def match_candidate_to_ground_truth(candidate, ground_truth_rings: list, min_overlap: float = 0.3):
    best_match, best_overlap = None, 0.0
    candidate_accounts = set(candidate.accounts)
    for gt in ground_truth_rings:
        gt_accounts = set(gt["accounts"])
        if not gt_accounts:
            continue
        overlap = len(gt_accounts & candidate_accounts) / len(gt_accounts)
        if overlap > best_overlap:
            best_overlap, best_match = overlap, gt
    if best_match is not None and best_overlap >= min_overlap:
        return best_match, best_overlap
    return None, 0.0


def _window_id_for_date(date_str: str, window_bounds: list) -> int:
    ts = pd.Timestamp(date_str, tz="UTC")
    for b in window_bounds:
        if b.start <= ts < b.end:
            return b.window_id
    return window_bounds[-1].window_id


def _cumulative_risk_at_window(candidate, target_window: int, final_behavioural: float, final_network: float, weights: dict) -> float:
    seq = candidate.trajectory.get("pattern_sequence", [])
    win_ids = candidate.trajectory.get("event_window_ids", [])
    truncated_patterns = [p for p, w in zip(seq, win_ids) if w <= target_window]
    truncated_count = len(truncated_patterns)

    if truncated_count == 0:
        return 0.0

    weight_sum = sum(_PATTERN_WEIGHT.get(p, 0.5) for p in set(truncated_patterns))
    fund_flow = min(100.0, (weight_sum / _MAX_POSSIBLE_PATTERN_WEIGHT) * 100)

    density = truncated_count / max(len(candidate.accounts), 1)
    persistence = min(100.0, 35 * np.log1p(density * 3))

    return (
        weights["behavioural"] * final_behavioural
        + weights["network"] * final_network
        + weights["fund_flow"] * fund_flow
        + weights["persistence"] * persistence
    )


def compute_lead_time_for_candidate(candidate, risk_result, ground_truth_rings, window_bounds, weights, alert_threshold, min_overlap=0.3):
    matched_ring, overlap = match_candidate_to_ground_truth(candidate, ground_truth_rings, min_overlap)

    win_ids = candidate.trajectory.get("event_window_ids", [])
    if not win_ids:
        return LeadTimeResult(candidate.candidate_ring_id, None, 0.0, None, None, None, False, None)

    final_behavioural = risk_result.score_components.get("behavioural", 0.0) if risk_result else 0.0
    final_network = risk_result.score_components.get("network", 0.0) if risk_result else 0.0

    warning_window = None
    for w in sorted(set(win_ids)):
        score = _cumulative_risk_at_window(candidate, w, final_behavioural, final_network, weights)
        if score >= alert_threshold:
            warning_window = w
            break

    alerted = warning_window is not None

    if matched_ring is None:
        return LeadTimeResult(candidate.candidate_ring_id, None, overlap, warning_window, None, None, alerted, None)

    observable_window = _window_id_for_date(matched_ring["observable_time"], window_bounds)

    if not alerted:
        return LeadTimeResult(
            candidate.candidate_ring_id, matched_ring["ring_id"], overlap,
            None, observable_window, None, False, False,
        )

    lead_time = observable_window - warning_window
    return LeadTimeResult(
        candidate.candidate_ring_id, matched_ring["ring_id"], overlap,
        warning_window, observable_window, lead_time, True, lead_time >= 0,
    )


def summarize_lead_times(results: list) -> dict:
    matched = [r for r in results if r.matched_ground_truth_ring_id is not None]
    alerted_and_matched = [r for r in matched if r.alerted and r.lead_time_windows is not None]
    lead_times = [r.lead_time_windows for r in alerted_and_matched]

    n_alerted_total = sum(1 for r in results if r.alerted)
    n_unmatched_alerted = sum(1 for r in results if r.alerted and r.matched_ground_truth_ring_id is None)

    return {
        "n_candidates": len(results),
        "n_matched_to_ground_truth": len(matched),
        "n_alerted": n_alerted_total,
        "n_alerted_and_matched": len(alerted_and_matched),
        "false_warning_rate_candidates": (n_unmatched_alerted / n_alerted_total) if n_alerted_total else None,
        "mean_lead_time_windows": float(np.mean(lead_times)) if lead_times else None,
        "median_lead_time_windows": float(np.median(lead_times)) if lead_times else None,
        "min_lead_time_windows": float(np.min(lead_times)) if lead_times else None,
        "max_lead_time_windows": float(np.max(lead_times)) if lead_times else None,
        "std_lead_time_windows": float(np.std(lead_times)) if len(lead_times) > 1 else None,
        "early_detection_rate": (
            sum(1 for r in alerted_and_matched if r.early_detection) / len(alerted_and_matched)
            if alerted_and_matched else None
        ),
        "ring_detection_rate": (
            sum(1 for r in matched if r.alerted) / len(matched) if matched else None
        ),
    }
