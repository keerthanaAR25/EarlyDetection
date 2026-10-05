"""
Network features (spec category C).

Computed on the CUMULATIVE graph as of each window's end (all edges
with timestamp < window_end) — this is deliberate: an account's
structural role (degree, centrality, which component it belongs to)
is a property of the network as it has evolved so far, not just of
one window's transactions. Using only the window's own edges would
make single-window centrality nearly meaningless (most windows are
too sparse for pagerank/betweenness to mean anything).

This is also exactly why temporal_change_features.py can compute
Δdegree, ΔPageRank, etc. between consecutive windows: it's tracking
how each account's position in the SAME growing network changes.
"""
from __future__ import annotations

import networkx as nx
import pandas as pd

_EPS = 1e-9


def compute_network_features(G: "nx.MultiDiGraph", window_id: int, betweenness_sample_k: int | None = None) -> pd.DataFrame:
    """
    betweenness_sample_k: if set and smaller than the graph's node
    count, betweenness centrality is APPROXIMATED via networkx's
    k-sample estimator instead of computed exactly. Necessary at real
    AMLSim scale: exact betweenness is O(V*E), and a real run's
    cumulative graph reaches ~4,700 nodes / ~198,000 edges — exact
    computation there did not finish within this environment's
    per-command time limit, across 720 windows. This was flagged as a
    known follow-up when network features were first built (Phase 6,
    validated only at ~200-account demo scale) and is now a real,
    encountered constraint rather than a hypothetical one. Callers at
    real AMLSim scale should treat betweenness_centrality as a sampled
    estimate, not an exact value — documented here and in docs/dataset.md.
    """
    if G.number_of_nodes() == 0:
        return pd.DataFrame()

    simple_di = nx.DiGraph(G)          # collapsed, directed — for degree/pagerank/betweenness
    simple_undi = simple_di.to_undirected()  # for clustering coefficient

    weighted_in = {n: 0.0 for n in G.nodes()}
    weighted_out = {n: 0.0 for n in G.nodes()}
    for u, v, d in G.edges(data=True):
        weighted_out[u] += d.get("amount", 0.0)
        weighted_in[v] += d.get("amount", 0.0)

    pagerank = nx.pagerank(simple_di, weight=None) if simple_di.number_of_edges() > 0 else {n: 0.0 for n in G.nodes()}

    if simple_di.number_of_nodes() <= 2:
        betweenness = {n: 0.0 for n in G.nodes()}
    elif betweenness_sample_k and betweenness_sample_k < simple_di.number_of_nodes():
        betweenness = nx.betweenness_centrality(simple_di, k=betweenness_sample_k, seed=42)
    else:
        betweenness = nx.betweenness_centrality(simple_di)

    clustering = nx.clustering(simple_undi)

    wccs = list(nx.weakly_connected_components(simple_di))
    component_size = {}
    for comp in wccs:
        for n in comp:
            component_size[n] = len(comp)

    rows = []
    for node in G.nodes():
        in_deg = simple_di.in_degree(node)
        out_deg = simple_di.out_degree(node)
        neighbors = set(simple_undi.neighbors(node))
        rows.append(
            {
                "window_id": window_id,
                "account_id": node,
                "in_degree": in_deg,
                "out_degree": out_deg,
                "total_degree": in_deg + out_deg,
                "weighted_in_degree": weighted_in.get(node, 0.0),
                "weighted_out_degree": weighted_out.get(node, 0.0),
                "degree_ratio_out_in": out_deg / (in_deg + _EPS),
                "pagerank": pagerank.get(node, 0.0),
                "betweenness_centrality": betweenness.get(node, 0.0),
                "clustering_coefficient": clustering.get(node, 0.0),
                "component_size": component_size.get(node, 1),
                "neighbor_count": len(neighbors),
                # a node passing roughly as much in as out, with both sides
                # present, behaves like an intermediary/pass-through account
                "intermediary_balance_ratio": (
                    min(in_deg, out_deg) / (max(in_deg, out_deg) + _EPS) if (in_deg + out_deg) > 0 else 0.0
                ),
            }
        )
    return pd.DataFrame(rows)
