"""
Graph analytics operations shared across the temporal graph engine,
feature engineering (Phase 6), and pattern detection (Phase 7).

Kept separate from temporal_graph.py so these operations can be
applied to any nx.MultiDiGraph snapshot — windowed, cumulative, or
the full graph — without duplicating logic per caller.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx


@dataclass
class SnapshotStats:
    n_nodes: int
    n_edges: int  # transaction count (parallel edges counted individually)
    n_unique_pairs: int  # distinct (sender, receiver) pairs, i.e. simple-graph edge count
    total_amount: float
    weakly_connected_components: int
    largest_wcc_size: int
    strongly_connected_components: int
    largest_scc_size: int
    density: float  # of the underlying simple directed graph


def snapshot_stats(G: nx.MultiDiGraph) -> SnapshotStats:
    """Core descriptive statistics for one graph snapshot."""
    if G.number_of_nodes() == 0:
        return SnapshotStats(0, 0, 0, 0.0, 0, 0, 0, 0, 0.0)

    simple = nx.DiGraph(G)  # collapses parallel edges, used for density/components
    total_amount = sum(d.get("amount", 0.0) for _, _, d in G.edges(data=True))

    wccs = list(nx.weakly_connected_components(simple))
    sccs = list(nx.strongly_connected_components(simple))

    return SnapshotStats(
        n_nodes=G.number_of_nodes(),
        n_edges=G.number_of_edges(),
        n_unique_pairs=simple.number_of_edges(),
        total_amount=float(total_amount),
        weakly_connected_components=len(wccs),
        largest_wcc_size=max((len(c) for c in wccs), default=0),
        strongly_connected_components=len(sccs),
        largest_scc_size=max((len(c) for c in sccs), default=0),
        density=nx.density(simple),
    )


def connected_components(G: nx.MultiDiGraph, kind: str = "weak") -> list[set]:
    simple = nx.DiGraph(G)
    if kind == "weak":
        return [set(c) for c in nx.weakly_connected_components(simple)]
    elif kind == "strong":
        return [set(c) for c in nx.strongly_connected_components(simple)]
    raise ValueError("kind must be 'weak' or 'strong'")


def k_hop_neighborhood(G: nx.MultiDiGraph, node, k: int = 2, direction: str = "out") -> set:
    """Nodes reachable from `node` within k hops. direction: 'out' | 'in' | 'both'."""
    if node not in G:
        return set()
    if direction == "in":
        H = G.reverse(copy=False)
    elif direction == "both":
        H = G.to_undirected(as_view=True)
    else:
        H = G
    lengths = nx.single_source_shortest_path_length(H, node, cutoff=k)
    return {n for n in lengths if n != node}


def find_cycles(G: nx.MultiDiGraph, max_length: int = 6) -> list[list]:
    """Simple directed cycles up to max_length nodes. Uses the collapsed
    simple graph (parallel edges don't create additional distinct
    cycles at the account level) and networkx's cycle enumerator,
    capped for tractability on larger graphs."""
    simple = nx.DiGraph(G)
    cycles = []
    try:
        for cycle in nx.simple_cycles(simple, length_bound=max_length):
            if len(cycle) >= 2:  # exclude self-loops handled elsewhere
                cycles.append(cycle)
    except nx.NetworkXNoCycle:
        pass
    return cycles


def paths_between(G: nx.MultiDiGraph, source, target, max_length: int = 6) -> list[list]:
    simple = nx.DiGraph(G)
    if source not in simple or target not in simple:
        return []
    try:
        return list(nx.all_simple_paths(simple, source, target, cutoff=max_length))
    except nx.NodeNotFound:
        return []


def node_activity(G: nx.MultiDiGraph) -> dict:
    """Per-node in/out transaction counts and amounts — the base table
    that behavioural/network features (Phase 6) build on."""
    activity = {}
    for node in G.nodes():
        in_edges = list(G.in_edges(node, data=True))
        out_edges = list(G.out_edges(node, data=True))
        activity[node] = {
            "in_count": len(in_edges),
            "out_count": len(out_edges),
            "in_amount": sum(d.get("amount", 0.0) for _, _, d in in_edges),
            "out_amount": sum(d.get("amount", 0.0) for _, _, d in out_edges),
            "unique_senders": len({u for u, _, _ in in_edges}),
            "unique_receivers": len({v for _, v, _ in out_edges}),
        }
    return activity
