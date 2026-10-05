"""
Evidence Engine (Phase 14).

Consolidates everything computed so far (Phase 9 candidate, Phase 12
risk score, Phase 13 forensic explanation) into ONE evidence record
per candidate, plus a compact evidence SUBGRAPH — only the accounts
and transactions actually relevant to that candidate, in the shape
the dashboard's graph UI (Cytoscape.js, Phase 20) needs: nodes and
edges, not a raw DataFrame.

warning_time / observable_time / lead_time are intentionally left as
None here too (same as Phase 13's how_early) — this engine assembles
evidence, it does not calculate lead time. That is Phase 15's job
specifically, and duplicating the calculation here would risk two
different lead-time numbers existing for the same candidate.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass
class EvidenceRecord:
    candidate_ring_id: str
    accounts: list
    transactions: list
    paths: list
    patterns: list
    time_range: list
    risk_factors: dict
    trajectory: dict
    warning_time: object = None
    observable_time: object = None
    lead_time: object = None
    evidence_subgraph: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "candidate_ring_id": self.candidate_ring_id,
            "accounts": self.accounts,
            "transactions": self.transactions,
            "paths": self.paths,
            "patterns": self.patterns,
            "time_range": self.time_range,
            "risk_factors": self.risk_factors,
            "trajectory": self.trajectory,
            "warning_time": self.warning_time,
            "observable_time": self.observable_time,
            "lead_time": self.lead_time,
            "evidence_subgraph": self.evidence_subgraph,
        }


def _build_evidence_subgraph(transactions: list) -> dict:
    nodes = {}
    edges = []
    for tx in transactions:
        for account in (tx["sender"], tx["receiver"]):
            if account not in nodes:
                nodes[account] = {"id": account, "label": account}
        edges.append({
            "id": tx["transaction_id"],
            "source": tx["sender"],
            "target": tx["receiver"],
            "amount": tx["amount"],
            "timestamp": tx["timestamp"],
        })
    return {"nodes": list(nodes.values()), "edges": edges}


def _extract_notable_paths(pattern_sequence: list, patterns: list) -> list:
    paths = []
    if "fan_in" in patterns and "layering" in patterns and "fan_out" in patterns:
        paths.append("fan-in collector -> layering chain -> fan-out distribution (full structural sequence observed)")
    elif "layering" in patterns:
        paths.append("layering chain observed (see layering pattern evidence for exact hops)")
    if "circular_flow" in patterns:
        paths.append("circular flow closes back toward an originating account")
    return paths


def build_evidence_record(candidate, df: pd.DataFrame, risk_result=None) -> EvidenceRecord:
    tx_rows = df[df["transaction_id"].isin(candidate.transaction_ids)]
    transactions = [
        {
            "transaction_id": row.transaction_id,
            "sender": row.sender,
            "receiver": row.receiver,
            "amount": float(row.amount),
            "timestamp": row.timestamp.isoformat() if hasattr(row.timestamp, "isoformat") else str(row.timestamp),
        }
        for row in tx_rows.itertuples(index=False)
    ]

    risk_factors = risk_result.to_dict() if risk_result is not None else {
        "risk_score": candidate.risk_score,
        "note": "Not yet evaluated" if candidate.risk_score is None else None,
    }

    return EvidenceRecord(
        candidate_ring_id=candidate.candidate_ring_id,
        accounts=candidate.accounts,
        transactions=transactions,
        paths=_extract_notable_paths(candidate.trajectory.get("pattern_sequence", []), candidate.patterns),
        patterns=candidate.patterns,
        time_range=candidate.time_span,
        risk_factors=risk_factors,
        trajectory=candidate.trajectory,
        evidence_subgraph=_build_evidence_subgraph(transactions),
    )


def write_evidence_records(records: list, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "evidence.json", "w") as f:
        json.dump([r.to_dict() for r in records], f, indent=2, default=str)
