"""
Phase 14 tests: evidence engine.

Run with: pytest tests/test_evidence.py -v
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ring.ring_candidate_engine import RingCandidate
from src.scoring.risk_engine import RiskScoreResult
from src.evidence.evidence_engine import build_evidence_record, _build_evidence_subgraph, write_evidence_records


def _candidate():
    return RingCandidate(
        candidate_ring_id="RING001",
        accounts=["C1", "S1", "C4", "D1"],
        transaction_ids=["T1", "T2", "T3"],
        time_span=["2026-01-03T00:00:00", "2026-01-07T00:00:00"],
        patterns=["fan_in", "layering", "fan_out", "circular_flow"],
        trajectory={"pattern_sequence": ["fan_in", "layering", "fan_out", "circular_flow"]},
        network_statistics={"density": 0.09},
        formation_stage="OBSERVABLE_RING",
        evidence_event_count=4,
    )


def _tx_df():
    rows = [
        {"transaction_id": "T1", "sender": "S1", "receiver": "C1", "amount": 100.0,
         "timestamp": pd.Timestamp("2026-01-03T00:00:00", tz="UTC")},
        {"transaction_id": "T2", "sender": "C1", "receiver": "C4", "amount": 95.0,
         "timestamp": pd.Timestamp("2026-01-04T00:00:00", tz="UTC")},
        {"transaction_id": "T3", "sender": "C4", "receiver": "D1", "amount": 90.0,
         "timestamp": pd.Timestamp("2026-01-05T00:00:00", tz="UTC")},
        {"transaction_id": "T_UNRELATED", "sender": "X", "receiver": "Y", "amount": 10.0,
         "timestamp": pd.Timestamp("2026-01-03T00:00:00", tz="UTC")},
    ]
    return pd.DataFrame(rows)


def test_evidence_record_only_includes_candidate_transactions():
    record = build_evidence_record(_candidate(), _tx_df())
    tx_ids = {t["transaction_id"] for t in record.transactions}
    assert tx_ids == {"T1", "T2", "T3"}
    assert "T_UNRELATED" not in tx_ids


def test_evidence_subgraph_has_correct_nodes_and_edges():
    record = build_evidence_record(_candidate(), _tx_df())
    sub = record.evidence_subgraph
    node_ids = {n["id"] for n in sub["nodes"]}
    assert node_ids == {"S1", "C1", "C4", "D1"}
    assert len(sub["edges"]) == 3
    edge_ids = {e["id"] for e in sub["edges"]}
    assert edge_ids == {"T1", "T2", "T3"}


def test_evidence_subgraph_deduplicates_nodes():
    transactions = [
        {"transaction_id": "T1", "sender": "A", "receiver": "B", "amount": 10, "timestamp": "2026-01-01"},
        {"transaction_id": "T2", "sender": "B", "receiver": "A", "amount": 5, "timestamp": "2026-01-02"},
    ]
    sub = _build_evidence_subgraph(transactions)
    assert len(sub["nodes"]) == 2


def test_evidence_record_never_fabricates_lead_time():
    record = build_evidence_record(_candidate(), _tx_df())
    assert record.warning_time is None
    assert record.observable_time is None
    assert record.lead_time is None


def test_evidence_record_uses_real_risk_result_when_available():
    risk = RiskScoreResult(
        candidate_ring_id="RING001", risk_score=80.0, risk_level="CRITICAL",
        score_components={"behavioural": 90}, top_factors=["strong signal"],
    )
    record = build_evidence_record(_candidate(), _tx_df(), risk_result=risk)
    assert record.risk_factors["risk_score"] == 80.0
    assert record.risk_factors["risk_level"] == "CRITICAL"


def test_evidence_record_falls_back_honestly_without_risk_result():
    candidate = _candidate()
    candidate.risk_score = None
    record = build_evidence_record(candidate, _tx_df())
    assert record.risk_factors["risk_score"] is None
    assert record.risk_factors["note"] == "Not yet evaluated"


def test_notable_paths_reflect_actual_patterns_present():
    record = build_evidence_record(_candidate(), _tx_df())
    assert any("fan-in" in p for p in record.paths)
    assert any("circular" in p for p in record.paths)


def test_write_evidence_records_produces_valid_json(tmp_path):
    record = build_evidence_record(_candidate(), _tx_df())
    write_evidence_records([record], tmp_path)
    out_file = tmp_path / "evidence.json"
    assert out_file.exists()
    import json
    with open(out_file) as f:
        data = json.load(f)
    assert len(data) == 1
    assert data[0]["candidate_ring_id"] == "RING001"
