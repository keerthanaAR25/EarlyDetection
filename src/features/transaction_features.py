"""
Transaction / behavioural features (spec category A).

One row per (account_id, window_id): counts, amounts, dispersion, and
counterparty diversity computed from that window's own transactions
(not cumulative history — see temporal_features.py for rolling/trend
views across windows).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

_EPS = 1e-9


def _herfindahl_concentration(amounts_by_counterparty: pd.Series) -> float:
    """Amount concentration: 1.0 = all volume with a single counterparty,
    close to 0 = evenly spread. Standard Herfindahl-Hirschman index on
    counterparty amount shares."""
    total = amounts_by_counterparty.sum()
    if total <= 0:
        return 0.0
    shares = amounts_by_counterparty / total
    return float((shares ** 2).sum())


def compute_transaction_features(window_df: pd.DataFrame, window_id: int) -> pd.DataFrame:
    """
    window_df: transactions belonging to ONE window (sender/receiver/amount columns).
    Returns one row per account active (as sender or receiver) in this window.
    """
    if window_df.empty:
        return pd.DataFrame()

    out = window_df.groupby("sender").agg(
        out_count=("transaction_id", "count"),
        out_amount=("amount", "sum"),
        out_amount_mean=("amount", "mean"),
        out_amount_median=("amount", "median"),
        out_amount_std=("amount", "std"),
    )
    out.index.name = "account_id"

    inc = window_df.groupby("receiver").agg(
        in_count=("transaction_id", "count"),
        in_amount=("amount", "sum"),
        in_amount_mean=("amount", "mean"),
        in_amount_median=("amount", "median"),
        in_amount_std=("amount", "std"),
    )
    inc.index.name = "account_id"

    unique_receivers = window_df.groupby("sender")["receiver"].nunique().rename("unique_receivers")
    unique_receivers.index.name = "account_id"
    unique_senders = window_df.groupby("receiver")["sender"].nunique().rename("unique_senders")
    unique_senders.index.name = "account_id"

    repeated_receivers = (
        window_df.groupby(["sender", "receiver"]).size().reset_index(name="n")
        .groupby("sender")["n"].apply(lambda s: int((s > 1).sum())).rename("repeated_receiver_count")
    )
    repeated_receivers.index.name = "account_id"
    repeated_senders = (
        window_df.groupby(["receiver", "sender"]).size().reset_index(name="n")
        .groupby("receiver")["n"].apply(lambda s: int((s > 1).sum())).rename("repeated_sender_count")
    )
    repeated_senders.index.name = "account_id"

    out_concentration = (
        window_df.groupby(["sender", "receiver"])["amount"].sum().reset_index()
        .groupby("sender").apply(lambda g: _herfindahl_concentration(g.set_index("receiver")["amount"]))
        .rename("out_amount_concentration")
    )
    out_concentration.index.name = "account_id"

    features = pd.concat(
        [out, inc, unique_receivers, unique_senders, repeated_receivers, repeated_senders, out_concentration],
        axis=1,
    ).fillna(0)

    features["total_count"] = features["out_count"] + features["in_count"]
    features["total_amount"] = features["out_amount"] + features["in_amount"]
    features["log_total_amount"] = np.log1p(features["total_amount"])
    features["amount_ratio_out_in"] = features["out_amount"] / (features["in_amount"] + _EPS)
    features["unique_counterparties"] = features["unique_receivers"] + features["unique_senders"]

    features = features.reset_index()
    features.insert(0, "window_id", window_id)
    return features
