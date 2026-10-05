"""
Phase 18 tests: database models and loading.

Run with: pytest tests/test_database.py -v
"""
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.database.models import Base, Account, Transaction, RingCandidateRow, RiskScoreRow


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_account_round_trip(db_session):
    db_session.add(Account(account_id="A1", is_ring_member=True, dataset_source="demo"))
    db_session.commit()
    fetched = db_session.query(Account).filter_by(account_id="A1").first()
    assert fetched is not None
    assert fetched.is_ring_member is True


def test_transaction_round_trip(db_session):
    from datetime import datetime
    db_session.add(Transaction(
        transaction_id="T1", sender="A", receiver="B", amount=100.0,
        timestamp=datetime(2026, 1, 1), label=1, scenario_id="R1", ring_id="R1", dataset_source="demo",
    ))
    db_session.commit()
    fetched = db_session.query(Transaction).filter_by(transaction_id="T1").first()
    assert fetched.amount == 100.0
    assert fetched.label == 1


def test_ring_candidate_and_risk_score_foreign_key(db_session):
    db_session.add(RingCandidateRow(
        candidate_ring_id="RING001", accounts_json="[]", transaction_ids_json="[]",
        time_span_start="2026-01-01", time_span_end="2026-01-05", patterns_json="[]",
        trajectory_json="{}", network_statistics_json="{}", formation_stage="WATCH",
        formation_stage_is_provisional=True, risk_score=None, evidence_event_count=0,
        source_trajectory_id="TRAJ0001",
    ))
    db_session.commit()

    db_session.add(RiskScoreRow(
        candidate_ring_id="RING001", risk_score=75.0, risk_level="HIGH",
        score_components_json="{}", top_factors_json="[]",
    ))
    db_session.commit()

    joined = (
        db_session.query(RingCandidateRow, RiskScoreRow)
        .join(RiskScoreRow, RingCandidateRow.candidate_ring_id == RiskScoreRow.candidate_ring_id)
        .first()
    )
    assert joined is not None
    candidate, risk = joined
    assert candidate.candidate_ring_id == risk.candidate_ring_id


def test_risk_score_none_is_never_fabricated_in_db(db_session):
    db_session.add(RingCandidateRow(
        candidate_ring_id="RING002", accounts_json="[]", transaction_ids_json="[]",
        time_span_start="2026-01-01", time_span_end="2026-01-05", patterns_json="[]",
        trajectory_json="{}", network_statistics_json="{}", formation_stage="WATCH",
        formation_stage_is_provisional=True, risk_score=None, evidence_event_count=0,
        source_trajectory_id="TRAJ0002",
    ))
    db_session.commit()
    fetched = db_session.query(RingCandidateRow).filter_by(candidate_ring_id="RING002").first()
    assert fetched.risk_score is None
