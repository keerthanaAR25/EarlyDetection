#!/usr/bin/env python3
"""
Run the Data Quality Engine over the active dataset and write
reports/data_quality_report.{json,html}.

Usage:
    python scripts/run_data_quality.py
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.demo_adapter import DemoAdapter
from src.data.amlsim_adapter import AMLSimAdapter
from src.data.elliptic_adapter import EllipticAdapter
from src.preprocessing.validation import DataQualityEngine


def load_active_dataset(config: dict):
    active = config["dataset"]["active"]
    if active == "demo":
        adapter = DemoAdapter(ROOT / config["dataset"]["demo"]["path"])
    elif active == "amlsim":
        adapter = AMLSimAdapter(ROOT / config["dataset"]["amlsim"]["raw_path"])
    elif active == "elliptic":
        adapter = EllipticAdapter(ROOT / config["dataset"]["elliptic"]["raw_path"])
    else:
        raise ValueError(f"Unknown dataset.active='{active}' in config.yaml")
    return active, adapter.load()


def main():
    with open(ROOT / "configs" / "config.yaml") as f:
        config = yaml.safe_load(f)

    active, df = load_active_dataset(config)
    print(f"Loaded '{active}' dataset: {len(df):,} rows")

    engine = DataQualityEngine(df, dataset_label=active)
    report = engine.run()

    json_path = ROOT / "reports" / "data_quality_report.json"
    html_path = ROOT / "reports" / "data_quality_report.html"
    engine.write_json(json_path, report)
    engine.write_html(html_path, report)

    print(f"\nSummary:")
    print(f"  Rows: {report['summary']['row_count']:,}")
    print(f"  Unique accounts: {report['summary']['unique_accounts']:,}")
    print(f"  Timestamp range: {report['summary']['timestamp_range']['min']} -> {report['summary']['timestamp_range']['max']}")
    print(f"  Class distribution: {report['summary']['class_distribution']}")
    print(f"  Issue categories with findings: {report['total_issue_categories_with_findings']} / {len(report['issues'])}")
    for name, info in report["issues"].items():
        if info["count"] > 0:
            print(f"    ⚠️  {name}: {info['count']} ({info['pct_of_rows']}%)")

    print(f"\nWrote {json_path}")
    print(f"Wrote {html_path}")


if __name__ == "__main__":
    main()
