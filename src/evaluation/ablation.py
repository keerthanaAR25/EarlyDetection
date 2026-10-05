"""
Ablation Study (Phase 16). MANDATORY per the project spec.

Runs 6 feature configurations through the SAME classifier (XGBoost,
same hyperparameters as the proposed model) and the SAME chronological
split + forecast-horizon label, so differences in results are
attributable to the feature set, not to comparing different model
classes (that comparison already happened in Phase 10/11's baseline
comparison — this is a different question).

Configs:
  A: Behavioural only            (TRANSACTION_FEATURES)
  B: Network only                (NETWORK_FEATURES)
  C: Behavioural + Network       (A + B)
  D: + Temporal                  (C + TEMPORAL_FEATURES)
  E: + Fund-flow patterns        (D + FUND_FLOW_FEATURES)
  F: Full proposed framework     (E + DELTA_FEATURES)
"""
from __future__ import annotations

import pandas as pd

from src.models.feature_groups import (
    NETWORK_FEATURES, TRANSACTION_FEATURES, TEMPORAL_FEATURES, DELTA_FEATURES, FUND_FLOW_FEATURES,
)
from src.evaluation.metrics import compute_classification_metrics

try:
    import xgboost as xgb
    _HAS_XGBOOST = True
except ImportError:
    from sklearn.ensemble import GradientBoostingClassifier
    _HAS_XGBOOST = False


ABLATION_CONFIGS = {
    "A_behavioural_only": list(TRANSACTION_FEATURES),
    "B_network_only": list(NETWORK_FEATURES),
    "C_behavioural_network": list(TRANSACTION_FEATURES) + list(NETWORK_FEATURES),
    "D_plus_temporal": list(TRANSACTION_FEATURES) + list(NETWORK_FEATURES) + list(TEMPORAL_FEATURES),
    "E_plus_fund_flow": (
        list(TRANSACTION_FEATURES) + list(NETWORK_FEATURES) + list(TEMPORAL_FEATURES) + list(FUND_FLOW_FEATURES)
    ),
    "F_full_proposed": (
        list(TRANSACTION_FEATURES) + list(NETWORK_FEATURES) + list(TEMPORAL_FEATURES)
        + list(FUND_FLOW_FEATURES) + list(DELTA_FEATURES)
    ),
}


def _make_classifier(random_state: int = 42):
    if _HAS_XGBOOST:
        return xgb.XGBClassifier(
            n_estimators=300, max_depth=5, learning_rate=0.05, subsample=0.8,
            colsample_bytree=0.8, eval_metric="aucpr", random_state=random_state,
        )
    return GradientBoostingClassifier(n_estimators=300, max_depth=3, learning_rate=0.05, random_state=random_state)


def run_ablation(train_df: pd.DataFrame, test_df: pd.DataFrame, top_k: list, random_state: int = 42) -> pd.DataFrame:
    rows = []

    for config_name, feature_cols in ABLATION_CONFIGS.items():
        available = [c for c in feature_cols if c in train_df.columns]
        missing = set(feature_cols) - set(available)

        row = {
            "config": config_name, "n_features": len(available), "n_features_missing": len(missing),
            "precision": None, "recall": None, "f1": None, "roc_auc": None, "pr_auc": None,
            "false_warning_rate": None, "note": None,
        }

        y_train = train_df["y"].to_numpy()
        if y_train.sum() == 0 or not available:
            row["note"] = "Skipped: no positive examples in train or no available features"
            rows.append(row)
            continue

        model = _make_classifier(random_state)
        X_train = train_df[available].fillna(0).to_numpy(dtype="float32")
        if _HAS_XGBOOST:
            n_pos, n_neg = y_train.sum(), len(y_train) - y_train.sum()
            model.set_params(scale_pos_weight=max(n_neg / max(n_pos, 1), 1.0))
        model.fit(X_train, y_train)
        del X_train

        X_test = test_df[available].fillna(0).to_numpy(dtype="float32")
        scores = model.predict_proba(X_test)[:, 1]
        del X_test, model
        import gc
        gc.collect()
        metrics = compute_classification_metrics(test_df["y"].to_numpy(), scores, top_k=top_k)

        row.update({
            "precision": metrics.get("precision"),
            "recall": metrics.get("recall"),
            "f1": metrics.get("f1"),
            "roc_auc": metrics.get("roc_auc"),
            "pr_auc": metrics.get("pr_auc"),
            "false_warning_rate": metrics.get("false_warning_rate"),
            "note": metrics.get("note"),
        })
        rows.append(row)

    return pd.DataFrame(rows)
