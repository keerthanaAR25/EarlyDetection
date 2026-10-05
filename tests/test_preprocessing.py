"""
Phase 4 tests: DataPreprocessor.

Run with: pytest tests/test_preprocessing.py -v
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.preprocessing.cleaning import DataPreprocessor


def _row(**overrides):
    row = {
        "transaction_id": "T1",
        "sender": "A",
        "receiver": "B",
        "amount": 100.0,
        "timestamp": "2026-01-01T00:00:00Z",
        "label": 0,
        "scenario_id": "",
        "ring_id": "",
        "dataset_source": "unit_test",
    }
    row.update(overrides)
    return row


def _df(rows):
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["label"] = df["label"].astype("int8")
    return df


def test_clean_input_passes_through_untouched():
    rows = [_row(transaction_id=f"T{i}") for i in range(5)]
    clean, log = DataPreprocessor(_df(rows)).run()
    assert len(clean) == 5
    assert all(s.rows_affected == 0 for s in log)


def test_drops_unparseable_timestamp():
    rows = [_row(transaction_id="T1"), _row(transaction_id="T2", timestamp=pd.NaT)]
    clean, log = DataPreprocessor(_df(rows)).run()
    assert len(clean) == 1
    ts_step = next(s for s in log if s.step == "parse_and_drop_invalid_timestamps")
    assert ts_step.rows_affected == 1


def test_drops_missing_sender_and_receiver():
    rows = [_row(transaction_id="T1"), _row(transaction_id="T2", sender=None), _row(transaction_id="T3", receiver="")]
    clean, log = DataPreprocessor(_df(rows)).run()
    assert len(clean) == 1
    step = next(s for s in log if s.step == "drop_missing_endpoints")
    assert step.rows_affected == 2


def test_drops_zero_and_negative_amount_by_default():
    rows = [_row(transaction_id="T1"), _row(transaction_id="T2", amount=0.0), _row(transaction_id="T3", amount=-10.0)]
    clean, log = DataPreprocessor(_df(rows)).run()
    assert len(clean) == 1
    assert clean.iloc[0]["transaction_id"] == "T1"


def test_can_configure_amount_drops_off():
    rows = [_row(transaction_id="T1"), _row(transaction_id="T2", amount=0.0), _row(transaction_id="T3", amount=-10.0)]
    clean, log = DataPreprocessor(
        _df(rows), drop_zero_amount=False, drop_negative_amount=False
    ).run()
    assert len(clean) == 3


def test_self_transactions_flagged_not_dropped_by_default():
    rows = [_row(transaction_id="T1"), _row(transaction_id="T2", sender="X", receiver="X")]
    clean, log = DataPreprocessor(_df(rows)).run()
    assert len(clean) == 2  # not dropped by default
    step = next(s for s in log if s.step == "flag_self_transactions")
    assert step.details["self_transaction_count"] == 1


def test_self_transactions_dropped_when_configured():
    rows = [_row(transaction_id="T1"), _row(transaction_id="T2", sender="X", receiver="X")]
    clean, log = DataPreprocessor(_df(rows), drop_self_transactions=True).run()
    assert len(clean) == 1


def test_deduplicates_transaction_ids_keeping_first():
    rows = [_row(transaction_id="T1", sender="A"), _row(transaction_id="T1", sender="Z")]
    clean, log = DataPreprocessor(_df(rows)).run()
    assert len(clean) == 1
    assert clean.iloc[0]["sender"] == "A"  # first occurrence kept


def test_output_is_sorted_chronologically():
    rows = [
        _row(transaction_id="T1", timestamp="2026-01-03T00:00:00Z"),
        _row(transaction_id="T2", timestamp="2026-01-01T00:00:00Z"),
        _row(transaction_id="T3", timestamp="2026-01-02T00:00:00Z"),
    ]
    clean, log = DataPreprocessor(_df(rows)).run()
    assert list(clean["transaction_id"]) == ["T2", "T3", "T1"]
    assert clean["timestamp"].is_monotonic_increasing


def test_labels_preserved_unmodified():
    rows = [_row(transaction_id="T1", label=1, ring_id="RING1", scenario_id="RING1")]
    clean, log = DataPreprocessor(_df(rows)).run()
    assert clean.iloc[0]["label"] == 1
    assert clean.iloc[0]["ring_id"] == "RING1"


def test_write_produces_files_and_log(tmp_path):
    rows = [_row(transaction_id=f"T{i}") for i in range(3)]
    pre = DataPreprocessor(_df(rows), dataset_label="unit_test")
    clean, log = pre.run()
    result = pre.write(clean, log, tmp_path)
    assert Path(result["clean_path"]).exists()
    assert Path(result["log_path"]).exists()
    assert result["log_record"]["rows_in"] == 3
    assert result["log_record"]["rows_out"] == 3
    assert len(result["log_record"]["steps"]) == len(log)


def test_rejects_input_with_missing_schema_columns():
    bad_df = pd.DataFrame({"transaction_id": ["T1"]})
    with pytest.raises(ValueError):
        DataPreprocessor(bad_df).run()
