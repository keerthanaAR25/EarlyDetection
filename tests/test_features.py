"""
Phase 6 tests: transaction, temporal, network, and delta features.

Run with: pytest tests/test_features.py -v
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.features.transaction_features import compute_transaction_features
from src.features.network_features import compute_network_features
from src.features.temporal_change_features import compute_temporal_change_features
from src.features.feature_engine import FeatureEngine
from src.graph.temporal_graph import TemporalGraphBuilder


def _tx(tid, sender, receiver, amount, day, hour=0):
    return {
        "transaction_id": tid,
        "sender": sender,
        "receiver": receiver,
        "amount": amount,
        "timestamp": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=day, hours=hour),
        "label": 0,
        "scenario_id": "",
        "ring_id": "",
        "dataset_source": "unit_test",
    }


def _sorted_df(rows):
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)


# ------------------------------------------------------------ transaction
def test_transaction_features_fan_in_counts():
    # 4 senders -> 1 receiver, same window
    rows = [_tx(f"T{i}", f"S{i}", "HUB", 100, day=0) for i in range(4)]
    df = _sorted_df(rows)
    feat = compute_transaction_features(df, window_id=0)
    hub = feat[feat["account_id"] == "HUB"].iloc[0]
    assert hub["in_count"] == 4
    assert hub["in_amount"] == 400
    assert hub["unique_senders"] == 4


def test_transaction_features_concentration_all_to_one_counterparty():
    rows = [_tx(f"T{i}", "A", "B", 100, day=0) for i in range(3)]
    df = _sorted_df(rows)
    feat = compute_transaction_features(df, window_id=0)
    a = feat[feat["account_id"] == "A"].iloc[0]
    assert a["out_amount_concentration"] == pytest.approx(1.0)  # all volume to one counterparty


def test_transaction_features_concentration_spread_evenly():
    rows = [_tx(f"T{i}", "A", f"B{i}", 100, day=0) for i in range(4)]
    df = _sorted_df(rows)
    feat = compute_transaction_features(df, window_id=0)
    a = feat[feat["account_id"] == "A"].iloc[0]
    assert a["out_amount_concentration"] == pytest.approx(0.25)  # HHI of 4 equal shares = 1/4


# ------------------------------------------------------------ network
def test_network_features_fan_in_hub_has_high_in_degree():
    rows = [_tx(f"T{i}", f"S{i}", "HUB", 100, day=0) for i in range(5)]
    df = _sorted_df(rows)
    G = TemporalGraphBuilder(df, "1d", "1d").full_graph()
    feat = compute_network_features(G, window_id=0)
    hub = feat[feat["account_id"] == "HUB"].iloc[0]
    assert hub["in_degree"] == 5
    assert hub["out_degree"] == 0
    assert hub["weighted_in_degree"] == 500


def test_network_features_intermediary_balance_ratio():
    # C has in_degree=2, out_degree=2 -> perfectly balanced pass-through
    rows = [
        _tx("T1", "A", "C", 100, day=0), _tx("T2", "B", "C", 100, day=0),
        _tx("T3", "C", "D", 100, day=0), _tx("T4", "C", "E", 100, day=0),
    ]
    df = _sorted_df(rows)
    G = TemporalGraphBuilder(df, "1d", "1d").full_graph()
    feat = compute_network_features(G, window_id=0)
    c = feat[feat["account_id"] == "C"].iloc[0]
    assert c["intermediary_balance_ratio"] == pytest.approx(1.0)


def test_network_features_empty_graph_returns_empty():
    import networkx as nx
    feat = compute_network_features(nx.MultiDiGraph(), window_id=0)
    assert feat.empty


# ------------------------------------------------------------ delta
def test_delta_features_capture_change_between_windows():
    df = pd.DataFrame(
        [
            {"account_id": "A", "window_id": 0, "total_degree": 2, "pagerank": 0.1, "total_count": 2,
             "total_amount": 100.0, "transaction_velocity": 1.0, "weighted_in_degree": 50.0,
             "weighted_out_degree": 50.0, "component_size": 3, "neighbor_count": 2},
            {"account_id": "A", "window_id": 1, "total_degree": 5, "pagerank": 0.3, "total_count": 5,
             "total_amount": 400.0, "transaction_velocity": 2.0, "weighted_in_degree": 200.0,
             "weighted_out_degree": 200.0, "component_size": 6, "neighbor_count": 4},
        ]
    )
    result = compute_temporal_change_features(df)
    row1 = result[result["window_id"] == 1].iloc[0]
    assert row1["delta_total_degree"] == 3
    assert row1["delta_pagerank"] == pytest.approx(0.2)
    assert row1["delta_total_amount"] == 300.0
    assert row1["delta_connectivity"] == 3 + 2  # delta_total_degree + delta_neighbor_count


def test_delta_features_first_window_is_nan():
    df = pd.DataFrame(
        [{"account_id": "A", "window_id": 0, "total_degree": 2, "pagerank": 0.1, "total_count": 2,
          "total_amount": 100.0, "transaction_velocity": 1.0, "weighted_in_degree": 50.0,
          "weighted_out_degree": 50.0, "component_size": 3, "neighbor_count": 2}]
    )
    result = compute_temporal_change_features(df)
    assert pd.isna(result.iloc[0]["delta_total_degree"])


# ------------------------------------------------------------ integration
def test_feature_engine_end_to_end_on_small_fan_in_scenario():
    rows = [_tx(f"T{i}", f"S{i}", "HUB", 100, day=0) for i in range(4)]
    rows += [_tx("T_next", "HUB", "OUT1", 350, day=1)]
    df = _sorted_df(rows)

    engine = FeatureEngine(df, window_size="1d", step_size="1d")
    table = engine.build()

    assert not table.empty
    assert {"window_id", "account_id", "in_degree", "total_amount", "delta_total_degree"}.issubset(table.columns)

    hub_rows = table[table["account_id"] == "HUB"].sort_values("window_id")
    assert hub_rows.iloc[0]["in_degree"] == 4     # fan-in window
    assert hub_rows.iloc[-1]["out_degree"] == 1   # layering-out window
