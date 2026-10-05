"""
Proposed early-warning model (Phase 11).

FIX #2:
Controlled class-imbalance experiment for XGBoost.

Instead of always forcing the full negative/positive ratio
(~4282:1), the model supports a configurable class-weight multiplier.

Example:

base imbalance ratio ≈ 4282

multiplier 0.10
    -> scale_pos_weight ≈ 428

multiplier 0.25
    -> scale_pos_weight ≈ 1071

multiplier 0.50
    -> scale_pos_weight ≈ 2141

multiplier 1.00
    -> scale_pos_weight ≈ 4282

The comparison script can train multiple versions and select the
best configuration using validation performance.

The test set must remain untouched during selection.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.models.feature_groups import ALL_FEATURES

try:
    import xgboost as xgb

    _HAS_XGBOOST = True

except ImportError:
    from sklearn.ensemble import GradientBoostingClassifier

    _HAS_XGBOOST = False


class ProposedEarlyWarningModel:
    """
    Proposed early-warning model using all available network,
    transaction, temporal and delta features.

    FIX #2 adds controlled class imbalance through:

        effective_weight =
            base_scale_pos_weight * class_weight_multiplier

    The model also exposes both:

        scale_pos_weight
        effective_scale_pos_weight

    in get_model_info() for compatibility with existing scripts.
    """

    name = "proposed_gradient_boosting"

    def __init__(
        self,
        random_state: int = 42,
        class_weight_multiplier: float = 1.0,
    ):
        # --------------------------------------------------------------
        # Feature configuration
        # --------------------------------------------------------------
        self.feature_cols = list(ALL_FEATURES)
        self._fitted_cols = None

        # --------------------------------------------------------------
        # Backend
        # --------------------------------------------------------------
        self.backend = (
            "xgboost"
            if _HAS_XGBOOST
            else "sklearn_gradient_boosting"
        )

        self.random_state = random_state

        # --------------------------------------------------------------
        # FIX #2 — class-weight configuration
        # --------------------------------------------------------------
        self.class_weight_multiplier = float(
            class_weight_multiplier
        )

        if self.class_weight_multiplier <= 0:
            raise ValueError(
                "class_weight_multiplier must be greater than 0."
            )

        self.base_scale_pos_weight = None
        self.scale_pos_weight = None

        # --------------------------------------------------------------
        # MODEL
        # --------------------------------------------------------------
        if _HAS_XGBOOST:

            self.model = xgb.XGBClassifier(
                n_estimators=300,
                max_depth=5,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                eval_metric="aucpr",
                random_state=random_state,
                verbosity=0,
            )

        else:

            self.model = GradientBoostingClassifier(
                n_estimators=300,
                max_depth=3,
                learning_rate=0.05,
                random_state=random_state,
            )

    # ==============================================================
    # FIT
    # ==============================================================

    def fit(
        self,
        train_df: pd.DataFrame,
        y_col: str = "y",
    ):
        """
        Train the proposed early-warning model.

        The class-weight ratio is calculated ONLY from the training
        split to avoid information leakage from validation/test data.
        """

        # ----------------------------------------------------------
        # SELECT AVAILABLE FEATURES
        # ----------------------------------------------------------
        cols = [
            c
            for c in self.feature_cols
            if c in train_df.columns
        ]

        if not cols:
            raise ValueError(
                "None of the configured model features are present "
                "in the training dataframe."
            )

        self._fitted_cols = cols

        X = (
            train_df[cols]
            .fillna(0)
            .to_numpy()
        )

        y = (
            train_df[y_col]
            .to_numpy()
            .astype(int)
        )

        # ----------------------------------------------------------
        # VALIDATE LABELS
        # ----------------------------------------------------------
        n_pos = int(y.sum())
        n_neg = int(len(y) - n_pos)

        if n_pos == 0:
            raise ValueError(
                "Cannot fit a supervised model with zero "
                "positive examples in the training split."
            )

        if n_neg == 0:
            raise ValueError(
                "Cannot calculate class imbalance because the "
                "training split contains zero negative examples."
            )

        # ----------------------------------------------------------
        # FIX #2 — CLASS IMBALANCE
        # ----------------------------------------------------------
        if _HAS_XGBOOST:

            # Natural negative / positive ratio.
            self.base_scale_pos_weight = (
                n_neg / max(n_pos, 1)
            )

            # Controlled class-weight multiplier.
            self.scale_pos_weight = (
                self.base_scale_pos_weight
                * self.class_weight_multiplier
            )

            # XGBoost should not receive a value below 1.
            self.scale_pos_weight = max(
                self.scale_pos_weight,
                1.0,
            )

            self.model.set_params(
                scale_pos_weight=self.scale_pos_weight
            )

            print(
                "  Class imbalance:"
                f" positives={n_pos},"
                f" negatives={n_neg},"
                f" base_weight={self.base_scale_pos_weight:.2f},"
                f" multiplier={self.class_weight_multiplier:.3f},"
                f" effective_weight={self.scale_pos_weight:.2f}"
            )

        # ----------------------------------------------------------
        # TRAIN
        # ----------------------------------------------------------
        self.model.fit(
            X,
            y,
        )

        return self

    # ==============================================================
    # PREDICT
    # ==============================================================

    def predict_score(
        self,
        df: pd.DataFrame,
    ) -> np.ndarray:
        """
        Return probability/risk score for the positive class.
        """

        if self._fitted_cols is None:
            raise RuntimeError(
                "Model must be fitted before prediction."
            )

        X = (
            df[self._fitted_cols]
            .fillna(0)
            .to_numpy()
        )

        return self.model.predict_proba(X)[:, 1]

    # ==============================================================
    # FEATURE IMPORTANCE
    # ==============================================================

    def feature_importances(self) -> dict:
        """
        Return model feature importance values.
        """

        if self._fitted_cols is None:
            return {}

        return dict(
            zip(
                self._fitted_cols,
                self.model.feature_importances_.tolist(),
            )
        )

    # ==============================================================
    # MODEL INFORMATION
    # ==============================================================

    def get_model_info(self) -> dict:
        """
        Return model configuration and training information.

        IMPORTANT:
        Both 'scale_pos_weight' and 'effective_scale_pos_weight'
        are returned because existing comparison/reporting code
        may use either key.
        """

        return {
            "model_name": self.name,

            "backend": self.backend,

            "class_weight_multiplier":
                self.class_weight_multiplier,

            # Natural imbalance ratio calculated from training data.
            "base_scale_pos_weight":
                self.base_scale_pos_weight,

            # Backward-compatible key expected by compare_models.py.
            "scale_pos_weight":
                self.scale_pos_weight,

            # Explicit descriptive name.
            "effective_scale_pos_weight":
                self.scale_pos_weight,

            "n_features": (
                len(self._fitted_cols)
                if self._fitted_cols
                else 0
            ),
        }