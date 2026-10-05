"""
Phase 8 tests: pattern trajectory engine.

Run with: pytest tests/test_trajectory.py -v
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.patterns.base import PatternEvent
from src.temporal.trajectory import group_events_into_trajectories, compute_trajectory_features, build_all_trajectories


def _event(pattern_type, window_id, timestamp, central, accounts, strength=0.5):
    return PatternEvent(
        pattern_type=pattern_type,
        window_id=window_id,
        timestamp=timestamp,
        central_account=central,
        accounts=accounts,
        transaction_ids=[f"T_{pattern_type}_{window_id}"],
        pattern_strength=strength,
        evidence={},
    )


def test_structural_events_sharing_an_account_are_grouped_together():
    events = [
        _event("fan_in", 0, "2026-01-01T00:00:00", "C1", ["C1", "S1", "S2", "S3", "S4"]),
        _event("layering", 1, "2026-01-02T00:00:00", "C1", ["C1", "C2", "C3", "C4"]),
    ]
    trajectories = group_events_into_trajectories(events)
    assert len(trajectories) == 1
    traj = list(trajectories.values())[0]
    assert traj.accounts == {"C1", "S1", "S2", "S3", "S4", "C2", "C3", "C4"}


def test_unrelated_structural_events_form_separate_trajectories():
    events = [
        _event("fan_in", 0, "2026-01-01T00:00:00", "HUB_A", ["HUB_A", "X1", "X2", "X3", "X4"]),
        _event("fan_in", 0, "2026-01-01T00:00:00", "HUB_B", ["HUB_B", "Y1", "Y2", "Y3", "Y4"]),
    ]
    trajectories = group_events_into_trajectories(events)
    assert len(trajectories) == 2


def test_circular_flow_does_not_bridge_unrelated_groups_regression():
    """Regression test for the exact over-merging bug found in Phase 8
    verification: circular_flow was originally a union-forming type and
    transitively merged nearly the whole account population via
    background-noise cycles. It must now only ATTACH to a group that
    already exists via a union-forming event on a shared account, never
    create a brand-new bridge between two independent groups."""
    events = [
        _event("fan_in", 0, "2026-01-01T00:00:00", "HUB_A", ["HUB_A", "X1", "X2", "X3", "X4"]),
        _event("fan_in", 0, "2026-01-01T00:00:00", "HUB_B", ["HUB_B", "Y1", "Y2", "Y3", "Y4"]),
        _event("circular_flow", 2, "2026-01-03T00:00:00", "X1", ["X1", "Y1", "Z9"]),
    ]
    trajectories = group_events_into_trajectories(events)
    assert len(trajectories) == 2, "circular_flow must not bridge unrelated structural groups"


def test_weak_event_attaches_to_existing_group_without_creating_new_one():
    events = [
        _event("fan_in", 0, "2026-01-01T00:00:00", "HUB", ["HUB", "S1", "S2", "S3", "S4"]),
        _event("rapid_pass_through", 1, "2026-01-02T00:00:00", "HUB", ["S1", "HUB", "OUT1"]),
    ]
    trajectories = group_events_into_trajectories(events)
    assert len(trajectories) == 1
    traj = list(trajectories.values())[0]
    assert len(traj.events) == 2
    assert "OUT1" in traj.accounts


def test_weak_event_with_no_matching_group_is_dropped():
    events = [
        _event("fan_in", 0, "2026-01-01T00:00:00", "HUB", ["HUB", "S1", "S2", "S3", "S4"]),
        _event("rapid_pass_through", 1, "2026-01-02T00:00:00", "ZZZ", ["ZZZ", "YYY"]),
    ]
    trajectories = group_events_into_trajectories(events)
    assert len(trajectories) == 1
    traj = list(trajectories.values())[0]
    assert len(traj.events) == 1


# ------------------------------------------------------------ features
def test_trajectory_features_capture_diversity_and_persistence():
    events = [
        _event("fan_in", 0, "2026-01-01T00:00:00", "HUB", ["HUB", "S1", "S2", "S3", "S4"]),
        _event("layering", 1, "2026-01-02T00:00:00", "HUB", ["HUB", "C2", "C3"]),
        _event("fan_out", 2, "2026-01-03T00:00:00", "C3", ["C3", "D1", "D2", "D3", "D4"]),
    ]
    trajectories = group_events_into_trajectories(events)
    traj = list(trajectories.values())[0]
    feat = compute_trajectory_features(traj)

    assert feat["pattern_diversity"] == 3
    assert feat["pattern_count"] == 3
    assert feat["n_consecutive_suspicious_windows"] == 3
    assert feat["first_suspicious_pattern"] == "fan_in"
    assert feat["latest_suspicious_pattern"] == "fan_out"
    assert feat["pattern_escalation_steps"] == 2
    assert feat["pattern_transitions"] == ["fan_in->layering", "layering->fan_out"]
    assert feat["has_structural_sequence"] is True


def test_trajectory_persistence_breaks_on_gap():
    events = [
        _event("fan_in", 0, "2026-01-01T00:00:00", "HUB", ["HUB", "S1", "S2", "S3", "S4"]),
        _event("layering", 5, "2026-01-06T00:00:00", "HUB", ["HUB", "C2", "C3"]),
    ]
    trajectories = group_events_into_trajectories(events)
    traj = list(trajectories.values())[0]
    feat = compute_trajectory_features(traj)
    assert feat["n_consecutive_suspicious_windows"] == 1


def test_combination_score_rewards_distinct_types_not_repetition():
    repeated = [_event("fan_in", i, f"2026-01-0{i+1}T00:00:00", "HUB", ["HUB", "S1", "S2", "S3", "S4"]) for i in range(3)]
    diverse = [
        _event("fan_in", 0, "2026-01-01T00:00:00", "HUB2", ["HUB2", "S1", "S2", "S3", "S4"]),
        _event("layering", 1, "2026-01-02T00:00:00", "HUB2", ["HUB2", "C2", "C3"]),
        _event("circular_flow", 2, "2026-01-03T00:00:00", "HUB2", ["HUB2", "C2", "C3"]),
    ]
    repeated_traj = list(group_events_into_trajectories(repeated).values())[0]
    diverse_traj = list(group_events_into_trajectories(diverse).values())[0]

    repeated_score = compute_trajectory_features(repeated_traj)["pattern_combination_score"]
    diverse_score = compute_trajectory_features(diverse_traj)["pattern_combination_score"]
    assert diverse_score > repeated_score


def test_build_all_trajectories_returns_dataframe():
    events = [_event("fan_in", 0, "2026-01-01T00:00:00", "HUB", ["HUB", "S1", "S2", "S3", "S4"])]
    trajectories, df = build_all_trajectories(events)
    assert len(trajectories) == 1
    assert len(df) == 1
    assert "pattern_combination_score" in df.columns
