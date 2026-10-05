#!/usr/bin/env python3
"""
Compare AML early-warning models.

FIX #2:
Controlled XGBoost class-imbalance experiment.

The proposed XGBoost model is trained using multiple class-weight
multipliers. The best configuration is selected using VALIDATION
PR-AUC, with validation F1 as a tie-breaker.

After selecting the class-weight configuration, the classification
threshold is tuned on VALIDATION data.

The TEST set is used only once for final evaluation.

Usage:
    python scripts/compare_models.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


from src.graph.temporal_graph import TemporalGraphBuilder
from src.models.labels import build_forecast_labels, attach_labels
from src.models.data_split import chronological_split
from src.models.feature_groups import downcast_numeric

from src.models.baseline_static import StaticGraphAnomalyBaseline
from src.models.baseline_behavioural import BehaviouralMLBaseline
from src.models.baseline_temporal import TemporalAnalyticalBaseline
from src.models.proposed_model import ProposedEarlyWarningModel

from src.evaluation.metrics import compute_classification_metrics


# ============================================================
# CONFIGURATION
# ============================================================

# Class-weight multipliers.

# Natural imbalance is approximately:
#
# 1,425,814 negatives / 333 positives ≈ 4,282
#
# Effective weights will therefore be approximately:
#
# 0.025 -> 107
# 0.050 -> 214
# 0.100 -> 428
# 0.250 -> 1,071
# 0.500 -> 2,141
# 1.000 -> 4,282

CLASS_WEIGHT_MULTIPLIERS = [
    0.025,
    0.050,
    0.100,
    0.250,
    0.500,
    1.000,
]

# Thresholds for Fix #1.

THRESHOLDS = [
    0.10,
    0.20,
    0.30,
    0.40,
    0.50,
    0.60,
    0.70,
    0.80,
    0.90,
]


# ============================================================
# STANDARD EVALUATION
# ============================================================

def evaluate_split(model, df, top_k):

    if len(df) == 0:
        return {
            "note": "No rows in this split."
        }

    scores = model.predict_score(df)

    return compute_classification_metrics(
        df["y"].to_numpy(),
        scores,
        top_k=top_k,
    )


# ============================================================
# THRESHOLD EVALUATION
# ============================================================

def evaluate_at_threshold(
    y_true,
    scores,
    threshold,
    top_k_values=(10, 20, 50),
):

    y_true = np.asarray(y_true).astype(int)
    scores = np.asarray(scores).astype(float)

    predictions = (
        scores >= threshold
    ).astype(int)

    precision = precision_score(
        y_true,
        predictions,
        zero_division=0,
    )

    recall = recall_score(
        y_true,
        predictions,
        zero_division=0,
    )

    f1 = f1_score(
        y_true,
        predictions,
        zero_division=0,
    )

    tn, fp, fn, tp = confusion_matrix(
        y_true,
        predictions,
        labels=[0, 1],
    ).ravel()

    false_warning_rate = (
        fp / (fp + tn)
        if (fp + tn) > 0
        else 0.0
    )

    # --------------------------------------------------------
    # TOP-K PRECISION
    # --------------------------------------------------------

    top_k_precision = {}

    ranking = np.argsort(
        -scores
    )

    for k in top_k_values:

        k_actual = min(
            k,
            len(y_true)
        )

        if k_actual == 0:
            top_k_precision[str(k)] = 0.0
            continue

        top_indices = ranking[
            :k_actual
        ]

        top_k_precision[str(k)] = float(
            np.mean(
                y_true[top_indices]
            )
        )

    return {
        "threshold": float(threshold),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "false_warning_rate": float(
            false_warning_rate
        ),
        "tp": int(tp),
        "fp": int(fp),
        "fn": int(fn),
        "tn": int(tn),
        "top_k_precision": top_k_precision,
    }


# ============================================================
# THRESHOLD TUNING
# ============================================================

def tune_threshold(
    model,
    val_df,
):

    y_val = val_df["y"].to_numpy()

    val_scores = model.predict_score(
        val_df
    )

    rows = []

    for threshold in THRESHOLDS:

        result = evaluate_at_threshold(
            y_val,
            val_scores,
            threshold,
        )

        rows.append(result)

    threshold_df = pd.DataFrame(
        rows
    )

    # --------------------------------------------------------
    # SELECT OPERATING THRESHOLD
    #
    # Primary criterion:
    #     F1
    #
    # Tie breakers:
    #     precision
    #     recall
    #     threshold
    # --------------------------------------------------------

    sorted_df = threshold_df.sort_values(
        by=[
            "f1",
            "precision",
            "recall",
            "threshold",
        ],
        ascending=[
            False,
            False,
            False,
            False,
        ],
    )

    best = sorted_df.iloc[0]

    return (
        float(best["threshold"]),
        threshold_df,
    )


# ============================================================
# FINAL TEST EVALUATION
# ============================================================

def evaluate_test_with_threshold(
    model,
    test_df,
    threshold,
    top_k,
):

    y_test = test_df["y"].to_numpy()

    scores = model.predict_score(
        test_df
    )

    threshold_metrics = evaluate_at_threshold(
        y_test,
        scores,
        threshold,
        top_k_values=(10, 20, 50),
    )

    # ROC-AUC / PR-AUC remain threshold-independent.
    standard_metrics = compute_classification_metrics(
        y_test,
        scores,
        top_k=top_k,
    )

    result = dict(
        standard_metrics
    )

    # Replace threshold-dependent values.
    result["threshold"] = float(
        threshold
    )

    result["precision"] = (
        threshold_metrics["precision"]
    )

    result["recall"] = (
        threshold_metrics["recall"]
    )

    result["f1"] = (
        threshold_metrics["f1"]
    )

    result["false_warning_rate"] = (
        threshold_metrics[
            "false_warning_rate"
        ]
    )

    result["confusion_matrix"] = {
        "tp": threshold_metrics["tp"],
        "fp": threshold_metrics["fp"],
        "fn": threshold_metrics["fn"],
        "tn": threshold_metrics["tn"],
    }

    result["top_k_precision"] = {
        int(k): float(v)
        for k, v in
        threshold_metrics[
            "top_k_precision"
        ].items()
    }

    return result


# ============================================================
# CLASS-WEIGHT EXPERIMENT
# ============================================================

def run_class_weight_experiment(
    train_df,
    val_df,
    seed,
):

    print(
        "\n"
        + "=" * 70
    )

    print(
        "FIX #2 — CLASS-WEIGHT EXPERIMENT"
    )

    print(
        "=" * 70
    )

    experiment_rows = []

    trained_models = {}

    for multiplier in CLASS_WEIGHT_MULTIPLIERS:

        print(
            f"\n--- Class-weight multiplier: "
            f"{multiplier:.3f} ---"
        )

        model = ProposedEarlyWarningModel(
            random_state=seed,
            class_weight_multiplier=multiplier,
        )

        try:

            model.fit(
                train_df
            )

        except ValueError as e:

            print(
                f"SKIPPED: {e}"
            )

            continue

        val_scores = model.predict_score(
            val_df
        )

        y_val = val_df["y"].to_numpy()

        # Threshold-independent metrics.
        val_standard = compute_classification_metrics(
            y_val,
            val_scores,
            top_k=50,
        )

        # Threshold tuning for this configuration.
        best_threshold, threshold_table = (
            tune_threshold(
                model,
                val_df,
            )
        )

        selected_row = threshold_table[
            threshold_table[
                "threshold"
            ] == best_threshold
        ].iloc[0]

        model_info = model.get_model_info()

        row = {
            "class_weight_multiplier":
                multiplier,

            "base_scale_pos_weight":
                model_info[
                    "base_scale_pos_weight"
                ],

            "effective_scale_pos_weight":
                model_info[
                    "effective_scale_pos_weight"
                ],

            "val_roc_auc":
                val_standard.get(
                    "roc_auc"
                ),

            "val_pr_auc":
                val_standard.get(
                    "pr_auc"
                ),

            "val_precision":
                selected_row[
                    "precision"
                ],

            "val_recall":
                selected_row[
                    "recall"
                ],

            "val_f1":
                selected_row[
                    "f1"
                ],

            "val_false_warning_rate":
                selected_row[
                    "false_warning_rate"
                ],

            "selected_threshold":
                best_threshold,
        }

        experiment_rows.append(
            row
        )

        trained_models[
            multiplier
        ] = {
            "model": model,
            "threshold": best_threshold,
        }

        print(
            f"  base weight: "
            f"{model_info['base_scale_pos_weight']:.2f}"
        )

        print(
            f"  effective weight: "
            f"{model_info['effective_scale_pos_weight']:.2f}"
        )

        print(
            f"  validation ROC-AUC: "
            f"{row['val_roc_auc']}"
        )

        print(
            f"  validation PR-AUC: "
            f"{row['val_pr_auc']}"
        )

        print(
            f"  validation precision: "
            f"{row['val_precision']}"
        )

        print(
            f"  validation recall: "
            f"{row['val_recall']}"
        )

        print(
            f"  validation F1: "
            f"{row['val_f1']}"
        )

        print(
            f"  selected threshold: "
            f"{best_threshold:.2f}"
        )

    experiment_df = pd.DataFrame(
        experiment_rows
    )

    if experiment_df.empty:

        raise RuntimeError(
            "Class-weight experiment produced "
            "no valid model."
        )

    # --------------------------------------------------------
    # SELECT BEST MODEL
    #
    # Primary:
    #     Validation PR-AUC
    #
    # Tie-break:
    #     Validation F1
    #
    # Secondary:
    #     Validation precision
    # --------------------------------------------------------

    experiment_df = (
        experiment_df
        .sort_values(
            by=[
                "val_pr_auc",
                "val_f1",
                "val_precision",
            ],
            ascending=[
                False,
                False,
                False,
            ],
        )
        .reset_index(drop=True)
    )

    best_row = experiment_df.iloc[0]

    best_multiplier = float(
        best_row[
            "class_weight_multiplier"
        ]
    )

    best_threshold = float(
        best_row[
            "selected_threshold"
        ]
    )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "BEST CLASS-WEIGHT CONFIGURATION"
    )

    print(
        "=" * 70
    )

    print(
        f"Multiplier: "
        f"{best_multiplier}"
    )

    print(
        f"Effective scale_pos_weight: "
        f"{best_row['effective_scale_pos_weight']:.2f}"
    )

    print(
        f"Validation PR-AUC: "
        f"{best_row['val_pr_auc']}"
    )

    print(
        f"Validation F1: "
        f"{best_row['val_f1']}"
    )

    print(
        f"Validation Precision: "
        f"{best_row['val_precision']}"
    )

    print(
        f"Validation Recall: "
        f"{best_row['val_recall']}"
    )

    print(
        f"Selected threshold: "
        f"{best_threshold:.2f}"
    )

    return (
        experiment_df,
        trained_models[
            best_multiplier
        ]["model"],
        best_threshold,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # LOAD CONFIG
    # --------------------------------------------------------

    with open(
        ROOT /
        "configs" /
        "config.yaml",
        encoding="utf-8",
    ) as f:

        config = yaml.safe_load(
            f
        )

    # --------------------------------------------------------
    # LOAD TRANSACTIONS
    # --------------------------------------------------------

    df = pd.read_csv(

        ROOT /
        "data" /
        "processed" /
        "transactions_clean.csv",

        parse_dates=[
            "timestamp"
        ],

        dtype={
            "transaction_id": str,
            "sender": str,
            "receiver": str,
            "scenario_id": str,
            "ring_id": str,
        },
    )

    # --------------------------------------------------------
    # LOAD FEATURES
    # --------------------------------------------------------

    features = downcast_numeric(

        pd.read_csv(

            ROOT /
            "data" /
            "processed" /
            "features.csv",

            dtype={
                "account_id": str
            },
        )
    )

    # --------------------------------------------------------
    # TEMPORAL GRAPH
    # --------------------------------------------------------

    builder = TemporalGraphBuilder(

        df,

        config[
            "temporal"
        ]["window_size"],

        config[
            "temporal"
        ]["step_size"],
    )

    bounds = (
        builder.generate_window_bounds()
    )

    horizon = config[
        "evaluation"
    ][
        "forecast_horizon_windows"
    ]

    labels = build_forecast_labels(

        df,

        bounds,

        horizon=horizon,
    )

    full = attach_labels(
        features,
        labels,
    )

    # --------------------------------------------------------
    # CHRONOLOGICAL SPLIT
    # --------------------------------------------------------

    splits = chronological_split(

        full,

        config[
            "split"
        ]["train_fraction"],

        config[
            "split"
        ]["val_fraction"],
    )

    train_df = splits["train"]
    val_df = splits["val"]
    test_df = splits["test"]

    top_k = config[
        "evaluation"
    ]["top_k"]

    seed = config[
        "project"
    ]["seed"]

    # --------------------------------------------------------
    # SPLIT SUMMARY
    # --------------------------------------------------------

    print(
        f"Forecast horizon: "
        f"{horizon} windows"
    )

    print(
        f"Train: {len(train_df)} rows "
        f"({int(train_df['y'].sum())} positive)"
    )

    print(
        f"Val:   {len(val_df)} rows "
        f"({int(val_df['y'].sum())} positive)"
    )

    print(
        f"Test:  {len(test_df)} rows "
        f"({int(test_df['y'].sum())} positive)"
    )

    # ========================================================
    # BASELINE MODELS
    # ========================================================

    baseline_models = [

        StaticGraphAnomalyBaseline(
            random_state=seed
        ),

        BehaviouralMLBaseline(
            random_state=seed
        ),

        TemporalAnalyticalBaseline(
            random_state=seed
        ),
    ]

    comparison_rows = []

    full_results = {}

    for model in baseline_models:

        print(
            f"\n--- {model.name} ---"
        )

        try:

            model.fit(
                train_df
            )

        except ValueError as e:

            print(
                f"SKIPPED: {e}"
            )

            continue

        val_metrics = evaluate_split(
            model,
            val_df,
            top_k,
        )

        test_metrics = evaluate_split(
            model,
            test_df,
            top_k,
        )

        full_results[
            model.name
        ] = {
            "val": val_metrics,
            "test": test_metrics,
        }

        backend = getattr(
            model,
            "backend",
            model.__class__.__module__,
        )

        print(
            f"  backend={backend}"
        )

        print(
            f"  test: "
            f"precision={test_metrics.get('precision')}, "
            f"recall={test_metrics.get('recall')}, "
            f"f1={test_metrics.get('f1')}, "
            f"roc_auc={test_metrics.get('roc_auc')}, "
            f"pr_auc={test_metrics.get('pr_auc')}, "
            f"false_warning_rate="
            f"{test_metrics.get('false_warning_rate')}"
        )

        comparison_rows.append({

            "method":
                model.name,

            "precision":
                test_metrics.get(
                    "precision"
                ),

            "recall":
                test_metrics.get(
                    "recall"
                ),

            "f1":
                test_metrics.get(
                    "f1"
                ),

            "roc_auc":
                test_metrics.get(
                    "roc_auc"
                ),

            "pr_auc":
                test_metrics.get(
                    "pr_auc"
                ),

            "false_warning_rate":
                test_metrics.get(
                    "false_warning_rate"
                ),

            "top_10_precision":
                test_metrics.get(
                    "top_k_precision",
                    {}
                ).get(10),

            "threshold":
                None,
        })

    # ========================================================
    # FIX #2 — CLASS-WEIGHTED PROPOSED MODEL
    # ========================================================

    (
        class_weight_results,
        proposed_model,
        selected_threshold,
    ) = run_class_weight_experiment(

        train_df,

        val_df,

        seed,
    )

    # --------------------------------------------------------
    # FINAL TEST
    #
    # IMPORTANT:
    # Model configuration and threshold were selected using
    # validation data only.
    # --------------------------------------------------------

    proposed_test_metrics = (
        evaluate_test_with_threshold(

            proposed_model,

            test_df,

            selected_threshold,

            top_k,
        )
    )

    # --------------------------------------------------------
    # PROPOSED MODEL RESULTS
    # --------------------------------------------------------

    proposed_val_metrics = evaluate_split(
        proposed_model,
        val_df,
        top_k,
    )

    model_info = (
        proposed_model.get_model_info()
    )

    full_results[
        "proposed_gradient_boosting"
    ] = {

        "val":
            proposed_val_metrics,

        "test":
            proposed_test_metrics,

        "class_weight": {

            "multiplier":
                model_info[
                    "class_weight_multiplier"
                ],

            "base_scale_pos_weight":
                model_info[
                    "base_scale_pos_weight"
                ],

            "effective_scale_pos_weight":
                model_info[
                    "effective_scale_pos_weight"
                ],
        },

        "threshold_selection": {

            "threshold":
                selected_threshold,

            "selection_split":
                "validation",

            "selection_metric":
                "validation_pr_auc",
        },
    }

    print(
        "\n"
        + "=" * 70
    )

    print(
        "FINAL PROPOSED MODEL — TEST"
    )

    print(
        "=" * 70
    )

    print(
        f"Class-weight multiplier: "
        f"{model_info['class_weight_multiplier']}"
    )

    print(
        f"Effective scale_pos_weight: "
        f"{model_info['scale_pos_weight']}"
    )

    print(
        f"Threshold: "
        f"{selected_threshold:.2f}"
    )

    print(
        f"Precision: "
        f"{proposed_test_metrics['precision']}"
    )

    print(
        f"Recall: "
        f"{proposed_test_metrics['recall']}"
    )

    print(
        f"F1: "
        f"{proposed_test_metrics['f1']}"
    )

    print(
        f"ROC-AUC: "
        f"{proposed_test_metrics['roc_auc']}"
    )

    print(
        f"PR-AUC: "
        f"{proposed_test_metrics['pr_auc']}"
    )

    print(
        f"False-warning rate: "
        f"{proposed_test_metrics['false_warning_rate']}"
    )

    print(
        f"Confusion matrix: "
        f"{proposed_test_metrics['confusion_matrix']}"
    )

    # --------------------------------------------------------
    # ADD PROPOSED MODEL TO COMPARISON TABLE
    # --------------------------------------------------------

    comparison_rows.append({

        "method":
            "proposed_gradient_boosting",

        "precision":
            proposed_test_metrics.get(
                "precision"
            ),

        "recall":
            proposed_test_metrics.get(
                "recall"
            ),

        "f1":
            proposed_test_metrics.get(
                "f1"
            ),

        "roc_auc":
            proposed_test_metrics.get(
                "roc_auc"
            ),

        "pr_auc":
            proposed_test_metrics.get(
                "pr_auc"
            ),

        "false_warning_rate":
            proposed_test_metrics.get(
                "false_warning_rate"
            ),

        "top_10_precision":
            proposed_test_metrics.get(
                "top_k_precision",
                {}
            ).get(10),

        "threshold":
            selected_threshold,

        "class_weight_multiplier":
            model_info[
                "class_weight_multiplier"
            ],

        "effective_scale_pos_weight":
            model_info[
                "effective_scale_pos_weight"
            ],
    })

    # ========================================================
    # OUTPUTS
    # ========================================================

    out_dir = (
        ROOT /
        "results"
    )

    out_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # MODEL COMPARISON JSON
    # --------------------------------------------------------

    with open(
        out_dir /
        "model_comparison.json",
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            full_results,
            f,
            indent=2,
            default=str,
        )

    # --------------------------------------------------------
    # MODEL COMPARISON CSV
    # --------------------------------------------------------

    comparison_df = pd.DataFrame(
        comparison_rows
    )

    comparison_df.to_csv(
        out_dir /
        "model_comparison.csv",
        index=False,
    )

    # --------------------------------------------------------
    # CLASS-WEIGHT RESULTS
    # --------------------------------------------------------

    class_weight_results.to_csv(
        out_dir /
        "class_weight_experiment.csv",
        index=False,
    )

    with open(
        out_dir /
        "class_weight_experiment.json",
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            class_weight_results.to_dict(
                orient="records"
            ),
            f,
            indent=2,
            default=str,
        )

    # --------------------------------------------------------
    # SELECTED CONFIGURATION
    # --------------------------------------------------------

    selected_config = {

        "class_weight_multiplier":
            model_info[
                "class_weight_multiplier"
            ],

        "base_scale_pos_weight":
            model_info[
                "base_scale_pos_weight"
            ],

        "effective_scale_pos_weight":
            model_info[
                "effective_scale_pos_weight"
            ],

        "selected_threshold":
            selected_threshold,

        "selection_split":
            "validation",

        "selection_metric":
            "validation_pr_auc",

        "threshold_selection_metric":
            "validation_f1",
    }

    with open(
        out_dir /
        "selected_proposed_model_config.json",
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            selected_config,
            f,
            indent=2,
        )

    # --------------------------------------------------------
    # HTML
    # --------------------------------------------------------

    reports_dir = (
        ROOT /
        "reports" /
        "tables"
    )

    reports_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    comparison_df.to_html(
        reports_dir /
        "model_comparison.html",
        index=False,
    )

    class_weight_results.to_html(
        reports_dir /
        "class_weight_experiment.html",
        index=False,
    )

    print(
        f"\nWrote "
        f"{out_dir / 'model_comparison.json'}"
    )

    print(
        f"Wrote "
        f"{out_dir / 'model_comparison.csv'}"
    )

    print(
        f"Wrote "
        f"{out_dir / 'class_weight_experiment.csv'}"
    )

    print(
        f"Wrote "
        f"{out_dir / 'class_weight_experiment.json'}"
    )

    print(
        f"Wrote "
        f"{out_dir / 'selected_proposed_model_config.json'}"
    )

    print(
        f"Wrote "
        f"{reports_dir / 'model_comparison.html'}"
    )

    print(
        f"Wrote "
        f"{reports_dir / 'class_weight_experiment.html'}"
    )

    # ========================================================
    # FEATURE IMPORTANCE
    # ========================================================

    if getattr(
        proposed_model,
        "_fitted_cols",
        None,
    ):

        importances = (
            proposed_model.feature_importances()
        )

        top = sorted(
            importances.items(),
            key=lambda kv: -kv[1],
        )[:15]

        print(
            "\nProposed model — "
            "top 15 features by importance:"
        )

        for feat, imp in top:

            print(
                f"  {feat}: "
                f"{imp:.4f}"
            )

        with open(
            out_dir /
            "proposed_model_feature_importances.json",
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                importances,
                f,
                indent=2,
            )


if __name__ == "__main__":
    main()