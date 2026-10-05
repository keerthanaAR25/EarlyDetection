#!/usr/bin/env python3
"""
Generate SHAP global/local explanations for the proposed model and
forensic (WHO/WHAT/WHEN/WHERE/HOW/WHY) explanations for every ring
candidate, using its real risk score from Phase 12.

Usage:
    python scripts/generate_explanations.py
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
from src.explainability.shap_explainer import ShapExplainer
from src.explainability.forensic_explainer import build_forensic_explanation
from src.ring.ring_candidate_engine import RingCandidate
from src.scoring.risk_engine import RiskScoreResult


def main():
    with open(ROOT / "configs" / "config.yaml") as f:
        config = yaml.safe_load(f)

    df = pd.read_csv(ROOT / "data" / "processed" / "transactions_clean.csv", parse_dates=["timestamp"], dtype={"transaction_id": str, "sender": str, "receiver": str, "scenario_id": str, "ring_id": str})
    features = downcast_numeric(pd.read_csv(ROOT / "data" / "processed" / "features.csv", dtype={"account_id": str}))

    builder = TemporalGraphBuilder(df, config["temporal"]["window_size"], config["temporal"]["step_size"])
    bounds = builder.generate_window_bounds()
    labels = build_forecast_labels(df, bounds, horizon=config["evaluation"]["forecast_horizon_windows"])
    full = attach_labels(features, labels)
    splits = chronological_split(full, config["split"]["train_fraction"], config["split"]["val_fraction"])

    model = ProposedEarlyWarningModel(random_state=config["project"]["seed"])
    model.fit(splits["train"])
    print(f"Trained {model.backend} model on {len(splits['train'])} rows")

    explainer = ShapExplainer(model)
    eval_df = splits["test"] if len(splits["test"]) else splits["train"]
    global_importance = explainer.global_feature_importance(eval_df, top_n=15)
    print("\nGlobal SHAP feature importance (top 15):")
    for item in global_importance:
        print(f"  {item['feature']}: {item['mean_abs_shap']:.4f}")

    out_dir = ROOT / "results"
    with open(out_dir / "shap_global_importance.json", "w") as f:
        json.dump(global_importance, f, indent=2)

    with open(out_dir / "ring_candidates.json") as f:
        candidate_dicts = json.load(f)
    candidates = [RingCandidate(**d) for d in candidate_dicts]

    with open(out_dir / "risk_scores.json") as f:
        risk_dicts = json.load(f)
    risk_by_id = {r["candidate_ring_id"]: RiskScoreResult(**r) for r in risk_dicts}

    forensic_explanations = []
    for c in candidates:
        risk_result = risk_by_id.get(c.candidate_ring_id)
        explanation = build_forensic_explanation(c, risk_result=risk_result)
        forensic_explanations.append(explanation.to_dict())

    with open(out_dir / "forensic_explanations.json", "w") as f:
        json.dump(forensic_explanations, f, indent=2, default=str)

    print(f"\n{len(forensic_explanations)} forensic explanations generated")
    top = max(forensic_explanations, key=lambda e: e["why"].get("risk_score") or 0)
    print(f"\nExample — highest-risk candidate ({top['candidate_ring_id']}):")
    print(f"  WHO:   {top['who']['n_accounts']} accounts")
    print(f"  WHAT:  {top['what']['description']}")
    print(f"  WHEN:  {top['when']['time_span_start']} -> {top['when']['time_span_end']} "
          f"(stage: {top['when']['formation_stage']}, provisional)")
    print(f"  WHY:   {top['why']['risk_score']}/100 ({top['why']['risk_level']}) — {top['why']['top_factors'][0]}")
    print(f"  HOW EARLY: {top['how_early']['note']}")

    print(f"\nWrote {out_dir / 'shap_global_importance.json'}")
    print(f"Wrote {out_dir / 'forensic_explanations.json'}")


if __name__ == "__main__":
    main()
