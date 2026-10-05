"""
Phase 3 tests: Data Quality Engine.

Run with: pytest tests/test_data_quality.py -v
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.schema import empty_schema_frame
from src.preprocessing.validation import DataQualityEngine


def _base_row(**overrides):
    row = {
        "transaction_id": "T1",
        "sender": "A",
        "receiver": "B",
        "amount": 100.0,
        "timestamp": pd.Timestamp("2026-01-01", tz="UTC"),
        "label": 0,
        "scenario_id": "",
        "ring_id": "",
        "dataset_source": "unit_test",
    }
    row.update(overrides)
    return row


def _df(rows):
    return pd.DataFrame(rows)


def test_clean_data_has_no_findings():
    rows = [_base_row(transaction_id=f"T{i}", timestamp=pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(hours=i)) for i in range(10)]
    report = DataQualityEngine(_df(rows), "clean").run()
    assert report["total_issue_categories_with_findings"] == 0


def test_detects_duplicate_transaction_id():
    rows = [_base_row(transaction_id="T1"), _base_row(transaction_id="T1", sender="C")]
    report = DataQualityEngine(_df(rows), "test").run()
    assert report["issues"]["duplicate_transaction_ids"]["count"] == 2


def test_detects_negative_and_zero_amount():
    rows = [_base_row(transaction_id="T1", amount=-5.0), _base_row(transaction_id="T2", amount=0.0)]
    report = DataQualityEngine(_df(rows), "test").run()
    assert report["issues"]["negative_amount"]["count"] == 1
    assert report["issues"]["zero_amount"]["count"] == 1


def test_detects_missing_sender_and_receiver():
    rows = [_base_row(transaction_id="T1", sender=None), _base_row(transaction_id="T2", receiver=None)]
    report = DataQualityEngine(_df(rows), "test").run()
    assert report["issues"]["missing_sender"]["count"] == 1
    assert report["issues"]["missing_receiver"]["count"] == 1


def test_detects_self_transaction():
    rows = [_base_row(transaction_id="T1", sender="A", receiver="A")]
    report = DataQualityEngine(_df(rows), "test").run()
    assert report["issues"]["self_transaction"]["count"] == 1


def test_detects_invalid_and_future_timestamp():
    rows = [
        _base_row(transaction_id="T1", timestamp=pd.NaT),
        _base_row(transaction_id="T2", timestamp=pd.Timestamp("2099-01-01", tz="UTC")),
    ]
    report = DataQualityEngine(_df(rows), "test").run()
    assert report["issues"]["invalid_timestamp"]["count"] == 1
    assert report["issues"]["future_timestamp"]["count"] == 1


def test_detects_invalid_label():
    rows = [_base_row(transaction_id="T1", label=7)]
    report = DataQualityEngine(_df(rows), "test").run()
    assert report["issues"]["invalid_label_value"]["count"] == 1


def test_detects_ring_without_scenario():
    rows = [_base_row(transaction_id="T1", ring_id="RING1", scenario_id="")]
    report = DataQualityEngine(_df(rows), "test").run()
    assert report["issues"]["ring_without_scenario"]["count"] == 1


def test_summary_statistics_are_populated():
    rows = [_base_row(transaction_id=f"T{i}", amount=float(100 + i)) for i in range(5)]
    report = DataQualityEngine(_df(rows), "test").run()
    s = report["summary"]
    assert s["row_count"] == 5
    assert s["amount_statistics"]["min"] == 100.0
    assert s["amount_statistics"]["max"] == 104.0
    assert s["unique_accounts"] == 2  # "A" and "B"


def test_write_json_and_html(tmp_path):
    rows = [_base_row(transaction_id="T1")]
    engine = DataQualityEngine(_df(rows), "test")
    json_path = tmp_path / "report.json"
    html_path = tmp_path / "report.html"
    engine.write_json(json_path)
    engine.write_html(html_path)
    assert json_path.exists() and json_path.stat().st_size > 0
    assert html_path.exists() and "Data Quality Report" in html_path.read_text()
