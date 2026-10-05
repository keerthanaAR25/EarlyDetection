"""
Phase 16 tests: ablation study and pattern indicator features.

Run with: pytest tests/test_ablation.py -v
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.evaluation.ablation import run_ablation, ABLATION_CONFIGS
from src.features.pattern_indicator_features import build_pattern_indicator_features, attach_pattern_indicators
from src.models.feature_groups import FUND_FLOW_FEATURES, ALL_FEATURES


def test_ablation_configs_are_cumulative():
    """Each successive config (per spec: A -> F) should be a superset
    of the previous one's feature list — that's the entire point of an
    ablation study."""
    order = ["A_behavioural_only", "C_behavioural_network", "D_plus_temporal", "E_plus_fund_flow", "F_full_proposed"]
    for i in range(len(order) - 1):
        smaller = set(ABLATION_CONFIGS[order[i]])
        larger = set(ABLATION_CONFIGS[order[i + 1]])
        assert smaller.issubset(larger), f"{order[i]} should be a subset of {order[i+1]}"


def test_ablation_has_six_required_configs():
    assert len(ABLATION_CONFIGS) == 6
    for letter in ["A", "B", "C", "D", "E", "F"]:
        assert any(name.startswith(letter + "_") for name in ABLATION_CONFIGS)


def _synthetic_df(n=300, seed=0):
    rng = np.random.default_rng(seed)
    n_pos = max(int(n * 0.1), 3)
    y = np.array([1] * n_pos + [0] * (n - n_pos))
    rng.shuffle(y)
    df = pd.DataFrame({"window_id": rng.integers(0, 5, n), "account_id": [f"A{i}" for i in range(n)], "y": y})
    for col in ALL_FEATURES + FUND_FLOW_FEATURES:
        df[col] = rng.normal(0, 1, n) + df["y"] * 3.0
    return df


def test_run_ablation_produces_one_row_per_config():
    df = _synthetic_df()
    train, test = df.iloc[:200], df.iloc[200:]
    results = run_ablation(train, test, top_k=[10])
    assert len(results) == len(ABLATION_CONFIGS)
    assert set(results["config"]) == set(ABLATION_CONFIGS.keys())


def test_run_ablation_handles_zero_positive_train_gracefully():
    df = _synthetic_df(seed=1)
    train = df.copy()
    train["y"] = 0
    test = df.iloc[:50]
    results = run_ablation(train, test, top_k=[10])
    assert (results["note"].notna()).all()  # every row should carry the "skipped" note
    assert results["precision"].isna().all()


def test_combining_feature_groups_does_not_error_with_missing_columns():
    # Simulate a feature table that's missing some DELTA_FEATURES columns
    # (e.g. an early window with no prior data to diff against)
    df = _synthetic_df(seed=2)
    df = df.drop(columns=["delta_pagerank"])
    train, test = df.iloc[:200], df.iloc[200:]
    results = run_ablation(train, test, top_k=[10])
    f_row = results[results["config"] == "F_full_proposed"].iloc[0]
    assert f_row["n_features_missing"] == 1


# ------------------------------------------------------------ pattern indicators
def test_build_pattern_indicator_features_creates_correct_columns():
    events = pd.DataFrame([
        {"pattern_type": "fan_in", "window_id": 0, "accounts": "['C1', 'S1', 'S2']"},
        {"pattern_type": "circular_flow", "window_id": 2, "accounts": "['C1', 'C2']"},
    ])
    indicators = build_pattern_indicator_features(events)
    assert "pattern_fan_in" in indicators.columns
    assert "pattern_circular_flow" in indicators.columns

    c1_window0 = indicators[(indicators["account_id"] == "C1") & (indicators["window_id"] == 0)]
    assert c1_window0.iloc[0]["pattern_fan_in"] == 1


def test_build_pattern_indicator_features_empty_input():
    empty = pd.DataFrame(columns=["pattern_type", "window_id", "accounts"])
    indicators = build_pattern_indicator_features(empty)
    assert indicators.empty


def test_attach_pattern_indicators_fills_zero_for_uninvolved_accounts():
    features = pd.DataFrame({"window_id": [0, 0], "account_id": ["A", "B"], "x": [1, 2]})
    indicators = pd.DataFrame({"window_id": [0], "account_id": ["A"], "pattern_fan_in": [1]})
    merged = attach_pattern_indicators(features, indicators)
    assert merged[merged["account_id"] == "A"]["pattern_fan_in"].iloc[0] == 1
    assert merged[merged["account_id"] == "B"]["pattern_fan_in"].iloc[0] == 0
    # every FUND_FLOW_FEATURES column should exist even if never present in indicators
    for col in FUND_FLOW_FEATURES:
        assert col in merged.columns
