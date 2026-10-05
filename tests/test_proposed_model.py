"""
Phase 11 tests: forecast-horizon labels and the proposed model.

Run with: pytest tests/test_proposed_model.py -v
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.models.labels import build_forecast_labels, build_account_window_labels
from src.models.proposed_model import ProposedEarlyWarningModel
from src.graph.temporal_graph import WindowBounds


def _tx(tid, sender, receiver, amount, day, label=0):
    return {
        "transaction_id": tid, "sender": sender, "receiver": receiver, "amount": amount,
        "timestamp": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=day),
        "label": label, "scenario_id": "", "ring_id": "", "dataset_source": "unit_test",
    }


def _bounds(n=6):
    return [
        WindowBounds(i, pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=i),
                     pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=i + 1))
        for i in range(n)
    ]


def test_forecast_label_is_positive_when_future_window_has_labeled_tx():
    rows = [
        _tx("T0", "A", "B", 50, day=0, label=0),
        _tx("T2", "A", "C", 500, day=2, label=1),
    ]
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    labels = build_forecast_labels(df, _bounds(), horizon=2)
    w0 = labels[(labels["window_id"] == 0) & (labels["account_id"] == "A")]
    assert w0.iloc[0]["y"] == 1


def test_forecast_label_is_negative_when_labeled_tx_outside_horizon():
    rows = [
        _tx("T0", "A", "B", 50, day=0, label=0),
        _tx("T5", "A", "C", 500, day=5, label=1),
    ]
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    labels = build_forecast_labels(df, _bounds(), horizon=2)
    w0 = labels[(labels["window_id"] == 0) & (labels["account_id"] == "A")]
    assert w0.iloc[0]["y"] == 0


def test_forecast_label_does_not_use_same_window_transaction_regression():
    """Regression test for the exact tautology bug found in verification:
    build_account_window_labels made the SAME window's own labeled
    transaction determine that window's label, which is trivially
    correlated with that window's own amount/velocity features (median
    total_amount 939.6 for positives vs 0.0 for negatives, in the SAME
    window). build_forecast_labels must never let a window's OWN
    transaction (rather than a FUTURE one) make it positive."""
    rows = [_tx("T0", "A", "B", 5000, day=0, label=1)]
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    same_window = build_account_window_labels(df, _bounds())
    forecast = build_forecast_labels(df, _bounds(), horizon=2)

    w0_same = same_window[(same_window["window_id"] == 0) & (same_window["account_id"] == "A")]
    w0_forecast = forecast[(forecast["window_id"] == 0) & (forecast["account_id"] == "A")]

    assert w0_same.iloc[0]["y"] == 1
    assert w0_forecast.iloc[0]["y"] == 0


def test_forecast_label_horizon_boundary_is_exclusive_of_current_window():
    rows = [_tx("T0", "A", "B", 5000, day=0, label=1)]
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    forecast = build_forecast_labels(df, _bounds(), horizon=3)
    w0 = forecast[(forecast["window_id"] == 0) & (forecast["account_id"] == "A")]
    assert w0.iloc[0]["y"] == 0


def _synthetic_df(n=300, seed=0):
    rng = np.random.default_rng(seed)
    n_pos = max(int(n * 0.1), 2)
    y = np.array([1] * n_pos + [0] * (n - n_pos))
    rng.shuffle(y)
    df = pd.DataFrame({"window_id": rng.integers(0, 5, n), "account_id": [f"A{i}" for i in range(n)], "y": y})
    from src.models.feature_groups import ALL_FEATURES
    for col in ALL_FEATURES:
        df[col] = rng.normal(0, 1, n) + df["y"] * 3.0
    return df


def test_proposed_model_fits_and_scores():
    df = _synthetic_df()
    model = ProposedEarlyWarningModel(random_state=1)
    model.fit(df)
    scores = model.predict_score(df)
    assert len(scores) == len(df)
    assert ((scores >= 0) & (scores <= 1)).all()


def test_proposed_model_feature_importances_sum_to_one():
    df = _synthetic_df(seed=2)
    model = ProposedEarlyWarningModel(random_state=1)
    model.fit(df)
    importances = model.feature_importances()
    assert abs(sum(importances.values()) - 1.0) < 1e-4


def test_proposed_model_raises_on_zero_positives():
    df = _synthetic_df(seed=3)
    df["y"] = 0
    model = ProposedEarlyWarningModel()
    with pytest.raises(ValueError):
        model.fit(df)


def test_proposed_model_reports_its_backend():
    model = ProposedEarlyWarningModel()
    assert model.backend in ("xgboost", "sklearn_gradient_boosting")
