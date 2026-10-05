"""
Baseline 1: Static graph anomaly detection.

Unsupervised Isolation Forest trained on NETWORK features only
(degree, PageRank, betweenness, clustering, component size — see
feature_groups.NETWORK_FEATURES), computed at a single point in time
with no awareness of how they changed. This represents the "detect
anomalies in a static snapshot" approach the research explicitly
argues against (G1: detection -> early detection; G3: pattern ->
trajectory) — it's a deliberately weaker baseline, not a strawman: it
uses real structural features, just no temporal signal at all.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from src.models.feature_groups import NETWORK_FEATURES


class StaticGraphAnomalyBaseline:
    name = "static_graph_anomaly_isolation_forest"

    def __init__(self, random_state: int = 42, contamination="auto"):
        self.model = IsolationForest(random_state=random_state, contamination=contamination, n_estimators=200)
        self.feature_cols = list(NETWORK_FEATURES)
        self._fitted_cols = None

    def fit(self, train_df: pd.DataFrame):
        cols = [c for c in self.feature_cols if c in train_df.columns]
        self._fitted_cols = cols
        X = train_df[cols].fillna(0).to_numpy()
        self.model.fit(X)
        return self

    def predict_score(self, df: pd.DataFrame) -> np.ndarray:
        X = df[self._fitted_cols].fillna(0).to_numpy()
        raw = self.model.score_samples(X)
        rescaled = 1.0 - (raw - raw.min()) / (raw.max() - raw.min() + 1e-12)
        return rescaled
