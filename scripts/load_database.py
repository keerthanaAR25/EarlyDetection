#!/usr/bin/env python3
"""
Load every real artifact produced by scripts/ into the database.

This is the ONLY place fake data would sneak in if we let it — it
doesn't: every table is populated straight from files already written
by earlier phases' scripts, never invented here.

NOTE: the 51-column, multi-million-row feature table (features.csv)
is intentionally NOT mirrored into the relational DB — none of the
API endpoints need per-account-window feature blobs, and at real
AMLSim scale (2.69M rows) doing so caused an out-of-memory kill with
no benefit. features.csv remains the source of truth for offline
analysis; the DB holds the much smaller, API-relevant aggregates
(candidates, risk scores, evidence, pattern events, transactions).

Usage:
    python scripts/load_database.py
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.database.session import init_db, SessionLocal, DATABASE_URL
from backend.database.models import (
    Account, Transaction, GraphWindow, FeatureRow, PatternEventRow,
    RingCandidateRow, RiskScoreRow, EvidenceRow, Alert, ModelRun, EvaluationMetric,
)


def _load_json(path):
    with open(path) as f:
        return json.load(f)


def _chunked(iterable, size):
    buf = []
    for item in iterable:
        buf.append(item)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


def main():
    print(f"Target database: {DATABASE_URL}")
    init_db()
    db = SessionLocal()

    try:
        for model in [Alert, EvidenceRow, RiskScoreRow, RingCandidateRow, PatternEventRow,
                      FeatureRow, GraphWindow, Transaction, Account, ModelRun, EvaluationMetric]:
            db.query(model).delete()
        db.commit()

        with open(ROOT / "configs" / "config.yaml") as f:
            config = yaml.safe_load(f)
        active_dataset = config["dataset"]["active"]

        tx_df = pd.read_csv(
            ROOT / "data" / "processed" / "transactions_clean.csv", parse_dates=["timestamp"],
            dtype={"transaction_id": str, "sender": str, "receiver": str, "scenario_id": str, "ring_id": str},
        )

        if active_dataset == "amlsim":
            accounts_df = pd.read_csv(ROOT / "data" / "raw" / "amlsim" / "accounts.csv", dtype=str)
            accounts_df = accounts_df.rename(columns={"acct_id": "account_id"})[["account_id"]]
            alert_accts = set(pd.read_csv(ROOT / "data" / "raw" / "amlsim" / "alert_accounts.csv", dtype=str)["acct_id"])
            accounts_df["is_ring_member"] = accounts_df["account_id"].isin(alert_accts)
        else:
            accounts_df = pd.read_csv(ROOT / "data" / "demo" / "accounts.csv")

        for chunk in _chunked(accounts_df.itertuples(index=False), 50000):
            db.bulk_save_objects([
                Account(account_id=row.account_id, is_ring_member=bool(row.is_ring_member), dataset_source=active_dataset)
                for row in chunk
            ])
        db.commit()

        for chunk in _chunked(tx_df.itertuples(index=False), 50000):
            db.bulk_save_objects([
                Transaction(
                    transaction_id=row.transaction_id, sender=row.sender, receiver=row.receiver,
                    amount=float(row.amount), timestamp=row.timestamp.to_pydatetime(), label=int(row.label),
                    scenario_id=row.scenario_id or None, ring_id=row.ring_id or None, dataset_source=row.dataset_source,
                )
                for row in chunk
            ])
        db.commit()
        print(f"Loaded {len(accounts_df)} accounts, {len(tx_df)} transactions")

        window_summary = _load_json(ROOT / "reports" / "tables" / "graph_window_summary.json")
        cumulative_summary = _load_json(ROOT / "reports" / "tables" / "graph_cumulative_summary.json")
        cum_by_id = {c["window_id"]: c for c in cumulative_summary}
        db.bulk_save_objects([
            GraphWindow(
                window_id=w["window_id"],
                window_start=datetime.fromisoformat(w["start"]),
                window_end=datetime.fromisoformat(w["end"]),
                n_nodes=w["n_nodes"], n_transactions=w["n_transactions"], total_amount=w["total_amount"],
                cumulative_n_nodes=cum_by_id.get(w["window_id"], {}).get("cumulative_n_nodes"),
                cumulative_n_transactions=cum_by_id.get(w["window_id"], {}).get("cumulative_n_transactions"),
                cumulative_density=cum_by_id.get(w["window_id"], {}).get("cumulative_density"),
            )
            for w in window_summary
        ])
        db.commit()
        print(f"Loaded {len(window_summary)} graph windows")

        pattern_events = _load_json(ROOT / "results" / "pattern_events.json")
        for chunk in _chunked(pattern_events, 20000):
            db.bulk_save_objects([
                PatternEventRow(
                    pattern_type=e["pattern_type"], window_id=e["window_id"], timestamp=e["timestamp"],
                    central_account=e["central_account"], accounts_json=json.dumps(e["accounts"]),
                    transaction_ids_json=json.dumps(e["transaction_ids"]), pattern_strength=e["pattern_strength"],
                    evidence_json=json.dumps(e["evidence"]),
                )
                for e in chunk
            ])
        db.commit()
        print(f"Loaded {len(pattern_events)} pattern events")

        candidates = _load_json(ROOT / "results" / "ring_candidates.json")
        risk_scores = _load_json(ROOT / "results" / "risk_scores.json")
        evidence_records = _load_json(ROOT / "results" / "evidence.json")

        db.bulk_save_objects([
            RingCandidateRow(
                candidate_ring_id=c["candidate_ring_id"], accounts_json=json.dumps(c["accounts"]),
                transaction_ids_json=json.dumps(c["transaction_ids"]),
                time_span_start=c["time_span"][0], time_span_end=c["time_span"][1],
                patterns_json=json.dumps(c["patterns"]), trajectory_json=json.dumps(c["trajectory"]),
                network_statistics_json=json.dumps(c["network_statistics"]),
                formation_stage=c["formation_stage"], formation_stage_is_provisional=c["formation_stage_is_provisional"],
                risk_score=c["risk_score"], evidence_event_count=c["evidence_event_count"],
                source_trajectory_id=c["source_trajectory_id"],
            )
            for c in candidates
        ])
        db.bulk_save_objects([
            RiskScoreRow(
                candidate_ring_id=r["candidate_ring_id"], risk_score=r["risk_score"], risk_level=r["risk_level"],
                score_components_json=json.dumps(r["score_components"]), top_factors_json=json.dumps(r["top_factors"]),
            )
            for r in risk_scores
        ])
        db.bulk_save_objects([
            EvidenceRow(
                candidate_ring_id=e["candidate_ring_id"], accounts_json=json.dumps(e["accounts"]),
                transactions_json=json.dumps(e["transactions"]), paths_json=json.dumps(e["paths"]),
                patterns_json=json.dumps(e["patterns"]), time_range_json=json.dumps(e["time_range"]),
                risk_factors_json=json.dumps(e["risk_factors"]), trajectory_json=json.dumps(e["trajectory"]),
                warning_time=e.get("warning_time"), observable_time=e.get("observable_time"),
                lead_time=e.get("lead_time"), evidence_subgraph_json=json.dumps(e["evidence_subgraph"]),
            )
            for e in evidence_records
        ])
        db.commit()
        print(f"Loaded {len(candidates)} ring candidates, {len(risk_scores)} risk scores, {len(evidence_records)} evidence records")

        alerts = [
            Alert(candidate_ring_id=r["candidate_ring_id"], risk_level=r["risk_level"], created_at=datetime.now(timezone.utc))
            for r in risk_scores if r["risk_level"] in ("HIGH", "CRITICAL")
        ]
        db.bulk_save_objects(alerts)
        db.commit()
        print(f"Loaded {len(alerts)} alerts (HIGH/CRITICAL risk candidates)")

        model_comparison = _load_json(ROOT / "results" / "model_comparison.json")
        for method, splits in model_comparison.items():
            for split_name, metrics in splits.items():
                db.add(EvaluationMetric(method=method, split=split_name, metrics_json=json.dumps(metrics)))

        db.commit()
        print("\nDatabase load complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
