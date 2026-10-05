"""
Phase 7 tests: fund-flow pattern detectors.

Run with: pytest tests/test_patterns.py -v
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.patterns.fan_in import detect_fan_in
from src.patterns.fan_out import detect_fan_out
from src.patterns.layering import detect_layering
from src.patterns.split_merge import detect_split_merge
from src.patterns.circular_flow import detect_circular_flow
from src.patterns.rapid_pass_through import detect_rapid_pass_through
from src.patterns.repeated_intermediary import detect_repeated_intermediary
from src.patterns.escalating_connectivity import detect_escalating_connectivity
from src.graph.temporal_graph import WindowBounds


def _tx(tid, sender, receiver, amount, day=0, hour=0, minute=0):
    return {
        "transaction_id": tid,
        "sender": sender,
        "receiver": receiver,
        "amount": amount,
        "timestamp": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=day, hours=hour, minutes=minute),
        "label": 0,
        "scenario_id": "",
        "ring_id": "",
        "dataset_source": "unit_test",
    }


def _sorted_df(rows):
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)


def _bounds(n_days=10):
    return [
        WindowBounds(i, pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=i),
                     pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=i + 1))
        for i in range(n_days)
    ]


# ------------------------------------------------------------ fan-in / fan-out
def test_fan_in_detects_hub_above_threshold():
    rows = [_tx(f"T{i}", f"S{i}", "HUB", 100, day=0) for i in range(5)]
    df = _sorted_df(rows)
    events = detect_fan_in(df, window_id=0, min_senders=4)
    assert len(events) == 1
    assert events[0].central_account == "HUB"
    assert events[0].evidence["n_senders"] == 5


def test_fan_in_below_threshold_not_flagged():
    rows = [_tx(f"T{i}", f"S{i}", "HUB", 100, day=0) for i in range(3)]
    df = _sorted_df(rows)
    events = detect_fan_in(df, window_id=0, min_senders=4)
    assert events == []


def test_fan_out_detects_hub_above_threshold():
    rows = [_tx(f"T{i}", "HUB", f"R{i}", 100, day=0) for i in range(5)]
    df = _sorted_df(rows)
    events = detect_fan_out(df, window_id=0, min_receivers=4)
    assert len(events) == 1
    assert events[0].central_account == "HUB"


# ------------------------------------------------------------ layering
def test_layering_detects_chain_with_conserved_amount_and_timing():
    rows = [
        _tx("T1", "A", "B", 1000, day=0, hour=0),
        _tx("T2", "B", "C", 950, day=0, hour=2),
        _tx("T3", "C", "D", 900, day=0, hour=4),
    ]
    df = _sorted_df(rows)
    events = detect_layering(df, _bounds(), min_hops=3, max_hops=6, max_hop_gap_hours=24, amount_tolerance=0.3)
    assert len(events) == 1
    assert events[0].accounts == ["A", "B", "C", "D"]
    assert events[0].evidence["n_hops"] == 3


def test_layering_rejects_chain_with_amount_mismatch():
    rows = [
        _tx("T1", "A", "B", 1000, day=0, hour=0),
        _tx("T2", "B", "C", 50, day=0, hour=2),
        _tx("T3", "C", "D", 40, day=0, hour=4),
    ]
    df = _sorted_df(rows)
    events = detect_layering(df, _bounds(), min_hops=3, amount_tolerance=0.3)
    assert events == []


def test_layering_rejects_chain_exceeding_time_gap():
    rows = [
        _tx("T1", "A", "B", 1000, day=0, hour=0),
        _tx("T2", "B", "C", 950, day=5, hour=0),
        _tx("T3", "C", "D", 900, day=5, hour=2),
    ]
    df = _sorted_df(rows)
    events = detect_layering(df, _bounds(), min_hops=3, max_hop_gap_hours=24)
    assert events == []


def test_layering_requires_out_of_order_timestamps_to_fail():
    rows = [
        _tx("T1", "A", "B", 1000, day=0, hour=5),
        _tx("T2", "B", "C", 950, day=0, hour=1),
        _tx("T3", "C", "D", 900, day=0, hour=6),
    ]
    df = _sorted_df(rows)
    events = detect_layering(df, _bounds(), min_hops=3)
    assert events == []


# ------------------------------------------------------------ split-merge
def test_split_merge_detects_diamond_pattern():
    rows = [
        _tx("T1", "A", "B", 500, day=0, hour=0),
        _tx("T2", "A", "C", 500, day=0, hour=0, minute=30),
        _tx("T3", "B", "D", 480, day=0, hour=5),
        _tx("T4", "C", "D", 480, day=0, hour=6),
    ]
    df = _sorted_df(rows)
    events = detect_split_merge(df, _bounds(), max_time_window="2d")
    assert len(events) == 1
    assert events[0].evidence["merge_destination"] == "D"
    assert set(events[0].evidence["split_targets"]) == {"B", "C"}


def test_split_merge_no_event_without_common_destination():
    rows = [
        _tx("T1", "A", "B", 500, day=0, hour=0),
        _tx("T2", "A", "C", 500, day=0, hour=0, minute=30),
        _tx("T3", "B", "D", 480, day=0, hour=5),
        _tx("T4", "C", "E", 480, day=0, hour=6),
    ]
    df = _sorted_df(rows)
    events = detect_split_merge(df, _bounds(), max_time_window="2d")
    assert events == []


# ------------------------------------------------------------ circular flow
def test_circular_flow_detects_simple_triangle():
    rows = [
        _tx("T1", "A", "B", 100, day=0, hour=0),
        _tx("T2", "B", "C", 95, day=0, hour=2),
        _tx("T3", "C", "A", 90, day=0, hour=4),
    ]
    df = _sorted_df(rows)
    events = detect_circular_flow(df, _bounds(), max_cycle_length=6, max_duration_days=7)
    assert len(events) == 1
    assert set(events[0].accounts) == {"A", "B", "C"}


def test_circular_flow_no_cycle_on_dag():
    rows = [
        _tx("T1", "A", "B", 100, day=0, hour=0),
        _tx("T2", "B", "C", 95, day=0, hour=2),
    ]
    df = _sorted_df(rows)
    events = detect_circular_flow(df, _bounds())
    assert events == []


def test_circular_flow_respects_candidate_scoping():
    rows = [
        _tx("T1", "A", "B", 100, day=0, hour=0),
        _tx("T2", "B", "A", 95, day=0, hour=2),
    ]
    df = _sorted_df(rows)
    events_scoped_out = detect_circular_flow(df, _bounds(), candidate_start_accounts={"Z"})
    events_scoped_in = detect_circular_flow(df, _bounds(), candidate_start_accounts={"A"})
    assert events_scoped_out == []
    assert len(events_scoped_in) == 1


# ------------------------------------------------------------ rapid pass-through / repeated intermediary
def test_rapid_pass_through_detects_quick_forward():
    rows = [_tx("T1", "A", "MULE", 500, day=0, hour=0), _tx("T2", "MULE", "B", 490, day=0, hour=2)]
    df = _sorted_df(rows)
    events = detect_rapid_pass_through(df, _bounds(), max_hold_time_hours=6)
    assert len(events) == 1
    assert events[0].central_account == "MULE"


def test_rapid_pass_through_ignores_slow_forward():
    rows = [_tx("T1", "A", "SLOW", 500, day=0, hour=0), _tx("T2", "SLOW", "B", 490, day=3, hour=0)]
    df = _sorted_df(rows)
    events = detect_rapid_pass_through(df, _bounds(), max_hold_time_hours=6)
    assert events == []


def test_repeated_intermediary_requires_multiple_instances():
    rows = []
    for i in range(3):
        rows.append(_tx(f"IN{i}", f"UP{i}", "HUB", 100, day=i, hour=0))
        rows.append(_tx(f"OUT{i}", "HUB", f"DOWN{i}", 95, day=i, hour=2))
    df = _sorted_df(rows)
    events = detect_repeated_intermediary(df, _bounds(), max_hold_time_hours=6, min_pass_through_count=3)
    assert len(events) == 1
    assert events[0].central_account == "HUB"
    assert events[0].evidence["pass_through_count"] == 3


def test_repeated_intermediary_not_flagged_below_threshold():
    rows = [_tx("IN0", "UP0", "HUB", 100, day=0, hour=0), _tx("OUT0", "HUB", "DOWN0", 95, day=0, hour=2)]
    df = _sorted_df(rows)
    events = detect_repeated_intermediary(df, _bounds(), min_pass_through_count=3)
    assert events == []


# ------------------------------------------------------------ escalating connectivity
def test_escalating_connectivity_flags_consecutive_growth():
    df = pd.DataFrame(
        [
            {"account_id": "A", "window_id": 0, "delta_connectivity": None},
            {"account_id": "A", "window_id": 1, "delta_connectivity": 2},
            {"account_id": "A", "window_id": 2, "delta_connectivity": 3},
        ]
    )
    events = detect_escalating_connectivity(df, min_consecutive_increases=2, min_total_delta=3.0)
    assert len(events) == 1
    assert events[0].central_account == "A"
    assert events[0].evidence["total_connectivity_delta"] == 5


def test_escalating_connectivity_ignores_flat_or_declining():
    df = pd.DataFrame(
        [
            {"account_id": "A", "window_id": 0, "delta_connectivity": -1},
            {"account_id": "A", "window_id": 1, "delta_connectivity": 0},
        ]
    )
    events = detect_escalating_connectivity(df)
    assert events == []
