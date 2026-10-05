"""
Phase 9 tests: ring candidate engine.

Run with: pytest tests/test_ring_candidates.py -v
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.patterns.base import PatternEvent
from src.temporal.trajectory import group_events_into_trajectories
from src.ring.ring_candidate_engine import RingCandidateEngine, _central_account_clusters


def _event(pattern_type, window_id, day, central, accounts, tx_ids=None):
    return PatternEvent(
        pattern_type=pattern_type,
        window_id=window_id,
        timestamp=f"2026-01-{day:02d}T00:00:00+00:00",
        central_account=central,
        accounts=accounts,
        transaction_ids=tx_ids or [f"T_{pattern_type}_{day}_{central}"],
        pattern_strength=0.8,
        evidence={},
    )


def _tx_df(rows):
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def _config(**overrides):
    cfg = {"ring_candidates": {"min_accounts": 3, "min_pattern_count": 2, "max_formation_gap_days": 10}}
    cfg["ring_candidates"].update(overrides)
    return cfg


def test_central_account_clusters_links_via_shared_central():
    e1 = _event("fan_in", 0, 1, "C1", ["C1", "S1", "S2", "S3"])
    e2 = _event("layering", 1, 2, "C1", ["C1", "C2", "C3"])
    clusters = _central_account_clusters([e1, e2])
    assert len(clusters) == 1
    assert len(clusters[0]) == 2


def test_central_account_clusters_links_via_peripheral_becomes_central():
    e1 = _event("layering", 0, 1, "C1", ["C1", "C2", "C3", "C4"])
    e2 = _event("fan_out", 1, 2, "C4", ["C4", "D1", "D2", "D3"])
    clusters = _central_account_clusters([e1, e2])
    assert len(clusters) == 1


def test_central_account_clusters_does_not_link_unrelated_events():
    e1 = _event("fan_in", 0, 1, "HUB_A", ["HUB_A", "X1", "X2", "X3"])
    e2 = _event("fan_in", 0, 1, "HUB_B", ["HUB_B", "Y1", "Y2", "Y3"])
    clusters = _central_account_clusters([e1, e2])
    assert len(clusters) == 2


def test_full_ring_reconstructed_from_fan_in_layering_fan_out():
    events = [
        _event("fan_in", 2, 3, "C1", ["C1", "S1", "S2", "S3", "S4"], tx_ids=["T1", "T2", "T3", "T4"]),
        _event("layering", 3, 4, "C1", ["C1", "C2", "C3", "C4"], tx_ids=["T5", "T6", "T7"]),
        _event("fan_out", 4, 5, "C4", ["C4", "D1", "D2", "D3", "D4"], tx_ids=["T8", "T9", "T10", "T11"]),
    ]
    df_rows = []
    for e in events:
        accts = e.accounts
        for i, tx in enumerate(e.transaction_ids):
            sender = accts[0] if e.pattern_type != "fan_in" else accts[i % (len(accts) - 1) + 1]
            receiver = accts[0]
            df_rows.append({"transaction_id": tx, "sender": sender, "receiver": receiver, "amount": 100,
                             "timestamp": e.timestamp, "label": 1, "scenario_id": "R", "ring_id": "R",
                             "dataset_source": "unit_test"})
    df = _tx_df(df_rows)

    trajectories = group_events_into_trajectories(events)
    engine = RingCandidateEngine(df, trajectories, _config())
    candidates = engine.build()

    assert len(candidates) == 1
    cand = candidates[0]
    assert set(cand.accounts) == {"C1", "S1", "S2", "S3", "S4", "C2", "C3", "C4", "D1", "D2", "D3", "D4"}
    assert set(cand.patterns) == {"fan_in", "layering", "fan_out"}
    assert cand.risk_score is None


def test_unrelated_background_events_stay_separate_candidates():
    events = [
        _event("fan_in", 0, 1, "HUB_A", ["HUB_A", "X1", "X2", "X3", "X4"]),
        _event("layering", 1, 2, "HUB_A", ["HUB_A", "X5", "X6"]),
        _event("fan_in", 0, 1, "HUB_B", ["HUB_B", "Y1", "Y2", "Y3", "Y4"]),
        _event("layering", 1, 2, "HUB_B", ["HUB_B", "Y5", "Y6"]),
    ]
    df_rows = []
    for e in events:
        for i, tx in enumerate(e.transaction_ids):
            df_rows.append({"transaction_id": tx, "sender": e.central_account, "receiver": e.accounts[-1],
                             "amount": 100, "timestamp": e.timestamp, "label": 0, "scenario_id": "",
                             "ring_id": "", "dataset_source": "unit_test"})
    df = _tx_df(df_rows)

    trajectories = group_events_into_trajectories(events)
    engine = RingCandidateEngine(df, trajectories, _config())
    candidates = engine.build()

    assert len(candidates) == 2
    account_sets = [set(c.accounts) for c in candidates]
    assert not (account_sets[0] & account_sets[1])


def test_min_accounts_filter_drops_tiny_candidates():
    events = [
        _event("fan_in", 0, 1, "HUB", ["HUB", "S1"]),
        _event("layering", 1, 2, "HUB", ["HUB", "C2"]),
    ]
    df_rows = [{"transaction_id": tx, "sender": e.central_account, "receiver": e.accounts[-1], "amount": 100,
                "timestamp": e.timestamp, "label": 0, "scenario_id": "", "ring_id": "", "dataset_source": "u"}
               for e in events for tx in e.transaction_ids]
    df = _tx_df(df_rows)

    trajectories = group_events_into_trajectories(events)
    engine = RingCandidateEngine(df, trajectories, _config(min_accounts=5))
    candidates = engine.build()
    assert candidates == []


def test_formation_gap_splits_temporally_distant_evidence():
    e1 = _event("fan_in", 0, 1, "HUB", ["HUB", "S1", "S2", "S3", "S4"])
    e2 = _event("layering", 60, 28, "HUB", ["HUB", "C2", "C3"])
    df_rows = [{"transaction_id": tx, "sender": e.central_account, "receiver": e.accounts[-1], "amount": 100,
                "timestamp": e.timestamp, "label": 0, "scenario_id": "", "ring_id": "", "dataset_source": "u"}
               for e in [e1, e2] for tx in e.transaction_ids]
    df = _tx_df(df_rows)

    trajectories = group_events_into_trajectories([e1, e2])
    engine = RingCandidateEngine(df, trajectories, _config(max_formation_gap_days=10, min_pattern_count=1, min_accounts=3))
    candidates = engine.build()
    assert len(candidates) == 2
