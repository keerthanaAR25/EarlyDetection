"""
Canonical transaction schema.

Every dataset adapter (AMLSim, Elliptic, Demo/Synthetic) must produce a
pandas DataFrame with exactly these columns and dtypes. Everything
downstream of src/data/ operates only on this normalized schema and
must never know which raw dataset it came from.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

# Canonical column names, in order.
SCHEMA_COLUMNS = [
    "transaction_id",  # str, globally unique
    "sender",          # str, account id
    "receiver",        # str, account id
    "amount",          # float, > 0
    "timestamp",        # pandas.Timestamp (UTC), required, sortable
    "label",           # int8: 1 = part of a known laundering scenario, 0 = normal,
                       #       -1 = unknown/unlabeled (e.g. real-world unlabeled data)
    "scenario_id",     # str or "" — dataset-native scenario/typology identifier
    "ring_id",         # str or "" — candidate/ground-truth ring identifier
    "dataset_source",  # str: "amlsim" | "elliptic" | "demo"
]

SCHEMA_DTYPES = {
    "transaction_id": "string",
    "sender": "string",
    "receiver": "string",
    "amount": "float64",
    "timestamp": "datetime64[ns, UTC]",
    "label": "int8",
    "scenario_id": "string",
    "ring_id": "string",
    "dataset_source": "string",
}


@dataclass
class SchemaValidationResult:
    is_valid: bool
    n_rows: int
    missing_columns: list[str] = field(default_factory=list)
    dtype_errors: list[str] = field(default_factory=list)
    row_errors: dict[str, int] = field(default_factory=dict)  # error_name -> count


def empty_schema_frame() -> pd.DataFrame:
    """Return a zero-row DataFrame with the canonical columns/dtypes."""
    df = pd.DataFrame({col: pd.Series(dtype=dt) for col, dt in SCHEMA_DTYPES.items()})
    return df[SCHEMA_COLUMNS]


def coerce_to_schema(df: pd.DataFrame, dataset_source: str) -> pd.DataFrame:
    """
    Best-effort coercion of an adapter's raw-mapped DataFrame into the
    canonical schema. Does NOT drop or silently fix invalid rows —
    that is the job of src/preprocessing/, which runs after validation
    and logs every transformation it makes.
    """
    out = df.copy()

    for col in SCHEMA_COLUMNS:
        if col not in out.columns:
            if col == "dataset_source":
                out[col] = dataset_source
            elif col in ("scenario_id", "ring_id"):
                out[col] = ""
            elif col == "label":
                out[col] = -1
            else:
                raise ValueError(
                    f"Adapter for '{dataset_source}' did not provide required "
                    f"column '{col}' and it has no safe default."
                )

    out["transaction_id"] = out["transaction_id"].astype("string")
    out["sender"] = out["sender"].astype("string")
    out["receiver"] = out["receiver"].astype("string")
    out["amount"] = pd.to_numeric(out["amount"], errors="coerce")
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce", utc=True)
    out["label"] = pd.to_numeric(out["label"], errors="coerce").fillna(-1).astype("int8")
    out["scenario_id"] = out["scenario_id"].fillna("").astype("string")
    out["ring_id"] = out["ring_id"].fillna("").astype("string")
    out["dataset_source"] = out["dataset_source"].astype("string")

    return out[SCHEMA_COLUMNS]


def validate_schema(df: pd.DataFrame) -> SchemaValidationResult:
    """Structural validation only (columns/dtypes). Row-level quality
    checks (nulls, duplicates, invalid amounts, etc.) live in
    src/preprocessing/validation.py, which produces the full
    data_quality_report."""
    missing = [c for c in SCHEMA_COLUMNS if c not in df.columns]
    dtype_errors = []
    if not missing:
        for col, expected in SCHEMA_DTYPES.items():
            actual = str(df[col].dtype)
            # allow tz-naive/aware and string-family variance; strict check on numerics
            if col in ("amount",) and "float" not in actual:
                dtype_errors.append(f"{col}: expected float, got {actual}")
            if col in ("label",) and "int" not in actual:
                dtype_errors.append(f"{col}: expected int, got {actual}")

    return SchemaValidationResult(
        is_valid=(not missing and not dtype_errors),
        n_rows=len(df),
        missing_columns=missing,
        dtype_errors=dtype_errors,
    )
