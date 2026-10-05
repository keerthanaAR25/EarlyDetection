"""
Pattern-involvement indicator features.

FIX #3:
Explicit AML pattern-awareness features for the proposed early-warning
model.

Converts Phase 7 pattern_events into account-window features such as:

    pattern_fan_in
    pattern_fan_out
    pattern_layering
    pattern_split_merge
    pattern_circular_flow
    pattern_rapid_pass_through
    pattern_repeated_intermediary
    pattern_escalating_connectivity

Also adds:

    pattern_event_count
    pattern_type_count
    pattern_strength_sum
    pattern_strength_mean
    pattern_structural_count
    pattern_temporal_count

These features make AML behaviour explicit instead of forcing the
model to infer suspicious behaviour only from generic transaction
activity features.

No future-window information is introduced here because features are
constructed only from the supplied pattern events and their own
window_id.
"""

from __future__ import annotations

import ast

import pandas as pd

from src.models.feature_groups import FUND_FLOW_FEATURES


# ============================================================
# PATTERN DEFINITIONS
# ============================================================

PATTERN_TYPES = [
    "fan_in",
    "fan_out",
    "layering",
    "split_merge",
    "circular_flow",
    "rapid_pass_through",
    "repeated_intermediary",
    "escalating_connectivity",
]

_PATTERN_TO_COLUMN = {
    pattern: f"pattern_{pattern}"
    for pattern in PATTERN_TYPES
}


STRUCTURAL_PATTERNS = {
    "fan_in",
    "fan_out",
    "layering",
    "split_merge",
}

TEMPORAL_PATTERNS = {
    "circular_flow",
    "rapid_pass_through",
    "repeated_intermediary",
    "escalating_connectivity",
}


# ============================================================
# ACCOUNT PARSER
# ============================================================

def _parse_accounts(value):
    """
    Safely convert the accounts field into a list.

    Handles:
        - Python lists
        - tuples
        - sets
        - stringified lists
        - scalar account values
        - empty/null values

    Uses ast.literal_eval instead of eval.
    """

    if value is None:
        return []

    if isinstance(value, float) and pd.isna(value):
        return []

    if isinstance(value, (list, tuple, set)):
        return list(value)

    if isinstance(value, str):

        value = value.strip()

        if not value:
            return []

        try:
            parsed = ast.literal_eval(value)

            if isinstance(parsed, (list, tuple, set)):
                return list(parsed)

            return [parsed]

        except (ValueError, SyntaxError):
            return [value]

    return [value]


# ============================================================
# BUILD PATTERN INDICATOR FEATURES
# ============================================================

def build_pattern_indicator_features(
    pattern_events_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Convert pattern events into account-window AML pattern features.

    Required input columns:

        pattern_type
        window_id
        accounts

    Optional input:

        pattern_strength

    Output contains one row per:

        window_id + account_id

    with explicit AML pattern indicators and aggregate pattern
    awareness features.
    """

    output_columns = [
        "window_id",
        "account_id",
    ] + FUND_FLOW_FEATURES + [
        "pattern_event_count",
        "pattern_type_count",
        "pattern_strength_sum",
        "pattern_strength_mean",
        "pattern_structural_count",
        "pattern_temporal_count",
    ]

    # --------------------------------------------------------
    # Empty input
    # --------------------------------------------------------

    if pattern_events_df is None or pattern_events_df.empty:
        return pd.DataFrame(columns=output_columns)

    rows = []

    # --------------------------------------------------------
    # Process pattern events
    # --------------------------------------------------------

    for row in pattern_events_df.itertuples(index=False):

        pattern_type = getattr(
            row,
            "pattern_type",
            None,
        )

        if pattern_type is None:
            continue

        pattern_type = str(pattern_type).strip()

        if pattern_type not in PATTERN_TYPES:
            continue

        window_id = getattr(
            row,
            "window_id",
            None,
        )

        accounts = _parse_accounts(
            getattr(
                row,
                "accounts",
                None,
            )
        )

        if not accounts:
            continue

        # Pattern strength is optional.
        strength = getattr(
            row,
            "pattern_strength",
            1.0,
        )

        try:
            strength = float(strength)
        except (TypeError, ValueError):
            strength = 1.0

        if pd.isna(strength):
            strength = 1.0

        indicator_column = _PATTERN_TO_COLUMN[pattern_type]

        for account in accounts:

            if account is None:
                continue

            if isinstance(account, float) and pd.isna(account):
                continue

            account_id = str(account).strip()

            if not account_id:
                continue

            rows.append(
                {
                    "window_id": window_id,
                    "account_id": account_id,
                    indicator_column: 1,
                    "_pattern_strength": strength,
                    "_pattern_type": pattern_type,
                }
            )

    # --------------------------------------------------------
    # No usable rows
    # --------------------------------------------------------

    if not rows:
        return pd.DataFrame(columns=output_columns)

    long_df = pd.DataFrame(rows)

    # ========================================================
    # NORMALIZE KEYS
    # ========================================================

    long_df["window_id"] = pd.to_numeric(
        long_df["window_id"],
        errors="coerce",
    )

    long_df["account_id"] = (
        long_df["account_id"]
        .astype(str)
        .str.strip()
    )

    long_df = long_df.dropna(
        subset=[
            "window_id",
            "account_id",
        ]
    )

    long_df["window_id"] = (
        long_df["window_id"]
        .astype(int)
    )

    # ========================================================
    # INDIVIDUAL PATTERN INDICATORS
    # ========================================================

    indicator_cols = [
        _PATTERN_TO_COLUMN[p]
        for p in PATTERN_TYPES
    ]

    for col in indicator_cols:
        if col not in long_df.columns:
            long_df[col] = 0

    for col in indicator_cols:
        long_df[col] = (
            pd.to_numeric(
                long_df[col],
                errors="coerce",
            )
            .fillna(0)
            .astype(int)
        )

    # ========================================================
    # AGGREGATE BY ACCOUNT + WINDOW
    # ========================================================

    group_keys = [
        "window_id",
        "account_id",
    ]

    # Pattern indicators use MAX:
    # if an account participates in a pattern during a window,
    # the indicator becomes 1.
    indicators = (
        long_df
        .groupby(group_keys)[indicator_cols]
        .max()
    )

    # Number of pattern events involving the account.
    event_counts = (
        long_df
        .groupby(group_keys)
        .size()
        .rename("pattern_event_count")
    )

    # Number of different AML pattern types.
    type_counts = (
        long_df
        .groupby(group_keys)["_pattern_type"]
        .nunique()
        .rename("pattern_type_count")
    )

    # Pattern-strength statistics.
    strength_sum = (
        long_df
        .groupby(group_keys)["_pattern_strength"]
        .sum()
        .rename("pattern_strength_sum")
    )

    strength_mean = (
        long_df
        .groupby(group_keys)["_pattern_strength"]
        .mean()
        .rename("pattern_strength_mean")
    )

    # Structural pattern count.
    structural_mask = long_df["_pattern_type"].isin(
        STRUCTURAL_PATTERNS
    )

    structural_count = (
        long_df.loc[structural_mask]
        .groupby(group_keys)
        .size()
        .rename("pattern_structural_count")
    )

    # Temporal pattern count.
    temporal_mask = long_df["_pattern_type"].isin(
        TEMPORAL_PATTERNS
    )

    temporal_count = (
        long_df.loc[temporal_mask]
        .groupby(group_keys)
        .size()
        .rename("pattern_temporal_count")
    )

    # ========================================================
    # COMBINE
    # ========================================================

    wide = indicators.copy()

    wide = wide.join(event_counts)
    wide = wide.join(type_counts)
    wide = wide.join(strength_sum)
    wide = wide.join(strength_mean)
    wide = wide.join(structural_count)
    wide = wide.join(temporal_count)

    wide = wide.reset_index()

    # ========================================================
    # FILL MISSING VALUES
    # ========================================================

    count_columns = [
        "pattern_event_count",
        "pattern_type_count",
        "pattern_structural_count",
        "pattern_temporal_count",
    ]

    for col in count_columns:
        wide[col] = (
            pd.to_numeric(
                wide[col],
                errors="coerce",
            )
            .fillna(0)
            .astype(int)
        )

    for col in [
        "pattern_strength_sum",
        "pattern_strength_mean",
    ]:
        wide[col] = (
            pd.to_numeric(
                wide[col],
                errors="coerce",
            )
            .fillna(0.0)
        )

    for col in indicator_cols:
        wide[col] = (
            pd.to_numeric(
                wide[col],
                errors="coerce",
            )
            .fillna(0)
            .astype(int)
        )

    # ========================================================
    # GUARANTEE FUND_FLOW_FEATURES
    # ========================================================

    for col in FUND_FLOW_FEATURES:

        if col not in wide.columns:
            wide[col] = 0

    # ========================================================
    # FINAL SCHEMA
    # ========================================================

    return wide[
        output_columns
    ].reset_index(drop=True)


# ============================================================
# ATTACH PATTERN INDICATORS
# ============================================================

def attach_pattern_indicators(
    feature_table: pd.DataFrame,
    indicator_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge AML pattern features into the main account-window
    feature table.

    Explicitly normalizes:

        window_id
        account_id

    on BOTH dataframes before merging.
    """

    feature_table = feature_table.copy()
    indicator_df = indicator_df.copy()

    # ========================================================
    # NORMALIZE FEATURE TABLE KEYS
    # ========================================================

    feature_table["window_id"] = pd.to_numeric(
        feature_table["window_id"],
        errors="coerce",
    )

    feature_table["account_id"] = (
        feature_table["account_id"]
        .astype(str)
        .str.strip()
    )

    # ========================================================
    # NORMALIZE INDICATOR TABLE KEYS
    # ========================================================

    indicator_df["window_id"] = pd.to_numeric(
        indicator_df["window_id"],
        errors="coerce",
    )

    indicator_df["account_id"] = (
        indicator_df["account_id"]
        .astype(str)
        .str.strip()
    )

    # ========================================================
    # REMOVE INVALID KEYS
    # ========================================================

    feature_table = feature_table.dropna(
        subset=[
            "window_id",
            "account_id",
        ]
    )

    indicator_df = indicator_df.dropna(
        subset=[
            "window_id",
            "account_id",
        ]
    )

    feature_table["window_id"] = (
        feature_table["window_id"]
        .astype(int)
    )

    indicator_df["window_id"] = (
        indicator_df["window_id"]
        .astype(int)
    )

    # ========================================================
    # ENSURE ALL PATTERN FEATURES EXIST
    # ========================================================

    extra_pattern_features = [
        "pattern_event_count",
        "pattern_type_count",
        "pattern_strength_sum",
        "pattern_strength_mean",
        "pattern_structural_count",
        "pattern_temporal_count",
    ]

    all_pattern_features = list(
        dict.fromkeys(
            list(FUND_FLOW_FEATURES)
            + extra_pattern_features
        )
    )

    for col in all_pattern_features:

        if col not in indicator_df.columns:
            indicator_df[col] = 0

    # ========================================================
    # REMOVE DUPLICATE KEYS
    # ========================================================

    indicator_df = (
        indicator_df
        .drop_duplicates(
            subset=[
                "window_id",
                "account_id",
            ],
            keep="last",
        )
    )

    # ========================================================
    # MERGE
    # ========================================================

    merged = feature_table.merge(
        indicator_df[
            [
                "window_id",
                "account_id",
            ] + all_pattern_features
        ],
        on=[
            "window_id",
            "account_id",
        ],
        how="left",
    )

    # ========================================================
    # FILL PATTERN FEATURES
    # ========================================================

    for col in all_pattern_features:

        if col in [
            "pattern_strength_sum",
            "pattern_strength_mean",
        ]:

            merged[col] = (
                pd.to_numeric(
                    merged[col],
                    errors="coerce",
                )
                .fillna(0.0)
            )

        else:

            merged[col] = (
                pd.to_numeric(
                    merged[col],
                    errors="coerce",
                )
                .fillna(0)
                .astype(int)
            )

    return merged