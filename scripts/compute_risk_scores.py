#!/usr/bin/env python3
"""
Train the proposed model, score every ring candidate's accounts with
it, and combine into explainable 0-100 risk scores.

Usage:
    python scripts/compute_risk_scores.py
"""
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.graph.temporal_graph import TemporalGraphBuilder
from src.models.labels import build_forecast_labels, attach_labels
from src.models.data_split import chronological_split
from src.models.feature_groups import downcast_numeric
from src.models.proposed_model import ProposedEarlyWarningModel
from src.ring.ring_candidate_engine import RingCandidate
from src.scoring.risk_engine import RiskScoringEngine


def main():
    with open(ROOT / "configs" / "config.yaml") as f:
        config = yaml.safe_load(f)

    df = pd.read_csv(ROOT / "data" / "processed" / "transactions_clean.csv", parse_dates=["timestamp"], dtype={"transaction_id": str, "sender": str, "receiver": str, "scenario_id": str, "ring_id": str})
    features = downcast_numeric(pd.read_csv(ROOT / "data" / "processed" / "features.csv", dtype={"account_id": str}))
    with open(ROOT / "results" / "ring_candidates.json") as f:
        candidate_dicts = json.load(f)
    candidates = [RingCandidate(**d) for d in candidate_dicts]
    print(f"Loaded {len(candidates)} ring candidates")

    builder = TemporalGraphBuilder(df, config["temporal"]["window_size"], config["temporal"]["step_size"])
    bounds = builder.generate_window_bounds()
    horizon = config["evaluation"]["forecast_horizon_windows"]
    labels = build_forecast_labels(df, bounds, horizon=horizon)
    full = attach_labels(features, labels)
    splits = chronological_split(full, config["split"]["train_fraction"], config["split"]["val_fraction"])

    model = ProposedEarlyWarningModel(random_state=config["project"]["seed"])
    model.fit(splits["train"])
    print(f"Trained proposed model ({model.backend}) on {len(splits['train'])} rows")

    full = full.copy()
    full["model_score"] = model.predict_score(full)
    account_scores = full.groupby("account_id")["model_score"].max()

    engine = RiskScoringEngine(config)
    results = engine.score_candidates(candidates, account_scores)

    score_by_id = {r.candidate_ring_id: r for r in results}
    for c in candidates:
        r = score_by_id[c.candidate_ring_id]
        c.risk_score = round(r.risk_score, 2)

    out_dir = ROOT / "results"
    with open(out_dir / "risk_scores.json", "w") as f:
        json.dump([r.to_dict() for r in results], f, indent=2)
    with open(out_dir / "ring_candidates.json", "w") as f:
        json.dump([c.to_dict() for c in candidates], f, indent=2, default=str)

    rows = [r.to_dict() for r in results]
    for row in rows:
        row["top_factor"] = row["top_factors"][0] if row["top_factors"] else ""
        del row["top_factors"]
        row.update(row.pop("score_components"))
    pd.DataFrame(rows).sort_values("risk_score", ascending=False).to_csv(out_dir / "risk_scores.csv", index=False)

    print("\nRisk scores (highest first):")
    for r in sorted(results, key=lambda x: -x.risk_score):
        print(f"  {r.candidate_ring_id}: {r.risk_score:.1f}/100 ({r.risk_level}) "
              f"[behav={r.score_components['behavioural']:.0f} net={r.score_components['network']:.0f} "
              f"flow={r.score_components['fund_flow']:.0f} persist={r.score_components['persistence']:.0f}]")
        print(f"      top factor: {r.top_factors[0]}")

    print(f"\nWrote {out_dir / 'risk_scores.json'}")
    print(f"Wrote {out_dir / 'risk_scores.csv'}")
    print(f"Updated {out_dir / 'ring_candidates.json'} with real risk_score values")


if __name__ == "__main__":
    main()
