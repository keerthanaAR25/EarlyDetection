#!/usr/bin/env python3
"""
Build the consolidated evidence record (+ evidence subgraph) for every
real ring candidate.

Usage:
    python scripts/build_evidence.py
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ring.ring_candidate_engine import RingCandidate
from src.scoring.risk_engine import RiskScoreResult
from src.evidence.evidence_engine import build_evidence_record, write_evidence_records


def main():
    df = pd.read_csv(ROOT / "data" / "processed" / "transactions_clean.csv", parse_dates=["timestamp"], dtype={"transaction_id": str, "sender": str, "receiver": str, "scenario_id": str, "ring_id": str})

    with open(ROOT / "results" / "ring_candidates.json") as f:
        candidates = [RingCandidate(**d) for d in json.load(f)]
    with open(ROOT / "results" / "risk_scores.json") as f:
        risk_by_id = {r["candidate_ring_id"]: RiskScoreResult(**r) for r in json.load(f)}

    records = [build_evidence_record(c, df, risk_result=risk_by_id.get(c.candidate_ring_id)) for c in candidates]

    out_dir = ROOT / "results"
    write_evidence_records(records, out_dir)

    print(f"Built {len(records)} evidence records")
    top = max(records, key=lambda r: r.risk_factors.get("risk_score") or 0)
    print(f"\nHighest-risk candidate: {top.candidate_ring_id}")
    print(f"  {len(top.accounts)} accounts, {len(top.transactions)} evidence transactions")
    print(f"  Evidence subgraph: {len(top.evidence_subgraph['nodes'])} nodes, {len(top.evidence_subgraph['edges'])} edges")
    print(f"  Notable paths: {top.paths}")
    print(f"  Risk: {top.risk_factors['risk_score']}/100 ({top.risk_factors['risk_level']})")

    print(f"\nWrote {out_dir / 'evidence.json'}")


if __name__ == "__main__":
    main()
