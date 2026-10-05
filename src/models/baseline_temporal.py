"""
Baseline 3: Temporal analytical baseline.

Supervised Random Forest on TEMPORAL + Δ (change) features only —
velocity, burstiness, trend, persistence, and window-to-window deltas
(see feature_groups.TEMPORAL_FEATURES, DELTA_FEATURES). Has temporal
awareness but no network/graph structure and no transaction-amount
behaviour — this is the direct comparison point for RQ3 ("does
temporal analysis improve early detection over static graph
analysis?") together with Baseline 1.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from src.models.feature_groups import TEMPORAL_FEATURES, DELTA_FEATURES


class TemporalAnalyticalBaseline:
    name = "temporal_random_forest"

    def __init__(self, random_state: int = 42):
        self.model = RandomForestClassifier(
            n_estimators=300, max_depth=8, class_weight="balanced", random_state=random_state
        )
        self.feature_cols = list(TEMPORAL_FEATURES) + list(DELTA_FEATURES)
        self._fitted_cols = None

    def fit(self, train_df: pd.DataFrame, y_col: str = "y"):
        cols = [c for c in self.feature_cols if c in train_df.columns]
        self._fitted_cols = cols
        X = train_df[cols].fillna(0).to_numpy()
        y = train_df[y_col].to_numpy()
        if y.sum() == 0:
            raise ValueError("Cannot fit a supervised baseline with zero positive examples in the training split.")
        self.model.fit(X, y)
        return self

    def predict_score(self, df: pd.DataFrame) -> np.ndarray:
        X = df[self._fitted_cols].fillna(0).to_numpy()
        return self.model.predict_proba(X)[:, 1]

    def feature_importances(self) -> dict:
        if self._fitted_cols is None:
            return {}
        return dict(zip(self._fitted_cols, self.model.feature_importances_.tolist()))
