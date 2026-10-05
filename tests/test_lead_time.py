"""
Phase 15 tests: lead-time engine.

Run with: pytest tests/test_lead_time.py -v
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ring.ring_candidate_engine import RingCandidate
from src.scoring.risk_engine import RiskScoreResult
from src.evaluation.lead_time import (
    match_candidate_to_ground_truth,
    compute_lead_time_for_candidate,
    summarize_lead_times,
)
from src.graph.temporal_graph import WindowBounds


def _candidate(cid, accounts, pattern_sequence, event_window_ids):
    return RingCandidate(
        candidate_ring_id=cid,
        accounts=accounts,
        transaction_ids=[f"T{i}" for i in range(len(pattern_sequence))],
        time_span=["2026-01-01", "2026-01-10"],
        patterns=sorted(set(pattern_sequence)),
        trajectory={"pattern_sequence": pattern_sequence, "event_window_ids": event_window_ids},
        network_statistics={"density": 0.1},
        formation_stage="WATCH",
        evidence_event_count=len(pattern_sequence),
    )


def _risk_result(behavioural=80, network=80):
    return RiskScoreResult(
        candidate_ring_id="R", risk_score=80, risk_level="HIGH",
        score_components={"behavioural": behavioural, "network": network, "fund_flow": 0, "persistence": 0},
        top_factors=[],
    )


def _weights():
    return {"behavioural": 0.35, "network": 0.20, "fund_flow": 0.25, "persistence": 0.20}


def _bounds(n=30):
    return [
        WindowBounds(i, pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=i),
                     pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=i + 1))
        for i in range(n)
    ]


def test_match_candidate_to_ground_truth_by_overlap():
    candidate = _candidate("R1", ["A", "B", "C", "X"], ["fan_in"], [0])
    ground_truth = [{"ring_id": "GT1", "accounts": ["A", "B", "C"], "observable_time": "2026-01-05"}]
    matched, overlap = match_candidate_to_ground_truth(candidate, ground_truth)
    assert matched["ring_id"] == "GT1"
    assert overlap == 1.0


def test_match_returns_none_below_min_overlap():
    candidate = _candidate("R1", ["A"], ["fan_in"], [0])
    ground_truth = [{"ring_id": "GT1", "accounts": ["A", "B", "C", "D"], "observable_time": "2026-01-05"}]
    matched, overlap = match_candidate_to_ground_truth(candidate, ground_truth, min_overlap=0.5)
    assert matched is None


def test_match_picks_best_overlap_among_multiple_ground_truth_rings():
    candidate = _candidate("R1", ["A", "B", "C", "D"], ["fan_in"], [0])
    ground_truth = [
        {"ring_id": "GT_LOW", "accounts": ["A", "Z", "Y", "X"], "observable_time": "2026-01-05"},
        {"ring_id": "GT_HIGH", "accounts": ["A", "B", "C"], "observable_time": "2026-01-05"},
    ]
    matched, overlap = match_candidate_to_ground_truth(candidate, ground_truth)
    assert matched["ring_id"] == "GT_HIGH"


def test_early_detection_positive_lead_time():
    candidate = _candidate("R1", ["A", "B", "C"], ["fan_in", "layering", "circular_flow"], [1, 2, 3])
    ground_truth = [{"ring_id": "GT1", "accounts": ["A", "B", "C"], "observable_time": "2026-01-07"}]
    result = compute_lead_time_for_candidate(
        candidate, _risk_result(), ground_truth, _bounds(), _weights(), alert_threshold=30
    )
    assert result.alerted is True
    assert result.matched_ground_truth_ring_id == "GT1"
    assert result.observable_window == 6
    assert result.lead_time_windows is not None
    assert result.lead_time_windows > 0
    assert result.early_detection is True


def test_late_detection_negative_lead_time():
    candidate = _candidate("R1", ["A", "B", "C"], ["fan_in"], [1])
    ground_truth = [{"ring_id": "GT1", "accounts": ["A", "B", "C"], "observable_time": "2026-01-02"}]
    result = compute_lead_time_for_candidate(
        candidate, _risk_result(behavioural=0, network=0), ground_truth, _bounds(), _weights(), alert_threshold=99
    )
    assert result.alerted is False
    assert result.early_detection is False


def test_unmatched_candidate_has_no_observable_time():
    candidate = _candidate("R1", ["Q", "R", "S"], ["fan_in"], [0])
    ground_truth = [{"ring_id": "GT1", "accounts": ["A", "B", "C"], "observable_time": "2026-01-05"}]
    result = compute_lead_time_for_candidate(
        candidate, _risk_result(), ground_truth, _bounds(), _weights(), alert_threshold=30
    )
    assert result.matched_ground_truth_ring_id is None
    assert result.observable_window is None
    assert result.early_detection is None


def test_no_events_returns_unalerted_result():
    candidate = _candidate("R1", ["A"], [], [])
    result = compute_lead_time_for_candidate(
        candidate, _risk_result(), [], _bounds(), _weights(), alert_threshold=30
    )
    assert result.alerted is False
    assert result.matched_ground_truth_ring_id is None


def test_summarize_lead_times_excludes_unmatched_from_lead_time_stats():
    matched_early = compute_lead_time_for_candidate(
        _candidate("R1", ["A", "B"], ["fan_in", "circular_flow"], [1, 2]),
        _risk_result(),
        [{"ring_id": "GT1", "accounts": ["A", "B"], "observable_time": "2026-01-06"}],
        _bounds(), _weights(), alert_threshold=30,
    )
    unmatched = compute_lead_time_for_candidate(
        _candidate("R2", ["Z"], ["fan_in"], [0]),
        _risk_result(), [{"ring_id": "GT1", "accounts": ["A", "B"], "observable_time": "2026-01-06"}],
        _bounds(), _weights(), alert_threshold=30,
    )
    summary = summarize_lead_times([matched_early, unmatched])
    assert summary["n_matched_to_ground_truth"] == 1
    assert summary["mean_lead_time_windows"] == matched_early.lead_time_windows


def test_summarize_lead_times_handles_no_results():
    summary = summarize_lead_times([])
    assert summary["n_candidates"] == 0
    assert summary["mean_lead_time_windows"] is None
