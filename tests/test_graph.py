"""
Phase 5 tests: TemporalGraphBuilder and graph_ops.

Run with: pytest tests/test_graph.py -v
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.graph.temporal_graph import TemporalGraphBuilder
from src.graph.graph_ops import (
    snapshot_stats,
    connected_components,
    k_hop_neighborhood,
    find_cycles,
    paths_between,
    node_activity,
)


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
    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    return df


# ------------------------------------------------------------ construction
def test_rejects_empty_dataframe():
    with pytest.raises(ValueError):
        TemporalGraphBuilder(pd.DataFrame())


def test_rejects_unsorted_input():
    rows = [_tx("T1", "A", "B", 10, day=2), _tx("T2", "B", "C", 10, day=0)]
    df = pd.DataFrame(rows)  # deliberately NOT sorted
    with pytest.raises(ValueError):
        TemporalGraphBuilder(df)


def test_window_bounds_cover_full_range():
    rows = [_tx(f"T{i}", "A", "B", 10, day=i) for i in range(5)]
    df = _sorted_df(rows)
    builder = TemporalGraphBuilder(df, window_size="1d", step_size="1d")
    bounds = builder.generate_window_bounds()
    assert len(bounds) == 5
    assert bounds[0].start == df["timestamp"].min()


# ------------------------------------------------------------ snapshot content
def test_window_snapshot_only_contains_its_own_transactions():
    rows = [_tx("T1", "A", "B", 10, day=0), _tx("T2", "C", "D", 20, day=1)]
    df = _sorted_df(rows)
    builder = TemporalGraphBuilder(df, window_size="1d", step_size="1d")
    bounds_list = builder.generate_window_bounds()

    G0 = builder.build_snapshot(bounds_list[0], mode="window")
    assert set(G0.nodes()) == {"A", "B"}
    assert G0.number_of_edges() == 1


def test_cumulative_snapshot_grows_over_time():
    rows = [_tx("T1", "A", "B", 10, day=0), _tx("T2", "C", "D", 20, day=1), _tx("T3", "E", "F", 30, day=2)]
    df = _sorted_df(rows)
    builder = TemporalGraphBuilder(df, window_size="1d", step_size="1d")
    bounds_list = builder.generate_window_bounds()

    sizes = [builder.build_snapshot(b, mode="cumulative").number_of_edges() for b in bounds_list]
    assert sizes == sorted(sizes)  # monotonically non-decreasing
    assert sizes[-1] == 3


def test_parallel_edges_preserved_not_collapsed():
    rows = [_tx("T1", "A", "B", 10, day=0), _tx("T2", "A", "B", 20, day=0)]
    df = _sorted_df(rows)
    builder = TemporalGraphBuilder(df, window_size="1d", step_size="1d")
    G = builder.full_graph()
    assert G.number_of_edges() == 2  # both transactions kept as distinct edges


# ------------------------------------------------------------ graph_ops
def test_snapshot_stats_on_simple_chain():
    rows = [_tx("T1", "A", "B", 100, day=0), _tx("T2", "B", "C", 90, day=0)]
    df = _sorted_df(rows)
    G = TemporalGraphBuilder(df, "1d", "1d").full_graph()
    stats = snapshot_stats(G)
    assert stats.n_nodes == 3
    assert stats.n_edges == 2
    assert stats.total_amount == 190
    assert stats.weakly_connected_components == 1
    assert stats.strongly_connected_components == 3  # no cycle -> each node its own SCC


def test_snapshot_stats_empty_graph():
    import networkx as nx
    stats = snapshot_stats(nx.MultiDiGraph())
    assert stats.n_nodes == 0
    assert stats.density == 0.0


def test_find_cycles_detects_triangle():
    rows = [_tx("T1", "A", "B", 10, day=0), _tx("T2", "B", "C", 10, day=0), _tx("T3", "C", "A", 10, day=0)]
    df = _sorted_df(rows)
    G = TemporalGraphBuilder(df, "1d", "1d").full_graph()
    cycles = find_cycles(G, max_length=6)
    assert any(set(c) == {"A", "B", "C"} for c in cycles)


def test_find_cycles_no_false_positive_on_dag():
    rows = [_tx("T1", "A", "B", 10, day=0), _tx("T2", "B", "C", 10, day=0), _tx("T3", "A", "C", 10, day=0)]
    df = _sorted_df(rows)
    G = TemporalGraphBuilder(df, "1d", "1d").full_graph()
    cycles = find_cycles(G, max_length=6)
    assert cycles == []


def test_k_hop_neighborhood():
    rows = [_tx("T1", "A", "B", 10, day=0), _tx("T2", "B", "C", 10, day=0), _tx("T3", "C", "D", 10, day=0)]
    df = _sorted_df(rows)
    G = TemporalGraphBuilder(df, "1d", "1d").full_graph()
    one_hop = k_hop_neighborhood(G, "A", k=1, direction="out")
    two_hop = k_hop_neighborhood(G, "A", k=2, direction="out")
    assert one_hop == {"B"}
    assert two_hop == {"B", "C"}


def test_paths_between():
    rows = [_tx("T1", "A", "B", 10, day=0), _tx("T2", "B", "C", 10, day=0)]
    df = _sorted_df(rows)
    G = TemporalGraphBuilder(df, "1d", "1d").full_graph()
    paths = paths_between(G, "A", "C", max_length=5)
    assert ["A", "B", "C"] in paths


def test_node_activity_counts():
    rows = [
        _tx("T1", "A", "B", 100, day=0),
        _tx("T2", "C", "B", 50, day=0),
        _tx("T3", "B", "D", 30, day=0),
    ]
    df = _sorted_df(rows)
    G = TemporalGraphBuilder(df, "1d", "1d").full_graph()
    activity = node_activity(G)
    assert activity["B"]["in_count"] == 2
    assert activity["B"]["out_count"] == 1
    assert activity["B"]["in_amount"] == 150
    assert activity["B"]["unique_senders"] == 2


def test_connected_components_weak_and_strong():
    rows = [_tx("T1", "A", "B", 10, day=0), _tx("T2", "X", "Y", 10, day=0)]
    df = _sorted_df(rows)
    G = TemporalGraphBuilder(df, "1d", "1d").full_graph()
    weak = connected_components(G, kind="weak")
    assert len(weak) == 2
    assert {"A", "B"} in weak and {"X", "Y"} in weak
