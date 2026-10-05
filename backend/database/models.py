"""
SQLAlchemy ORM models, mirroring database/schema.sql.

JSON-shaped fields are stored as TEXT columns containing serialized
JSON for portability between SQLite and PostgreSQL — the API layer
deserializes them before returning to the frontend, so nothing about
this storage choice leaks into the API contract.
"""
from __future__ import annotations

from sqlalchemy import Column, String, Float, Integer, SmallInteger, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Account(Base):
    __tablename__ = "accounts"
    account_id = Column(String(64), primary_key=True)
    is_ring_member = Column(Boolean, default=False)
    dataset_source = Column(String(32))


class Transaction(Base):
    __tablename__ = "transactions"
    transaction_id = Column(String(64), primary_key=True)
    sender = Column(String(64), nullable=False, index=True)
    receiver = Column(String(64), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    label = Column(SmallInteger, nullable=False, default=-1)
    scenario_id = Column(String(64))
    ring_id = Column(String(64))
    dataset_source = Column(String(32))


class GraphWindow(Base):
    __tablename__ = "graph_windows"
    window_id = Column(Integer, primary_key=True)
    window_start = Column(DateTime, nullable=False)
    window_end = Column(DateTime, nullable=False)
    n_nodes = Column(Integer)
    n_transactions = Column(Integer)
    total_amount = Column(Float)
    cumulative_n_nodes = Column(Integer)
    cumulative_n_transactions = Column(Integer)
    cumulative_density = Column(Float)


class FeatureRow(Base):
    __tablename__ = "features"
    id = Column(Integer, primary_key=True, autoincrement=True)
    window_id = Column(Integer, nullable=False, index=True)
    account_id = Column(String(64), nullable=False, index=True)
    feature_json = Column(Text, nullable=False)


class PatternEventRow(Base):
    __tablename__ = "pattern_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    pattern_type = Column(String(32), nullable=False)
    window_id = Column(Integer, nullable=False, index=True)
    timestamp = Column(String(64))
    central_account = Column(String(64))
    accounts_json = Column(Text)
    transaction_ids_json = Column(Text)
    pattern_strength = Column(Float)
    evidence_json = Column(Text)


class RingCandidateRow(Base):
    __tablename__ = "ring_candidates"
    candidate_ring_id = Column(String(32), primary_key=True)
    accounts_json = Column(Text)
    transaction_ids_json = Column(Text)
    time_span_start = Column(String(64))
    time_span_end = Column(String(64))
    patterns_json = Column(Text)
    trajectory_json = Column(Text)
    network_statistics_json = Column(Text)
    formation_stage = Column(String(32))
    formation_stage_is_provisional = Column(Boolean)
    risk_score = Column(Float, nullable=True)
    evidence_event_count = Column(Integer)
    source_trajectory_id = Column(String(32))


class RiskScoreRow(Base):
    __tablename__ = "risk_scores"
    candidate_ring_id = Column(String(32), ForeignKey("ring_candidates.candidate_ring_id"), primary_key=True)
    risk_score = Column(Float)
    risk_level = Column(String(16))
    score_components_json = Column(Text)
    top_factors_json = Column(Text)


class EvidenceRow(Base):
    __tablename__ = "evidence"
    candidate_ring_id = Column(String(32), ForeignKey("ring_candidates.candidate_ring_id"), primary_key=True)
    accounts_json = Column(Text)
    transactions_json = Column(Text)
    paths_json = Column(Text)
    patterns_json = Column(Text)
    time_range_json = Column(Text)
    risk_factors_json = Column(Text)
    trajectory_json = Column(Text)
    warning_time = Column(String(64), nullable=True)
    observable_time = Column(String(64), nullable=True)
    lead_time = Column(Float, nullable=True)
    evidence_subgraph_json = Column(Text)


class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_ring_id = Column(String(32), ForeignKey("ring_candidates.candidate_ring_id"))
    risk_level = Column(String(16))
    created_at = Column(DateTime)


class ModelRun(Base):
    __tablename__ = "model_runs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(64))
    backend = Column(String(32))
    dataset_source = Column(String(32))
    trained_at = Column(DateTime)
    random_seed = Column(Integer)
    n_train_rows = Column(Integer)
    n_train_positive = Column(Integer)


class EvaluationMetric(Base):
    __tablename__ = "evaluation_metrics"
    id = Column(Integer, primary_key=True, autoincrement=True)
    method = Column(String(64))
    split = Column(String(16))
    metrics_json = Column(Text)
