"""
Phase 12 tests: risk scoring engine.

Run with: pytest tests/test_risk_scoring.py -v
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ring.ring_candidate_engine import RingCandidate
from src.scoring.risk_engine import RiskScoringEngine, _risk_level, _behavioural_component


def _config(weights=None):
    return {
        "risk_scoring": {
            "thresholds": {"low": [0, 24], "moderate": [25, 49], "high": [50, 74], "critical": [75, 100]},
            "component_weights": weights or {"behavioural": 0.35, "network": 0.20, "fund_flow": 0.25, "persistence": 0.20},
        }
    }


def _candidate(cid, accounts, patterns, evidence_event_count, density):
    return RingCandidate(
        candidate_ring_id=cid,
        accounts=accounts,
        transaction_ids=[f"T{i}" for i in range(evidence_event_count)],
        time_span=["2026-01-01T00:00:00", "2026-01-05T00:00:00"],
        patterns=patterns,
        trajectory={},
        network_statistics={"density": density},
        formation_stage="WATCH",
        evidence_event_count=evidence_event_count,
    )


def test_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        RiskScoringEngine(_config(weights={"behavioural": 0.5, "network": 0.5, "fund_flow": 0.5, "persistence": 0.5}))


def test_risk_level_boundary_regression():
    """Regression test for the exact bug found in verification: a score
    of 74.4 fell into neither the inclusive [50,74] 'high' band nor the
    [75,100] 'critical' band under a literal lo<=score<=hi check, and
    was reported as 'UNKNOWN'. Every score in [0,100] must map to a
    real level."""
    thresholds = {"low": [0, 24], "moderate": [25, 49], "high": [50, 74], "critical": [75, 100]}
    for score in [0, 24, 24.9, 25, 49.9, 50, 74, 74.4, 74.999, 75, 100]:
        level = _risk_level(score, thresholds)
        assert level != "UNKNOWN", f"score {score} should map to a real band"


def test_risk_level_bands_are_correctly_ordered():
    thresholds = {"low": [0, 24], "moderate": [25, 49], "high": [50, 74], "critical": [75, 100]}
    assert _risk_level(10, thresholds) == "LOW"
    assert _risk_level(30, thresholds) == "MODERATE"
    assert _risk_level(60, thresholds) == "HIGH"
    assert _risk_level(90, thresholds) == "CRITICAL"


def test_behavioural_component_uses_mean_not_max_regression():
    """Regression test for the exact bug found in verification: using
    max() over a candidate's account scores meant a single high-scoring
    account saturated the component to ~100 regardless of how weak the
    rest of the evidence was. mean() must actually differ between a
    uniformly-high-scoring group and a mostly-low one with an outlier."""
    uniform_high = pd.Series([0.9, 0.85, 0.92, 0.88], index=["A", "B", "C", "D"])
    mostly_low_one_outlier = pd.Series([0.05, 0.02, 0.03, 0.99], index=["A", "B", "C", "D"])

    score_high, _ = _behavioural_component(["A", "B", "C", "D"], uniform_high)
    score_outlier, _ = _behavioural_component(["A", "B", "C", "D"], mostly_low_one_outlier)

    assert score_high > 80
    assert score_outlier < 30
    assert score_high > score_outlier + 40


def test_behavioural_component_handles_missing_accounts():
    scores = pd.Series([0.5], index=["A"])
    result, reason = _behavioural_component(["Z", "Y"], scores)
    assert result == 0.0
    assert "No model score" in reason


def test_clean_candidate_scores_higher_than_diluted_one():
    """End-to-end sanity check mirroring the real verification finding."""
    engine = RiskScoringEngine(_config())

    clean = _candidate("RING_CLEAN", [f"A{i}" for i in range(14)],
                        ["fan_in", "layering", "fan_out", "circular_flow"], evidence_event_count=8, density=0.10)
    diluted = _candidate("RING_DILUTED", [f"B{i}" for i in range(150)],
                          ["fan_in", "layering", "fan_out", "circular_flow"], evidence_event_count=8, density=0.02)

    account_scores = pd.Series(
        {**{f"A{i}": 0.8 for i in range(14)}, **{f"B{i}": 0.05 for i in range(150)}}
    )

    results = engine.score_candidates([clean, diluted], account_scores)
    by_id = {r.candidate_ring_id: r for r in results}
    assert by_id["RING_CLEAN"].risk_score > by_id["RING_DILUTED"].risk_score


def test_score_components_and_top_factors_are_populated():
    engine = RiskScoringEngine(_config())
    cand = _candidate("R1", ["A", "B", "C"], ["fan_in", "circular_flow"], evidence_event_count=4, density=0.1)
    scores = pd.Series({"A": 0.5, "B": 0.6, "C": 0.4})
    result = engine.score_candidates([cand], scores)[0]
    assert set(result.score_components.keys()) == {"behavioural", "network", "fund_flow", "persistence"}
    assert len(result.top_factors) == 4
    assert 0 <= result.risk_score <= 100


def test_risk_score_never_fabricated_matches_weighted_sum():
    engine = RiskScoringEngine(_config())
    cand = _candidate("R1", ["A", "B"], ["fan_in"], evidence_event_count=2, density=0.05)
    scores = pd.Series({"A": 0.5, "B": 0.5})
    result = engine.score_candidates([cand], scores)[0]
    expected = sum(result.score_components[k] * engine.weights[k] for k in result.score_components)
    assert abs(result.risk_score - expected) < 1e-6
