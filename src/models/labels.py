"""
Account-window label construction.

The canonical schema labels TRANSACTIONS (label 0/1), but the feature
table (Phase 6) is at ACCOUNT-WINDOW granularity. This derives the
target the baselines and proposed model predict: an account-window row
is positive (y=1) if that account participated, as sender or receiver,
in at least one label==1 transaction WITHIN that window. This is
leak-safe by construction — it only uses that window's own
transactions, never a later window's.
"""
from __future__ import annotations

import pandas as pd


def build_account_window_labels(df: pd.DataFrame, window_bounds: list) -> pd.DataFrame:
    rows = []
    for bounds in window_bounds:
        window_df = df[(df["timestamp"] >= bounds.start) & (df["timestamp"] < bounds.end)]
        if window_df.empty:
            continue
        positive_tx = window_df[window_df["label"] == 1]
        positive_accounts = set(positive_tx["sender"]) | set(positive_tx["receiver"])
        all_accounts = set(window_df["sender"]) | set(window_df["receiver"])
        for account in all_accounts:
            rows.append({"window_id": bounds.window_id, "account_id": account, "y": int(account in positive_accounts)})
    return pd.DataFrame(rows)


def build_forecast_labels(df: pd.DataFrame, window_bounds: list, horizon: int = 2) -> pd.DataFrame:
    """
    The genuine EARLY-WARNING target, as opposed to build_account_window_labels'
    same-window target.

    Found necessary by direct verification: training on the same-window
    label produced a suspicious perfect 1.0 ROC-AUC. Investigating why
    showed the same-window label and same-window features aren't
    independent — an account's total_amount/transaction_velocity in a
    window is dominated by the very ring transaction that makes that
    window positive in the first place (positive rows: median
    total_amount 939.6; negative rows: median 0.0, in the SAME window).
    The model wasn't forecasting anything; it was detecting the labeled
    transaction's own footprint, which is a near-tautology, not early
    warning.

    This target instead asks: given everything observable up to and
    including window t (features are already leak-safe from Phase 6 —
    they never look past window t), will this account be part of a
    labeled transaction in any of the NEXT `horizon` windows
    (t+1 .. t+horizon), which the features at window t cannot see?
    That is a real forecasting task, and is what "early warning" means
    operationally in this project.
    """
    same_window = build_account_window_labels(df, window_bounds)
    same_window = same_window.rename(columns={"y": "y_same_window"})

    positive_by_window = {
        wid: set(g[g["y_same_window"] == 1]["account_id"])
        for wid, g in same_window.groupby("window_id")
    }

    all_window_ids = sorted({b.window_id for b in window_bounds})
    rows = []
    for wid in all_window_ids:
        accounts_active_at_t = set(same_window[same_window["window_id"] == wid]["account_id"])
        future_positive_accounts = set()
        for future_wid in range(wid + 1, wid + 1 + horizon):
            future_positive_accounts |= positive_by_window.get(future_wid, set())
        for account in accounts_active_at_t:
            rows.append({
                "window_id": wid,
                "account_id": account,
                "y": int(account in future_positive_accounts),
            })
    return pd.DataFrame(rows)


def attach_labels(feature_table: pd.DataFrame, labels_df: pd.DataFrame) -> pd.DataFrame:
    merged = feature_table.merge(labels_df, on=["window_id", "account_id"], how="left")
    merged["y"] = merged["y"].fillna(0).astype(int)
    return merged
