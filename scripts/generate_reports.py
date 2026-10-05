#!/usr/bin/env python3
"""
Generate the remaining consolidated reports (lead_time_analysis,
pattern_analysis, feature_analysis) and results/metrics.json,
results/predictions.csv — reusing artifacts already produced by
earlier phases' scripts rather than recomputing anything.

Usage:
    python scripts/generate_reports.py
"""
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.evaluation.report_utils import render_report, df_to_html_table
from src.graph.temporal_graph import TemporalGraphBuilder
from src.models.labels import build_forecast_labels, attach_labels
from src.models.data_split import chronological_split
from src.models.feature_groups import downcast_numeric
from src.models.proposed_model import ProposedEarlyWarningModel


def _load_json(path):
    with open(path) as f:
        return json.load(f)


def main():
    results_dir = ROOT / "results"
    reports_dir = ROOT / "reports" / "tables"
    reports_dir.mkdir(parents=True, exist_ok=True)

    with open(ROOT / "configs" / "config.yaml") as f:
        config = yaml.safe_load(f)

    lead_time_df = pd.read_csv(results_dir / "lead_time.csv")
    lead_time_summary = _load_json(results_dir / "lead_time_summary.json")
    cards = [
        ("Ring Detection Rate", f"{lead_time_summary['ring_detection_rate']:.0%}" if lead_time_summary["ring_detection_rate"] is not None else "N/A"),
        ("Early Detection Rate", f"{lead_time_summary['early_detection_rate']:.0%}" if lead_time_summary["early_detection_rate"] is not None else "N/A"),
        ("Median Lead Time", f"{lead_time_summary['median_lead_time_windows']:.1f} windows" if lead_time_summary["median_lead_time_windows"] is not None else "N/A"),
        ("Mean Lead Time", f"{lead_time_summary['mean_lead_time_windows']:.2f} windows" if lead_time_summary["mean_lead_time_windows"] is not None else "N/A"),
        ("False Warning Rate", f"{lead_time_summary['false_warning_rate_candidates']:.0%}" if lead_time_summary["false_warning_rate_candidates"] is not None else "N/A"),
    ]
    html = render_report(
        "Lead-Time Analysis — How Early Can We Know?",
        "Central research question: warning_time vs observable_time per ring candidate, matched against demo ground truth.",
        cards,
        [
            ("Per-Candidate Results", df_to_html_table(lead_time_df)),
            ("Note", "<p class='note'>Behavioural/network risk components are held at their final values when "
                     "reconstructing cumulative risk per window (Phase 15 documented approximation); "
                     "fund_flow/persistence are recomputed from truncated evidence.</p>"),
        ],
    )
    (reports_dir / "lead_time_analysis.html").write_text(html)

    pattern_events = pd.read_csv(results_dir / "pattern_events.csv", dtype={"central_account": str})
    pattern_summary = (
        pattern_events.groupby("pattern_type")
        .agg(count=("pattern_type", "size"), mean_strength=("pattern_strength", "mean"))
        .reset_index()
        .sort_values("count", ascending=False)
    )
    html = render_report(
        "Pattern Analytics",
        f"{len(pattern_events):,} total pattern events detected across 8 detector types.",
        [("Total Events", f"{len(pattern_events):,}"), ("Distinct Types", pattern_events["pattern_type"].nunique())],
        [("Events by Pattern Type", df_to_html_table(pattern_summary))],
    )
    (reports_dir / "pattern_analysis.html").write_text(html)

    shap_importance = _load_json(results_dir / "shap_global_importance.json")
    shap_df = pd.DataFrame(shap_importance)
    html = render_report(
        "Feature Analysis — Global SHAP Importance",
        "Mean absolute SHAP value per feature for the proposed early-warning model, computed on the test split.",
        [("Top Feature", shap_df.iloc[0]["feature"] if not shap_df.empty else "N/A")],
        [("Global Feature Importance (Top 15)", df_to_html_table(shap_df))],
    )
    (reports_dir / "feature_analysis.html").write_text(html)

    print("Wrote lead_time_analysis.html, pattern_analysis.html, feature_analysis.html")

    df = pd.read_csv(ROOT / "data" / "processed" / "transactions_clean.csv", parse_dates=["timestamp"], dtype={"transaction_id": str, "sender": str, "receiver": str, "scenario_id": str, "ring_id": str})
    features = downcast_numeric(pd.read_csv(ROOT / "data" / "processed" / "features.csv", dtype={"account_id": str}))
    builder = TemporalGraphBuilder(df, config["temporal"]["window_size"], config["temporal"]["step_size"])
    bounds = builder.generate_window_bounds()
    labels = build_forecast_labels(df, bounds, horizon=config["evaluation"]["forecast_horizon_windows"])
    full = attach_labels(features, labels)
    splits = chronological_split(full, config["split"]["train_fraction"], config["split"]["val_fraction"])

    model = ProposedEarlyWarningModel(random_state=config["project"]["seed"])
    model.fit(splits["train"])
    test_df = splits["test"].copy()
    test_df["predicted_score"] = model.predict_score(test_df)
    test_df[["window_id", "account_id", "y", "predicted_score"]].to_csv(results_dir / "predictions.csv", index=False)
    print("Wrote results/predictions.csv")

    model_comparison = _load_json(results_dir / "model_comparison.json")
    ablation = pd.read_csv(results_dir / "ablation_results.csv").to_dict(orient="records")
    risk_scores = _load_json(results_dir / "risk_scores.json")

    metrics = {
        "model_comparison": model_comparison,
        "ablation_study": ablation,
        "lead_time_summary": lead_time_summary,
        "risk_score_distribution": {
            "n_candidates": len(risk_scores),
            "mean_risk_score": float(pd.Series([r["risk_score"] for r in risk_scores]).mean()),
            "by_level": pd.Series([r["risk_level"] for r in risk_scores]).value_counts().to_dict(),
        },
        "pattern_event_counts": pattern_summary.set_index("pattern_type")["count"].to_dict(),
    }
    with open(results_dir / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    print("Wrote results/metrics.json")


if __name__ == "__main__":
    main()
