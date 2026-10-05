"""
Temporal Graph Engine.

ACCOUNT = NODE
TRANSACTION = DIRECTED EDGE
AMOUNT = EDGE WEIGHT
TIMESTAMP = TEMPORAL EDGE ATTRIBUTE

Builds a sequence of snapshot graphs G(t1), G(t2), ... from a clean,
chronologically-sorted canonical-schema DataFrame. Two snapshot modes
are supported (both are meaningful for different downstream uses):

  - "window":     only edges whose timestamp falls in [start, end) —
                   used for detecting patterns that happen WITHIN a
                   window (e.g. same-day fan-in).
  - "cumulative":  all edges with timestamp < end — used for tracking
                   NETWORK GROWTH / structural evolution over time
                   (Δdegree, ΔPageRank, etc. in later phases read
                   consecutive cumulative snapshots).

Graphs are built as nx.MultiDiGraph: multiple transactions between the
same ordered pair within a window are kept as separate parallel edges
(not collapsed), so transaction-level evidence (used by the forensic
evidence engine later) is never lost. Snapshots are built lazily
on request rather than all held in memory at once, to keep this
practical on larger transaction volumes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Literal

import networkx as nx
import pandas as pd

# configs/config.yaml uses lowercase shorthand ("1d", "1h", "7d");
# pandas' Timedelta parser wants the uppercase alias for these units.
_UNIT_MAP = {"d": "D", "h": "H", "w": "W", "s": "s", "min": "min"}


def _parse_offset(spec: str) -> pd.Timedelta:
    spec = spec.strip()
    for lower, upper in _UNIT_MAP.items():
        if spec.lower().endswith(lower) and spec[:-len(lower)].strip().isdigit():
            return pd.Timedelta(spec[: -len(lower)].strip() + upper)
    return pd.Timedelta(spec)  # fall back to letting pandas parse it directly


@dataclass
class WindowBounds:
    window_id: int
    start: pd.Timestamp
    end: pd.Timestamp  # exclusive


class TemporalGraphBuilder:
    def __init__(
        self,
        df: pd.DataFrame,
        window_size: str = "1d",
        step_size: str = "1d",
    ):
        """
        df must be the clean, canonical-schema, chronologically-sorted
        transaction DataFrame (output of src/preprocessing/cleaning.py).
        window_size / step_size are pandas Timedelta-parseable strings,
        e.g. "1h", "1d", "7d" — see configs/config.yaml `temporal:`.
        """
        if df.empty:
            raise ValueError("Cannot build a temporal graph from an empty DataFrame.")
        if not df["timestamp"].is_monotonic_increasing:
            raise ValueError(
                "Input to TemporalGraphBuilder must be chronologically sorted "
                "(run src/preprocessing/cleaning.py first)."
            )

        self.df = df
        self.window_size = _parse_offset(window_size)
        self.step_size = _parse_offset(step_size)
        self.t_min = df["timestamp"].min()
        self.t_max = df["timestamp"].max()

    # ------------------------------------------------------------ windows
    def generate_window_bounds(self) -> list[WindowBounds]:
        bounds = []
        start = self.t_min
        window_id = 0
        while start <= self.t_max:
            end = start + self.window_size
            bounds.append(WindowBounds(window_id, start, end))
            start = start + self.step_size
            window_id += 1
        return bounds

    # ------------------------------------------------------------ build
    def _rows_in_range(self, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        # end is exclusive to avoid double-counting a boundary row in
        # two adjacent windows when step_size == window_size.
        mask = (self.df["timestamp"] >= start) & (self.df["timestamp"] < end)
        return self.df.loc[mask]

    def _build_graph_from_rows(self, rows: pd.DataFrame) -> nx.MultiDiGraph:
        """
        Vectorized edge construction. The original implementation used
        `iterrows()` — convenient but catastrophically slow at real-data
        scale: verified at 7 seconds for a single ~175k-edge cumulative
        snapshot, which extrapolates to over an hour just for graph
        building across a real 720-window AMLSim run (before even
        reaching the more expensive per-window feature computation).
        `iterrows()` reconstructs a Series object per row, which is
        where the overhead comes from; building plain Python tuples via
        zip() over the underlying numpy arrays and handing them to
        add_edges_from() in one bulk call avoids that entirely.
        """
        G = nx.MultiDiGraph()
        if rows.empty:
            return G

        G.add_nodes_from(pd.concat([rows["sender"], rows["receiver"]]).unique())

        edges = [
            (
                sender, receiver,
                tx_id,  # MultiDiGraph edge key
                {
                    "transaction_id": tx_id,
                    "amount": amount,
                    "timestamp": timestamp,
                    "label": label,
                    "scenario_id": scenario_id,
                    "ring_id": ring_id,
                },
            )
            for sender, receiver, tx_id, amount, timestamp, label, scenario_id, ring_id in zip(
                rows["sender"], rows["receiver"], rows["transaction_id"], rows["amount"],
                rows["timestamp"], rows["label"], rows["scenario_id"], rows["ring_id"],
            )
        ]
        G.add_edges_from(edges)
        return G

    def build_snapshot(self, bounds: WindowBounds, mode: Literal["window", "cumulative"] = "window") -> nx.MultiDiGraph:
        if mode == "window":
            rows = self._rows_in_range(bounds.start, bounds.end)
        elif mode == "cumulative":
            rows = self.df.loc[self.df["timestamp"] < bounds.end]
        else:
            raise ValueError(f"Unknown mode '{mode}', expected 'window' or 'cumulative'")
        return self._build_graph_from_rows(rows)

    def iter_snapshots(self, mode: Literal["window", "cumulative"] = "window") -> Iterator[tuple[WindowBounds, nx.MultiDiGraph]]:
        """Lazily yield (bounds, graph) for every window — avoids holding
        every snapshot in memory simultaneously for large datasets."""
        for bounds in self.generate_window_bounds():
            yield bounds, self.build_snapshot(bounds, mode=mode)

    def full_graph(self) -> nx.MultiDiGraph:
        """The complete graph over all available history (no time cutoff)."""
        return self._build_graph_from_rows(self.df)
