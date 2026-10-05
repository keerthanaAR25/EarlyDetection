"""
Phase 10 tests: chronological split, account-window labels, baselines.

Run with: pytest tests/test_baselines.py -v
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.models.data_split import chronological_split
from src.models.labels import build_account_window_labels, attach_labels
from src.models.baseline_static import StaticGraphAnomalyBaseline
from src.models.baseline_behavioural import BehaviouralMLBaseline
from src.models.baseline_temporal import TemporalAnalyticalBaseline
from src.evaluation.metrics import compute_classification_metrics
from src.graph.temporal_graph import WindowBounds


def _tx(tid, sender, receiver, amount, day, label=0):
    return {
        "transaction_id": tid, "sender": sender, "receiver": receiver, "amount": amount,
        "timestamp": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=day),
        "label": label, "scenario_id": "", "ring_id": "", "dataset_source": "unit_test",
    }


def test_chronological_split_never_shuffles():
    df = pd.DataFrame({"window_id": list(range(10)), "account_id": [f"A{i}" for i in range(10)]})
    splits = chronological_split(df, train_fraction=0.6, val_fraction=0.2)
    assert splits["train_window_range"][1] < splits["val_window_range"][0]
    assert splits["val_window_range"][1] < splits["test_window_range"][0]


def test_chronological_split_respects_fractions():
    df = pd.DataFrame({"window_id": list(range(100)), "account_id": [f"A{i}" for i in range(100)]})
    splits = chronological_split(df, train_fraction=0.6, val_fraction=0.2)
    assert len(splits["train"]) == 60
    assert len(splits["val"]) == 20
    assert len(splits["test"]) == 20


def test_account_window_labels_leak_safe():
    df = pd.DataFrame([
        _tx("T1", "A", "B", 100, day=0, label=1),
        _tx("T2", "C", "D", 100, day=1, label=0),
    ])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    bounds = [
        WindowBounds(0, pd.Timestamp("2026-01-01", tz="UTC"), pd.Timestamp("2026-01-02", tz="UTC")),
        WindowBounds(1, pd.Timestamp("2026-01-02", tz="UTC"), pd.Timestamp("2026-01-03", tz="UTC")),
    ]
    labels = build_account_window_labels(df, bounds)

    window0 = labels[labels["window_id"] == 0]
    assert set(window0[window0["y"] == 1]["account_id"]) == {"A", "B"}
    window1 = labels[labels["window_id"] == 1]
    assert (window1["y"] == 0).all()


def test_attach_labels_fills_missing_with_zero():
    features = pd.DataFrame({"window_id": [0, 0], "account_id": ["A", "Z"], "x": [1, 2]})
    labels = pd.DataFrame({"window_id": [0], "account_id": ["A"], "y": [1]})
    merged = attach_labels(features, labels)
    assert merged[merged["account_id"] == "A"]["y"].iloc[0] == 1
    assert merged[merged["account_id"] == "Z"]["y"].iloc[0] == 0


def _synthetic_feature_df(n=200, seed=0):
    rng = np.random.default_rng(seed)
    n_pos = max(int(n * 0.1), 2)
    y = np.array([1] * n_pos + [0] * (n - n_pos))
    rng.shuffle(y)

    df = pd.DataFrame({
        "window_id": rng.integers(0, 5, n),
        "account_id": [f"A{i}" for i in range(n)],
        "y": y,
    })
    cols = [
        "in_degree", "out_degree", "total_degree", "weighted_in_degree", "weighted_out_degree",
        "degree_ratio_out_in", "pagerank", "betweenness_centrality", "clustering_coefficient",
        "component_size", "neighbor_count", "intermediary_balance_ratio",
        "out_count", "out_amount", "out_amount_mean", "out_amount_median", "out_amount_std",
        "in_count", "in_amount", "in_amount_mean", "in_amount_median", "in_amount_std",
        "unique_receivers", "unique_senders", "repeated_receiver_count", "repeated_sender_count",
        "out_amount_concentration", "total_count", "total_amount", "log_total_amount",
        "amount_ratio_out_in", "unique_counterparties", "transaction_velocity",
        "median_time_gap_seconds", "min_time_gap_seconds", "max_time_gap_seconds", "burstiness",
        "activity_acceleration", "activity_trend_slope", "recent_vs_historical_activity",
        "activity_persistence_windows", "delta_total_degree", "delta_weighted_in_degree",
        "delta_weighted_out_degree", "delta_pagerank", "delta_component_size", "delta_neighbor_count",
        "delta_total_count", "delta_total_amount", "delta_transaction_velocity", "delta_connectivity",
    ]
    for col in cols:
        base = rng.normal(0, 1, n)
        df[col] = base + df["y"] * 3.0
    return df


def test_static_baseline_fits_unsupervised_and_scores_in_unit_range():
    df = _synthetic_feature_df()
    model = StaticGraphAnomalyBaseline(random_state=1)
    model.fit(df)
    scores = model.predict_score(df)
    assert len(scores) == len(df)
    assert scores.min() >= 0.0 - 1e-9
    assert scores.max() <= 1.0 + 1e-9


def test_behavioural_baseline_separates_positive_and_negative():
    df = _synthetic_feature_df(n=300, seed=2)
    model = BehaviouralMLBaseline(random_state=1)
    model.fit(df)
    scores = model.predict_score(df)
    metrics = compute_classification_metrics(df["y"].to_numpy(), scores)
    assert metrics["roc_auc"] > 0.8


def test_behavioural_baseline_raises_on_zero_positives():
    df = _synthetic_feature_df(n=50, seed=3)
    df["y"] = 0
    model = BehaviouralMLBaseline()
    with pytest.raises(ValueError):
        model.fit(df)


def test_temporal_baseline_separates_and_exposes_importances():
    df = _synthetic_feature_df(n=300, seed=4)
    model = TemporalAnalyticalBaseline(random_state=1)
    model.fit(df)
    scores = model.predict_score(df)
    metrics = compute_classification_metrics(df["y"].to_numpy(), scores)
    assert metrics["roc_auc"] > 0.8
    importances = model.feature_importances()
    assert len(importances) > 0
    assert abs(sum(importances.values()) - 1.0) < 1e-6


def test_metrics_report_none_with_zero_positives_not_fabricated():
    y_true = np.zeros(50)
    y_score = np.random.rand(50)
    metrics = compute_classification_metrics(y_true, y_score)
    assert metrics["precision"] is None
    assert metrics["roc_auc"] is None
    assert "note" in metrics


def test_metrics_top_k_precision_computed_correctly():
    y_true = np.array([1, 1, 0, 0, 0])
    y_score = np.array([0.9, 0.8, 0.1, 0.2, 0.3])
    metrics = compute_classification_metrics(y_true, y_score, top_k=[2])
    assert metrics["top_k_precision"][2] == 1.0
