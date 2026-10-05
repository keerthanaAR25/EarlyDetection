# Research Mapping: Gap -> Objective -> Module -> Metric

| Gap | Objective | Module | Experiment | Metric | Evidence |
|---|---|---|---|---|---|
| G1 Detection->Early | O4 | src/models/proposed_model.py + labels.py (forecast horizon) | compare_models.py | ROC-AUC, PR-AUC | results/model_comparison.json |
| G2 Structure->Formation | O1, O3 | src/ring/ring_candidate_engine.py | build_ring_candidates.py | n_accounts, patterns | results/ring_candidates.json |
| G3 Pattern->Trajectory | O2, O3 | src/temporal/trajectory.py | build_trajectories.py | pattern_combination_score | results/trajectory_features.csv |
| G4 Accuracy->Lead Time | O4 | src/evaluation/lead_time.py | compute_lead_time.py | mean/median lead_time, early_detection_rate | results/lead_time_summary.json |
| O5 Explainable risk | O5 | src/scoring/risk_engine.py, src/explainability/ | compute_risk_scores.py, generate_explanations.py | SHAP importance, score_components | results/shap_global_importance.json |

See docs/limitations.md for where real-data-scale results diverge
from demo-scale validation (primarily G2: candidate decomposition).
