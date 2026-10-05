"""
Phase 2 tests: schema coercion/validation and dataset adapters.

Run with: pytest tests/test_data_adapters.py -v
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.schema import SCHEMA_COLUMNS, coerce_to_schema, validate_schema, empty_schema_frame
from src.data.demo_adapter import DemoAdapter
from src.data.demo_generator import DemoDataGenerator


DEMO_DIR = ROOT / "data" / "demo"


# ---------------------------------------------------------------- schema ---
def test_empty_schema_frame_has_canonical_columns():
    df = empty_schema_frame()
    assert list(df.columns) == SCHEMA_COLUMNS
    assert len(df) == 0


def test_coerce_to_schema_fills_missing_optional_columns():
    raw = pd.DataFrame(
        {
            "transaction_id": ["T1"],
            "sender": ["A"],
            "receiver": ["B"],
            "amount": [100.0],
            "timestamp": ["2026-01-01"],
        }
    )
    coerced = coerce_to_schema(raw, dataset_source="unit_test")
    assert list(coerced.columns) == SCHEMA_COLUMNS
    assert coerced.loc[0, "label"] == -1
    assert coerced.loc[0, "scenario_id"] == ""
    assert coerced.loc[0, "dataset_source"] == "unit_test"


def test_coerce_to_schema_raises_on_missing_required_column():
    raw = pd.DataFrame({"sender": ["A"], "receiver": ["B"]})  # no transaction_id/amount/timestamp
    with pytest.raises(ValueError):
        coerce_to_schema(raw, dataset_source="unit_test")


def test_validate_schema_flags_missing_columns():
    df = pd.DataFrame({"transaction_id": ["T1"]})
    result = validate_schema(df)
    assert not result.is_valid
    assert "sender" in result.missing_columns


# ------------------------------------------------------------ generator ---
def test_demo_generator_produces_valid_schema_and_labels():
    gen = DemoDataGenerator(
        n_normal_accounts=30, n_rings=2, simulation_days=20, normal_tx_per_day=10, seed=1
    )
    df, ground_truth = gen.generate()

    result = validate_schema(df)
    assert result.is_valid, result

    assert len(ground_truth) == 2
    assert (df["label"] == 1).sum() > 0, "ring scenarios must produce labeled transactions"
    assert (df["label"] == 0).sum() > 0, "background traffic must produce normal transactions"

    for g in ground_truth:
        ring_tx = df[df["ring_id"] == g["ring_id"]]
        assert len(ring_tx) > 0
        stage_names = [s["stage_name"] for s in g["stages"]]
        assert stage_names == [
            "fan_in",
            "layering",
            "fan_out",
            "repeated_intermediary",
            "circular_flow",
        ]
        assert g["observable_time"] >= g["start_date"]


def test_demo_generator_is_deterministic_given_seed():
    gen1 = DemoDataGenerator(n_normal_accounts=20, n_rings=1, simulation_days=15, seed=7)
    gen2 = DemoDataGenerator(n_normal_accounts=20, n_rings=1, simulation_days=15, seed=7)
    df1, gt1 = gen1.generate()
    df2, gt2 = gen2.generate()
    assert len(df1) == len(df2)
    assert gt1[0]["observable_time"] == gt2[0]["observable_time"]


# ------------------------------------------------------------- adapter ----
@pytest.mark.skipif(not DEMO_DIR.exists(), reason="run scripts/generate_demo_data.py first")
def test_demo_adapter_loads_generated_data():
    adapter = DemoAdapter(DEMO_DIR)
    df = adapter.load()
    result = adapter.validate(df)
    assert result.is_valid
    assert len(df) > 0
    assert set(df["dataset_source"].unique()) == {"demo"}

    gt = adapter.load_ground_truth()
    assert len(gt) >= 1
    for g in gt:
        assert "observable_time" in g
        assert "ring_id" in g
