"""
Elliptic dataset adapter.

IMPORTANT STRUCTURAL DIFFERENCE FROM AMLSim (do not paper over this):

AMLSim's graph is ACCOUNT -> ACCOUNT (a node is a bank account; an edge
is a transfer of money between two accounts, with a real amount).

The original Elliptic dataset's graph is TRANSACTION -> TRANSACTION (a
node is a single Bitcoin transaction on the UTXO graph; an edge means
one transaction's output funds another transaction's input). There is
no "sender account" / "receiver account" concept, and the ~165 node
features are PCA-anonymized (no raw BTC amount is published).

This adapter maps Elliptic's transaction-to-transaction edges onto our
sender/receiver columns for structural/graph-analytics compatibility,
but:
  - `amount` is NOT available and is left as NaN (never fabricated).
  - `sender`/`receiver` here mean "upstream/downstream transaction",
    not "account". Any feature or narrative built from this adapter's
    output that talks about "accounts" is incorrect and must instead
    talk about "transactions" in the graph-theoretic sense.
  - `timestamp` is reconstructed from Elliptic's integer `time_step`
    (1..49), each step nominally ~2 weeks apart per the original
    Elliptic paper (Weber et al., 2019) — an approximation, not a
    real timestamp, and is documented as such in docs/dataset.md.

Expected raw files (original Elliptic release):
    elliptic_txs_features.csv   (no header; col0=txId, col1=time_step, 165 feature cols)
    elliptic_txs_classes.csv    (header: txId, class  where class in {"1","2","unknown"})
    elliptic_txs_edgelist.csv   (header: txId1, txId2)

Elliptic2 (subgraph-level money-laundering labels, IEEE Access 2026
paper referenced in the Review-1 literature review) uses a different
release format centered on labeled *subgraphs* rather than per-node
classes. This adapter targets the original Elliptic release; wiring
up Elliptic2 specifically is left as a documented follow-up in
docs/dataset.md rather than guessed at here.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from src.data.base_adapter import BaseDatasetAdapter

logger = logging.getLogger(__name__)

_STEP_UNIT_DAYS = 14  # ~2 weeks per Elliptic time_step, per Weber et al. 2019


class EllipticAdapter(BaseDatasetAdapter):
    source_name = "elliptic"

    def __init__(
        self,
        raw_path: str | Path,
        features_file: str = "elliptic_txs_features.csv",
        classes_file: str = "elliptic_txs_classes.csv",
        edgelist_file: str = "elliptic_txs_edgelist.csv",
        dataset_start_date: str = "2017-01-01",
    ):
        super().__init__(raw_path)
        self.features_file = features_file
        self.classes_file = classes_file
        self.edgelist_file = edgelist_file
        self.dataset_start_date = pd.Timestamp(dataset_start_date, tz="UTC")

    def _load_raw(self) -> pd.DataFrame:
        feat_path = self.raw_path / self.features_file
        class_path = self.raw_path / self.classes_file
        edge_path = self.raw_path / self.edgelist_file

        for p, label in [(feat_path, "features"), (class_path, "classes"), (edge_path, "edgelist")]:
            if not p.exists():
                raise FileNotFoundError(
                    f"Elliptic {label} file not found at {p}. Elliptic requires "
                    f"manual download/registration — see docs/dataset.md."
                )

        # features file has no header row in the original release
        features = pd.read_csv(feat_path, header=None)
        features = features.rename(columns={0: "txId", 1: "time_step"})[["txId", "time_step"]]

        classes = pd.read_csv(class_path)
        classes.columns = [c.strip().lower() for c in classes.columns]

        edges = pd.read_csv(edge_path)
        edges.columns = [c.strip() for c in edges.columns]

        tx_meta = features.merge(classes, on="txId", how="left")

        merged = edges.merge(
            tx_meta.rename(columns={"txId": "txId1", "time_step": "time_step_1"}),
            on="txId1",
            how="left",
        )

        class_map = {"1": 1, "2": 0, "unknown": -1}
        merged["label"] = merged["class"].astype(str).map(class_map).fillna(-1).astype(int)

        timestamp = self.dataset_start_date + pd.to_timedelta(
            (merged["time_step_1"].astype(float) - 1) * _STEP_UNIT_DAYS, unit="D"
        )

        out = pd.DataFrame(
            {
                "transaction_id": merged["txId1"].astype(str) + "_" + merged["txId2"].astype(str),
                "sender": merged["txId1"].astype(str),     # upstream transaction, not an account
                "receiver": merged["txId2"].astype(str),   # downstream transaction, not an account
                "amount": float("nan"),                    # not published in Elliptic
                "timestamp": timestamp,
                "label": merged["label"],
                "scenario_id": "",  # Elliptic does not provide typology/scenario groupings
                "ring_id": "",      # no ring-level ground truth in the original release
            }
        )
        return out
