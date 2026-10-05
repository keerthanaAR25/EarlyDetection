"""
Query service layer (Phase 19).

All database access lives here, separated from route handlers in
backend/api/ so routes stay thin.

All dashboard responses are backed by the real SQLite database and
the generated evaluation results.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database.models import (
    Account,
    Transaction,
    RingCandidateRow,
    RiskScoreRow,
    EvidenceRow,
    PatternEventRow,
    EvaluationMetric,
)


# -------------------------------------------------------------------
# JSON helpers
# -------------------------------------------------------------------

def _j(text, default=None):
    """
    Safely decode JSON stored in database text columns.
    """
    if text is None:
        return default

    if isinstance(text, (dict, list)):
        return text

    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _risk_for_candidate(db: Session, candidate_ring_id: str):
    """
    Return the risk-score row associated with a candidate.
    """
    return (
        db.query(RiskScoreRow)
        .filter(
            RiskScoreRow.candidate_ring_id == candidate_ring_id
        )
        .first()
    )


# -------------------------------------------------------------------
# Candidate serialization
# -------------------------------------------------------------------

def candidate_to_dict(
    row: RingCandidateRow,
    risk: RiskScoreRow | None = None,
) -> dict:
    """
    Convert a RingCandidateRow into the API representation.

    Risk information is optionally supplied separately because the
    candidate table and risk-score table are separate database tables.
    """

    accounts = _j(row.accounts_json, [])
    transaction_ids = _j(row.transaction_ids_json, [])
    patterns = _j(row.patterns_json, [])
    trajectory = _j(row.trajectory_json, {})
    network_statistics = _j(
        row.network_statistics_json,
        {},
    )

    return {
        "candidate_ring_id": row.candidate_ring_id,

        "accounts": accounts,
        "n_accounts": len(accounts),

        "transaction_ids": transaction_ids,

        "time_span": [
            row.time_span_start,
            row.time_span_end,
        ],

        "patterns": patterns,

        "trajectory": trajectory,

        "network_statistics": network_statistics,

        "formation_stage": row.formation_stage,

        "formation_stage_is_provisional":
            row.formation_stage_is_provisional,

        "risk_score": (
            risk.risk_score
            if risk is not None
            else (
                row.risk_score
                if row.risk_score is not None
                else "Not yet evaluated"
            )
        ),

        "risk_level": (
            risk.risk_level
            if risk is not None
            else None
        ),

        "evidence_event_count":
            row.evidence_event_count,

        "source_trajectory_id":
            row.source_trajectory_id,

        "top_factors": (
            _j(risk.top_factors_json, [])
            if risk is not None
            else []
        ),

        "score_components": (
            _j(risk.score_components_json, {})
            if risk is not None
            else {}
        ),
    }


# -------------------------------------------------------------------
# Executive summary
# -------------------------------------------------------------------

def get_summary(db: Session) -> dict:
    n_transactions = (
        db.query(
            func.count(Transaction.transaction_id)
        ).scalar()
    )

    n_accounts = (
        db.query(
            func.count(Account.account_id)
        ).scalar()
    )

    n_candidates = (
        db.query(
            func.count(
                RingCandidateRow.candidate_ring_id
            )
        ).scalar()
    )

    n_high = (
        db.query(
            func.count(
                RiskScoreRow.candidate_ring_id
            )
        )
        .filter(
            RiskScoreRow.risk_level == "HIGH"
        )
        .scalar()
    )

    n_critical = (
        db.query(
            func.count(
                RiskScoreRow.candidate_ring_id
            )
        )
        .filter(
            RiskScoreRow.risk_level == "CRITICAL"
        )
        .scalar()
    )

    n_moderate = (
        db.query(
            func.count(
                RiskScoreRow.candidate_ring_id
            )
        )
        .filter(
            RiskScoreRow.risk_level == "MODERATE"
        )
        .scalar()
    )

    avg_risk = (
        db.query(
            func.avg(RiskScoreRow.risk_score)
        ).scalar()
    )

    return {
        "total_transactions": n_transactions or 0,
        "total_accounts": n_accounts or 0,

        "candidate_rings": n_candidates or 0,

        "high_risk": n_high or 0,
        "critical_risk": n_critical or 0,
        "moderate_risk": n_moderate or 0,

        "average_risk_score": (
            round(float(avg_risk), 2)
            if avg_risk is not None
            else None
        ),
    }


# -------------------------------------------------------------------
# Alerts
# -------------------------------------------------------------------

def list_alerts(
    db: Session,
    risk_level: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list:

    q = (
        db.query(
            RingCandidateRow,
            RiskScoreRow,
        )
        .join(
            RiskScoreRow,
            RingCandidateRow.candidate_ring_id
            == RiskScoreRow.candidate_ring_id,
        )
    )

    if risk_level:
        q = q.filter(
            RiskScoreRow.risk_level
            == risk_level.upper()
        )

    rows = (
        q.order_by(
            RiskScoreRow.risk_score.desc()
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    results = []

    for candidate, risk in rows:

        results.append(
            candidate_to_dict(
                candidate,
                risk,
            )
        )

    return results


# -------------------------------------------------------------------
# Ring candidates
# -------------------------------------------------------------------

def list_ring_candidates(
    db: Session,
    limit: int = 50,
    offset: int = 0,
) -> list:

    rows = (
        db.query(
            RingCandidateRow,
            RiskScoreRow,
        )
        .outerjoin(
            RiskScoreRow,
            RingCandidateRow.candidate_ring_id
            == RiskScoreRow.candidate_ring_id,
        )
        .order_by(
            RiskScoreRow.risk_score.desc().nullslast()
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        candidate_to_dict(
            candidate,
            risk,
        )
        for candidate, risk in rows
    ]


def get_ring_candidate(
    db: Session,
    ring_id: str,
):
    row = (
        db.query(
            RingCandidateRow,
            RiskScoreRow,
        )
        .outerjoin(
            RiskScoreRow,
            RingCandidateRow.candidate_ring_id
            == RiskScoreRow.candidate_ring_id,
        )
        .filter(
            RingCandidateRow.candidate_ring_id
            == ring_id
        )
        .first()
    )

    if row is None:
        return None

    candidate, risk = row

    return candidate_to_dict(
        candidate,
        risk,
    )


# -------------------------------------------------------------------
# Ring evidence graph
# -------------------------------------------------------------------

def get_ring_graph(
    db: Session,
    ring_id: str,
):

    row = (
        db.query(EvidenceRow)
        .filter(
            EvidenceRow.candidate_ring_id
            == ring_id
        )
        .first()
    )

    if row is None:
        return None

    return _j(
        row.evidence_subgraph_json,
        {
            "nodes": [],
            "edges": [],
        },
    )


# -------------------------------------------------------------------
# Ring temporal timeline
# -------------------------------------------------------------------

def get_ring_timeline(
    db: Session,
    ring_id: str,
):

    candidate = (
        db.query(RingCandidateRow)
        .filter(
            RingCandidateRow.candidate_ring_id
            == ring_id
        )
        .first()
    )

    if candidate is None:
        return None

    trajectory = _j(
        candidate.trajectory_json,
        {},
    )

    return {
        "candidate_ring_id": ring_id,

        "pattern_sequence":
            trajectory.get(
                "pattern_sequence",
                [],
            ),

        "event_window_ids":
            trajectory.get(
                "event_window_ids",
                [],
            ),

        "pattern_count":
            trajectory.get(
                "pattern_count",
                0,
            ),

        "pattern_diversity":
            trajectory.get(
                "pattern_diversity",
                0,
            ),

        "n_transitions":
            trajectory.get(
                "n_transitions",
                0,
            ),

        "pattern_transitions":
            trajectory.get(
                "pattern_transitions",
                [],
            ),

        "pattern_escalation_steps":
            trajectory.get(
                "pattern_escalation_steps",
                0,
            ),

        "pattern_combination_score":
            trajectory.get(
                "pattern_combination_score",
                0,
            ),

        "has_structural_sequence":
            trajectory.get(
                "has_structural_sequence",
                False,
            ),

        "first_suspicious_pattern":
            trajectory.get(
                "first_suspicious_pattern"
            ),

        "latest_suspicious_pattern":
            trajectory.get(
                "latest_suspicious_pattern"
            ),
    }


# -------------------------------------------------------------------
# Ring patterns
# -------------------------------------------------------------------

def get_ring_patterns(
    db: Session,
    ring_id: str,
) -> list:

    candidate = (
        db.query(RingCandidateRow)
        .filter(
            RingCandidateRow.candidate_ring_id
            == ring_id
        )
        .first()
    )

    if candidate is None:
        return []

    accounts = set(
        _j(
            candidate.accounts_json,
            [],
        )
    )

    rows = (
        db.query(PatternEventRow)
        .order_by(
            PatternEventRow.window_id,
            PatternEventRow.timestamp,
        )
        .all()
    )

    matching = []

    for row in rows:

        row_accounts = set(
            _j(
                row.accounts_json,
                [],
            )
        )

        if not (
            row_accounts & accounts
        ):
            continue

        matching.append(
            {
                "pattern_type":
                    row.pattern_type,

                "window_id":
                    row.window_id,

                "timestamp":
                    row.timestamp,

                "central_account":
                    row.central_account,

                "accounts":
                    _j(
                        row.accounts_json,
                        [],
                    ),

                "pattern_strength":
                    row.pattern_strength,

                "evidence":
                    _j(
                        row.evidence_json,
                        {},
                    ),
            }
        )

        # Prevent an unnecessarily huge
        # response for the investigation UI.
        if len(matching) >= 500:
            break

    return matching


# -------------------------------------------------------------------
# Ring forensic evidence
# -------------------------------------------------------------------

def get_ring_evidence(
    db: Session,
    ring_id: str,
):

    row = (
        db.query(EvidenceRow)
        .filter(
            EvidenceRow.candidate_ring_id
            == ring_id
        )
        .first()
    )

    if row is None:
        return None

    return {
        "candidate_ring_id":
            row.candidate_ring_id,

        "accounts":
            _j(
                row.accounts_json,
                [],
            ),

        "transactions":
            _j(
                row.transactions_json,
                [],
            )[:500],

        "paths":
            _j(
                row.paths_json,
                [],
            ),

        "patterns":
            _j(
                row.patterns_json,
                [],
            ),

        "time_range":
            _j(
                row.time_range_json,
                [],
            ),

        "risk_factors":
            _j(
                row.risk_factors_json,
                {},
            ),

        "trajectory":
            _j(
                row.trajectory_json,
                {},
            ),

        "warning_time":
            row.warning_time,

        "observable_time":
            row.observable_time,

        "lead_time":
            row.lead_time,

        "evidence_subgraph":
            _j(
                row.evidence_subgraph_json,
                {},
            ),
    }


# -------------------------------------------------------------------
# Explainable risk
# -------------------------------------------------------------------

def get_ring_explanation(
    db: Session,
    ring_id: str,
):

    candidate = (
        db.query(RingCandidateRow)
        .filter(
            RingCandidateRow.candidate_ring_id
            == ring_id
        )
        .first()
    )

    risk = (
        db.query(RiskScoreRow)
        .filter(
            RiskScoreRow.candidate_ring_id
            == ring_id
        )
        .first()
    )

    if candidate is None:
        return None

    return {
        "candidate_ring_id":
            ring_id,

        "risk_score":
            risk.risk_score
            if risk
            else None,

        "risk_level":
            risk.risk_level
            if risk
            else None,

        "score_components":
            _j(
                risk.score_components_json,
                {},
            )
            if risk
            else {},

        "top_factors":
            _j(
                risk.top_factors_json,
                [],
            )
            if risk
            else [],

        "disclaimer":
            "A risk score indicates investigative priority "
            "and does not establish criminal guilt.",
    }


# -------------------------------------------------------------------
# Account details
# -------------------------------------------------------------------

def get_account(
    db: Session,
    account_id: str,
):

    account = (
        db.query(Account)
        .filter(
            Account.account_id
            == account_id
        )
        .first()
    )

    if account is None:
        return None

    tx_out = (
        db.query(
            func.count(
                Transaction.transaction_id
            )
        )
        .filter(
            Transaction.sender
            == account_id
        )
        .scalar()
    )

    tx_in = (
        db.query(
            func.count(
                Transaction.transaction_id
            )
        )
        .filter(
            Transaction.receiver
            == account_id
        )
        .scalar()
    )

    candidates = (
        db.query(RingCandidateRow)
        .all()
    )

    member_of = []

    for candidate in candidates:

        accounts = _j(
            candidate.accounts_json,
            [],
        )

        if account_id in accounts:
            member_of.append(
                candidate.candidate_ring_id
            )

    return {
        "account_id":
            account.account_id,

        "is_ring_member":
            account.is_ring_member,

        "dataset_source":
            account.dataset_source,

        "outgoing_transaction_count":
            tx_out or 0,

        "incoming_transaction_count":
            tx_in or 0,

        "ring_candidate_membership":
            member_of,
    }


# -------------------------------------------------------------------
# Transactions
# -------------------------------------------------------------------

def list_transactions(
    db: Session,
    account_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list:

    q = db.query(Transaction)

    if account_id:
        q = q.filter(
            (Transaction.sender == account_id)
            | (Transaction.receiver == account_id)
        )

    rows = (
        q.order_by(
            Transaction.timestamp.desc()
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        {
            "transaction_id":
                row.transaction_id,

            "sender":
                row.sender,

            "receiver":
                row.receiver,

            "amount":
                row.amount,

            "timestamp":
                row.timestamp.isoformat()
                if row.timestamp
                else None,

            "label":
                row.label,

            "ring_id":
                row.ring_id,
        }
        for row in rows
    ]


# -------------------------------------------------------------------
# Pattern events
# -------------------------------------------------------------------

def list_patterns(
    db: Session,
    pattern_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list:

    q = db.query(PatternEventRow)

    if pattern_type:
        q = q.filter(
            PatternEventRow.pattern_type
            == pattern_type
        )

    rows = (
        q.order_by(
            PatternEventRow.window_id,
            PatternEventRow.timestamp,
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        {
            "pattern_type":
                row.pattern_type,

            "window_id":
                row.window_id,

            "timestamp":
                row.timestamp,

            "central_account":
                row.central_account,

            "accounts":
                _j(
                    row.accounts_json,
                    [],
                ),

            "pattern_strength":
                row.pattern_strength,
        }
        for row in rows
    ]


# -------------------------------------------------------------------
# Model evaluation metrics
# -------------------------------------------------------------------

def get_metrics(
    db: Session,
) -> dict:

    rows = (
        db.query(
            EvaluationMetric
        )
        .all()
    )

    by_method = {}

    for row in rows:

        by_method.setdefault(
            row.method,
            {},
        )[row.split] = _j(
            row.metrics_json,
            {},
        )

    return by_method


# -------------------------------------------------------------------
# Lead-time evaluation
# -------------------------------------------------------------------

def get_lead_time_summary() -> dict:

    path = (
        Path(__file__).resolve().parents[2]
        / "results"
        / "lead_time_summary.json"
    )

    if not path.exists():

        return {
            "note":
                "Lead-time evaluation has not been generated yet."
        }

    try:

        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:

            return json.load(file)

    except (
        OSError,
        json.JSONDecodeError,
    ):

        return {
            "note":
                "Lead-time evaluation file could not be read."
        }


# -------------------------------------------------------------------
# Available models
# -------------------------------------------------------------------

def list_models(
    db: Session,
) -> list:

    rows = (
        db.query(
            EvaluationMetric.method
        )
        .distinct()
        .all()
    )

    return [
        row[0]
        for row in rows
    ]