"""
Shared classification evaluation metrics for baselines and the
proposed model (Phase 10/11), reused again by the ablation study
(Phase 16) and baseline comparison (Phase 17).

Per the project's non-negotiable rule against fabricated results: if a
metric cannot be validly computed (e.g. ROC-AUC with zero positive
examples in the split), this returns None for that metric rather than
a placeholder number. Callers must render None as "Not yet evaluated".
"""
from __future__ import annotations

import numpy as np

from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    average_precision_score,
    confusion_matrix,
)


def compute_classification_metrics(
    y_true,
    y_score,
    threshold: float = 0.5,
    top_k=None,
) -> dict:
    """
    Compute classification metrics from true labels and predicted scores.

    Parameters
    ----------
    y_true : array-like
        Ground-truth binary labels.

    y_score : array-like
        Predicted probability/risk scores for the positive class.

    threshold : float, default=0.5
        Classification threshold used to convert scores into
        binary predictions.

    top_k : int, list, tuple, or None
        Optional investigator-oriented Top-K evaluation.

        Examples:
            top_k=10
            top_k=[10, 25, 50]
            top_k=(10, 25, 50)

    Returns
    -------
    dict
        Classification metrics and Top-K precision.
    """

    # ------------------------------------------------------------------
    # Convert inputs to NumPy arrays
    # ------------------------------------------------------------------
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score)

    # Flatten in case a column vector is supplied.
    y_true = y_true.reshape(-1)
    y_score = y_score.reshape(-1)

    if len(y_true) != len(y_score):
        raise ValueError(
            f"y_true and y_score must have the same length. "
            f"Got {len(y_true)} and {len(y_score)}."
        )

    # ------------------------------------------------------------------
    # Convert scores to binary predictions
    # ------------------------------------------------------------------
    y_pred = (y_score >= threshold).astype(int)

    # ------------------------------------------------------------------
    # Class counts
    # ------------------------------------------------------------------
    n_pos = int(y_true.sum())
    n_neg = int(len(y_true) - n_pos)

    metrics = {
        "n_samples": int(len(y_true)),
        "n_positive": n_pos,
        "n_negative": n_neg,
        "precision": None,
        "recall": None,
        "f1": None,
        "roc_auc": None,
        "pr_auc": None,
        "false_warning_rate": None,
        "top_k_precision": {},
    }

    # ------------------------------------------------------------------
    # No positive examples
    # ------------------------------------------------------------------
    if n_pos == 0:
        metrics["note"] = (
            "No positive examples in this split — "
            "precision/recall/AUC not computable."
        )
        return metrics

    # ------------------------------------------------------------------
    # Threshold-based metrics
    # ------------------------------------------------------------------
    metrics["precision"] = float(
        precision_score(
            y_true,
            y_pred,
            zero_division=0,
        )
    )

    metrics["recall"] = float(
        recall_score(
            y_true,
            y_pred,
            zero_division=0,
        )
    )

    metrics["f1"] = float(
        f1_score(
            y_true,
            y_pred,
            zero_division=0,
        )
    )

    # ------------------------------------------------------------------
    # Ranking-based metrics
    # ------------------------------------------------------------------
    if n_pos > 0 and n_neg > 0:
        try:
            metrics["roc_auc"] = float(
                roc_auc_score(
                    y_true,
                    y_score,
                )
            )

            metrics["pr_auc"] = float(
                average_precision_score(
                    y_true,
                    y_score,
                )
            )

        except ValueError:
            # Keep metrics as None if sklearn cannot compute them.
            pass

        # --------------------------------------------------------------
        # False Warning Rate
        # FWR = FP / (FP + TN)
        # --------------------------------------------------------------
        tn, fp, fn, tp = confusion_matrix(
            y_true,
            y_pred,
            labels=[0, 1],
        ).ravel()

        metrics["false_warning_rate"] = (
            float(fp / (fp + tn))
            if (fp + tn) > 0
            else None
        )

    # ------------------------------------------------------------------
    # FIX:
    # Normalize top_k so both:
    #
    #     top_k=10
    #
    # and:
    #
    #     top_k=[10, 25, 50]
    #
    # work correctly.
    # ------------------------------------------------------------------
    if top_k is None:
        top_k_values = []

    elif isinstance(top_k, (int, np.integer)):
        top_k_values = [int(top_k)]

    else:
        top_k_values = list(top_k)

    # ------------------------------------------------------------------
    # Top-K Precision
    # ------------------------------------------------------------------
    if top_k_values:
        order = np.argsort(-y_score)

        for k in top_k_values:
            try:
                k = int(k)
            except (TypeError, ValueError):
                continue

            if k <= 0:
                continue

            k = min(k, len(y_true))

            top_k_idx = order[:k]

            metrics["top_k_precision"][k] = (
                float(y_true[top_k_idx].mean())
                if k > 0
                else None
            )

    return metrics