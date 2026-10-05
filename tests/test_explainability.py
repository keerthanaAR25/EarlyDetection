"""
Phase 13 tests: SHAP explainer and forensic explanation.

Run with: pytest tests/test_explainability.py -v
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.models.proposed_model import ProposedEarlyWarningModel
from src.models.feature_groups import ALL_FEATURES
from src.explainability.shap_explainer import ShapExplainer
from src.explainability.forensic_explainer import build_forensic_explanation
from src.ring.ring_candidate_engine import RingCandidate
from src.scoring.risk_engine import RiskScoreResult


def _synthetic_df(n=200, seed=0):
    rng = np.random.default_rng(seed)
    n_pos = max(int(n * 0.15), 5)
    y = np.array([1] * n_pos + [0] * (n - n_pos))
    rng.shuffle(y)
    df = pd.DataFrame({"window_id": rng.integers(0, 5, n), "account_id": [f"A{i}" for i in range(n)], "y": y})
    for col in ALL_FEATURES:
        df[col] = rng.normal(0, 1, n) + df["y"] * 3.0
    return df


@pytest.fixture(scope="module")
def fitted_model_and_data():
    df = _synthetic_df()
    model = ProposedEarlyWarningModel(random_state=1)
    model.fit(df)
    return model, df


def test_global_feature_importance_returns_ranked_features(fitted_model_and_data):
    model, df = fitted_model_and_data
    explainer = ShapExplainer(model)
    importance = explainer.global_feature_importance(df, top_n=5)
    assert len(importance) == 5
    values = [item["mean_abs_shap"] for item in importance]
    assert values == sorted(values, reverse=True)


def test_local_explanation_has_positive_and_negative_factors(fitted_model_and_data):
    model, df = fitted_model_and_data
    explainer = ShapExplainer(model)
    pos_idx = df[df["y"] == 1].index[0]
    explanation = explainer.local_explanation(df, pos_idx)
    assert "predicted_score" in explanation
    assert 0 <= explanation["predicted_score"] <= 1
    assert isinstance(explanation["top_positive_factors"], list)
    assert isinstance(explanation["top_negative_factors"], list)


def test_local_explanations_differ_between_instances(fitted_model_and_data):
    model, df = fitted_model_and_data
    explainer = ShapExplainer(model)
    e1 = explainer.local_explanation(df, 0)
    e2 = explainer.local_explanation(df, 1)
    assert e1["predicted_score"] != e2["predicted_score"] or e1["top_positive_factors"] != e2["top_positive_factors"]


def test_waterfall_data_covers_all_fitted_features(fitted_model_and_data):
    model, df = fitted_model_and_data
    explainer = ShapExplainer(model)
    items = explainer.waterfall_data(df, 0)
    assert len(items) == len(model._fitted_cols)
    magnitudes = [abs(i["shap_contribution"]) for i in items]
    assert magnitudes == sorted(magnitudes, reverse=True)


def _candidate():
    return RingCandidate(
        candidate_ring_id="RING001",
        accounts=["C1", "S1", "S2", "C4", "D1"],
        transaction_ids=["T1", "T2", "T3"],
        time_span=["2026-01-03T00:00:00", "2026-01-07T00:00:00"],
        patterns=["fan_in", "layering", "fan_out", "circular_flow"],
        trajectory={"pattern_sequence": ["fan_in", "layering", "fan_out", "circular_flow"]},
        network_statistics={"density": 0.09, "n_nodes": 5},
        formation_stage="OBSERVABLE_RING",
        formation_stage_is_provisional=True,
        risk_score=None,
        evidence_event_count=4,
        source_trajectory_id="TRAJ0001",
    )


def test_forensic_explanation_covers_all_dimensions():
    exp = build_forensic_explanation(_candidate())
    d = exp.to_dict()
    assert set(d.keys()) == {"candidate_ring_id", "who", "what", "when", "where", "how", "why", "how_early"}
    assert d["who"]["n_accounts"] == 5
    assert "fan_in" in d["what"]["patterns_detected"]
    assert d["when"]["formation_stage"] == "OBSERVABLE_RING"


def test_forensic_explanation_how_early_is_honest_placeholder_not_fabricated():
    exp = build_forensic_explanation(_candidate())
    assert exp.how_early["lead_time"] is None
    assert exp.how_early["warning_time"] is None
    assert "Phase 15" in exp.how_early["note"]


def test_forensic_explanation_includes_disclaimer():
    exp = build_forensic_explanation(_candidate())
    assert "does not establish criminal guilt" in exp.why["disclaimer"]


def test_forensic_explanation_uses_real_risk_result_when_provided():
    risk_result = RiskScoreResult(
        candidate_ring_id="RING001", risk_score=78.5, risk_level="CRITICAL",
        score_components={"behavioural": 90, "network": 60, "fund_flow": 100, "persistence": 50},
        top_factors=["Strong behavioural signal", "Circular flow detected"],
    )
    exp = build_forensic_explanation(_candidate(), risk_result=risk_result)
    assert exp.why["risk_score"] == 78.5
    assert exp.why["risk_level"] == "CRITICAL"
    assert exp.why["top_factors"] == risk_result.top_factors


def test_pattern_description_is_readable_not_raw_codes():
    exp = build_forensic_explanation(_candidate())
    desc = exp.what["description"]
    assert "circular" in desc.lower() or "returning" in desc.lower()
    assert desc.endswith(".")
