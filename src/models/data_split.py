"""
Chronological train/validation/test split.

MANDATORY per the project spec: never randomly shuffle temporal
records. Splits are made on window_id boundaries (earliest windows to
train, middle to validation, latest to test), so no information from
a later point in time ever appears in training or validation.
"""
from __future__ import annotations

import pandas as pd


def chronological_split(
    feature_table: pd.DataFrame,
    train_fraction: float = 0.6,
    val_fraction: float = 0.2,
) -> dict:
    windows = sorted(feature_table["window_id"].unique())
    n = len(windows)
    train_end = int(n * train_fraction)
    val_end = int(n * (train_fraction + val_fraction))

    train_windows = set(windows[:train_end])
    val_windows = set(windows[train_end:val_end])
    test_windows = set(windows[val_end:])

    train_df = feature_table[feature_table["window_id"].isin(train_windows)].copy()
    val_df = feature_table[feature_table["window_id"].isin(val_windows)].copy()
    test_df = feature_table[feature_table["window_id"].isin(test_windows)].copy()

    return {
        "train": train_df,
        "val": val_df,
        "test": test_df,
        "train_window_range": [min(train_windows), max(train_windows)] if train_windows else None,
        "val_window_range": [min(val_windows), max(val_windows)] if val_windows else None,
        "test_window_range": [min(test_windows), max(test_windows)] if test_windows else None,
    }
