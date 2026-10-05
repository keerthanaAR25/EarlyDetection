"""
Baseline 2: Transaction / behavioural ML.

Supervised Logistic Regression on TRANSACTION features only (amounts,
counts, counterparty concentration — see feature_groups.TRANSACTION_FEATURES).
No graph structure, no temporal dynamics — represents a conventional
"transaction monitoring" rule-learning approach.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from src.models.feature_groups import TRANSACTION_FEATURES


class BehaviouralMLBaseline:
    name = "behavioural_logistic_regression"

    def __init__(self, random_state: int = 42):
        self.model = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=random_state)
        self.scaler = StandardScaler()
        self.feature_cols = list(TRANSACTION_FEATURES)
        self._fitted_cols = None

    def fit(self, train_df: pd.DataFrame, y_col: str = "y"):
        cols = [c for c in self.feature_cols if c in train_df.columns]
        self._fitted_cols = cols
        X = train_df[cols].fillna(0).to_numpy()
        y = train_df[y_col].to_numpy()
        if y.sum() == 0:
            raise ValueError("Cannot fit a supervised baseline with zero positive examples in the training split.")
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)
        return self

    def predict_score(self, df: pd.DataFrame) -> np.ndarray:
        X = df[self._fitted_cols].fillna(0).to_numpy()
        X_scaled = self.scaler.transform(X)
        return self.model.predict_proba(X_scaled)[:, 1]
