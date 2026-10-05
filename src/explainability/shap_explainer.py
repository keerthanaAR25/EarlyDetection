"""
SHAP explainability for the proposed early-warning model (Phase 13).

Uses shap.TreeExplainer, which supports both the XGBoost and sklearn
GradientBoosting backends the proposed model can use (Phase 11
documents that fallback), so this module works regardless of which
one is active.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import shap


class ShapExplainer:
    def __init__(self, model):
        self.model = model
        self.explainer = shap.TreeExplainer(model.model)

    def _shap_values(self, df: pd.DataFrame) -> np.ndarray:
        X = df[self.model._fitted_cols].fillna(0)
        raw = self.explainer.shap_values(X)
        if isinstance(raw, list):
            raw = raw[-1] if len(raw) > 1 else raw[0]
        return np.asarray(raw)

    def global_feature_importance(self, df: pd.DataFrame, top_n: int = 15) -> list:
        shap_vals = self._shap_values(df)
        mean_abs = np.abs(shap_vals).mean(axis=0)
        ranking = sorted(zip(self.model._fitted_cols, mean_abs), key=lambda kv: -kv[1])
        return [{"feature": f, "mean_abs_shap": round(float(v), 5)} for f, v in ranking[:top_n]]

    def local_explanation(self, df: pd.DataFrame, row_index: int, top_n: int = 8) -> dict:
        shap_vals = self._shap_values(df)
        row_shap = shap_vals[row_index]
        cols = self.model._fitted_cols
        row_values = df.iloc[row_index][cols]

        contributions = sorted(zip(cols, row_shap, row_values), key=lambda t: -abs(t[1]))[:top_n]

        positive = [
            {"feature": f, "value": float(v), "shap_contribution": round(float(s), 5)}
            for f, s, v in contributions if s > 0
        ]
        negative = [
            {"feature": f, "value": float(v), "shap_contribution": round(float(s), 5)}
            for f, s, v in contributions if s <= 0
        ]

        ev = self.explainer.expected_value
        base_value = float(ev[-1] if isinstance(ev, (list, np.ndarray)) else ev)

        return {
            "base_value": round(base_value, 5),
            "predicted_score": float(self.model.predict_score(df.iloc[[row_index]])[0]),
            "top_positive_factors": positive,
            "top_negative_factors": negative,
        }

    def waterfall_data(self, df: pd.DataFrame, row_index: int) -> list:
        shap_vals = self._shap_values(df)
        row_shap = shap_vals[row_index]
        cols = self.model._fitted_cols
        row_values = df.iloc[row_index][cols]

        items = sorted(
            [{"feature": f, "value": float(v), "shap_contribution": float(s)}
             for f, v, s in zip(cols, row_values, row_shap)],
            key=lambda d: -abs(d["shap_contribution"]),
        )
        return items
