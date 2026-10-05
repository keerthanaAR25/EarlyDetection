"""
Temporal features (spec category B).

Unlike transaction_features.py (single-window snapshot), these need
each account's activity HISTORY across windows, so they operate over
the full per-account transaction timeline, evaluated as of each
window's end — never using transactions that occur after that window
(this is the same no-leakage principle enforced project-wide).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _burstiness(gaps_seconds: np.ndarray) -> float:
    """Goh & Barabasi burstiness parameter: (sigma - mu) / (sigma + mu).
    -1 = perfectly regular, 0 = Poisson/random, +1 = highly bursty."""
    if len(gaps_seconds) < 2:
        return np.nan
    mu, sigma = gaps_seconds.mean(), gaps_seconds.std()
    if mu + sigma == 0:
        return np.nan
    return float((sigma - mu) / (sigma + mu))


def _compute_temporal_features_numpy(
    account_id: str,
    times_ns: np.ndarray,          # this account's timestamps up to window_end, sorted, int64 ns
    window_start_ns: np.int64,
    window_end_ns: np.int64,
    window_hours: float,
    prior_window_count: int | None,
    lookback_window_starts: list,
    window_counts_by_start: dict,
) -> dict:
    """
    Numpy-native equivalent of compute_temporal_features, operating on
    int64-nanosecond arrays instead of pandas Series/Timestamps.

    Found necessary by direct profiling at real-data scale: the
    pandas-Series version's per-call overhead (Series construction,
    boolean-mask comparison, dtype dispatch — all real costs even on a
    handful of values) dominated total runtime once called once per
    account per window (4,638 accounts x hundreds of pandas operations
    each, verified via cProfile). Produces numerically identical
    results to compute_temporal_features — cross-checked in
    tests/test_features.py — just without the per-call pandas tax.
    """
    lo = np.searchsorted(times_ns, window_start_ns, side="left")
    hi = np.searchsorted(times_ns, window_end_ns, side="left")
    times_in_window = times_ns[lo:hi]

    velocity = len(times_in_window) / window_hours

    if len(times_in_window) >= 2:
        gaps = np.diff(times_in_window) / 1e9  # ns -> seconds
        median_gap, min_gap, max_gap = float(np.median(gaps)), float(gaps.min()), float(gaps.max())
        burstiness = _burstiness(gaps)
    else:
        median_gap = min_gap = max_gap = np.nan
        burstiness = np.nan

    current_count = len(times_in_window)
    activity_acceleration = current_count - prior_window_count if prior_window_count is not None else np.nan

    trend_counts = [window_counts_by_start.get(ws, 0) for ws in lookback_window_starts]
    if len(trend_counts) >= 2 and any(trend_counts):
        x = np.arange(len(trend_counts))
        slope = float(np.polyfit(x, trend_counts, 1)[0])
    else:
        slope = np.nan

    n_before = len(times_ns)
    if n_before:
        days_span = max(1, int((window_end_ns - times_ns.min()) / 86_400_000_000_000) or 1)
        historical_avg = n_before / days_span
    else:
        historical_avg = 0.0
    recent_vs_historical = current_count / (historical_avg + 1e-9) if historical_avg else np.nan

    persistence = 0
    for ws in reversed(lookback_window_starts):
        if window_counts_by_start.get(ws, 0) > 0:
            persistence += 1
        else:
            break

    return {
        "account_id": account_id,
        "transaction_velocity": velocity,
        "median_time_gap_seconds": median_gap,
        "min_time_gap_seconds": min_gap,
        "max_time_gap_seconds": max_gap,
        "burstiness": burstiness,
        "activity_acceleration": activity_acceleration,
        "activity_trend_slope": slope,
        "recent_vs_historical_activity": recent_vs_historical,
        "activity_persistence_windows": persistence,
    }


def compute_temporal_features(
    account_id: str,
    account_tx_times: pd.Series,  # all this account's transaction timestamps, sorted, up to window_end
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    prior_window_count: int | None,
    lookback_window_starts: list,  # window starts for the trailing N windows, for trend/slope
    window_counts_by_start: dict,  # {window_start: count} for trend calc, already leak-safe
) -> dict:
    times_in_window = account_tx_times[(account_tx_times >= window_start) & (account_tx_times < window_end)]
    times_before = account_tx_times[account_tx_times < window_end]

    window_hours = max((window_end - window_start).total_seconds() / 3600.0, 1e-9)
    velocity = len(times_in_window) / window_hours

    gaps = times_in_window.sort_values().diff().dropna().dt.total_seconds().to_numpy()
    if len(gaps) == 0:
        median_gap = min_gap = max_gap = np.nan
    else:
        median_gap, min_gap, max_gap = float(np.median(gaps)), float(gaps.min()), float(gaps.max())

    burstiness = _burstiness(gaps)

    current_count = len(times_in_window)
    activity_acceleration = (
        current_count - prior_window_count if prior_window_count is not None else np.nan
    )

    # trend/slope over the trailing windows' counts (simple linear fit)
    trend_counts = [window_counts_by_start.get(ws, 0) for ws in lookback_window_starts]
    if len(trend_counts) >= 2 and any(trend_counts):
        x = np.arange(len(trend_counts))
        slope = float(np.polyfit(x, trend_counts, 1)[0])
    else:
        slope = np.nan

    historical_avg = len(times_before) / max(1, (window_end - account_tx_times.min()).days or 1) if len(times_before) else 0.0
    recent_vs_historical = current_count / (historical_avg + 1e-9) if historical_avg else np.nan

    # persistence: consecutive trailing windows (from lookback list, most recent first) with count > 0
    persistence = 0
    for ws in reversed(lookback_window_starts):
        if window_counts_by_start.get(ws, 0) > 0:
            persistence += 1
        else:
            break

    return {
        "account_id": account_id,
        "transaction_velocity": velocity,
        "median_time_gap_seconds": median_gap,
        "min_time_gap_seconds": min_gap,
        "max_time_gap_seconds": max_gap,
        "burstiness": burstiness,
        "activity_acceleration": activity_acceleration,
        "activity_trend_slope": slope,
        "recent_vs_historical_activity": recent_vs_historical,
        "activity_persistence_windows": persistence,
    }


def compute_temporal_features_for_window(
    df: pd.DataFrame,
    window_id: int,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    all_window_bounds: list,  # list of WindowBounds, full sequence
    lookback: int = 3,
) -> pd.DataFrame:
    """Compute temporal features for every account active up to window_end.

    NOTE: kept for backward compatibility / small-scale use (demo data,
    tests). At real-data scale, use TemporalFeatureComputer instead —
    this function rebuilds a groupby over the ENTIRE historical
    dataframe on every call, which is fine once but was found to cost
    ~6 seconds per window when called once per window across a
    720-window real run (verified directly): a full O(n) rebuild
    repeated 720 times. TemporalFeatureComputer precomputes the
    per-account timestamp index ONCE and reuses it across all windows.
    """
    accounts = pd.unique(pd.concat([df.loc[df["timestamp"] < window_end, "sender"],
                                     df.loc[df["timestamp"] < window_end, "receiver"]]))
    if len(accounts) == 0:
        return pd.DataFrame()

    prior_bounds = [b for b in all_window_bounds if b.window_id < window_id]
    lookback_bounds = prior_bounds[-lookback:] if prior_bounds else []
    lookback_starts = [b.start for b in lookback_bounds]
    prior_window_bounds = prior_bounds[-1] if prior_bounds else None

    rows = []
    sender_groups = df.groupby("sender")["timestamp"]
    receiver_groups = df.groupby("receiver")["timestamp"]

    for account in accounts:
        s_times = sender_groups.get_group(account) if account in sender_groups.groups else pd.Series(dtype="datetime64[ns, UTC]")
        r_times = receiver_groups.get_group(account) if account in receiver_groups.groups else pd.Series(dtype="datetime64[ns, UTC]")
        all_times = pd.concat([s_times, r_times]).sort_values()
        all_times = all_times[all_times < window_end]
        if all_times.empty:
            continue

        window_counts_by_start = {}
        for b in lookback_bounds:
            cnt = int(((all_times >= b.start) & (all_times < b.end)).sum())
            window_counts_by_start[b.start] = cnt

        prior_count = None
        if prior_window_bounds is not None:
            prior_count = int(((all_times >= prior_window_bounds.start) & (all_times < prior_window_bounds.end)).sum())

        feat = compute_temporal_features(
            account_id=account,
            account_tx_times=all_times,
            window_start=window_start,
            window_end=window_end,
            prior_window_count=prior_count,
            lookback_window_starts=lookback_starts,
            window_counts_by_start=window_counts_by_start,
        )
        rows.append(feat)

    result = pd.DataFrame(rows)
    if not result.empty:
        result.insert(0, "window_id", window_id)
    return result


class TemporalFeatureComputer:
    """
    Precomputes each account's sorted transaction-timestamp index ONCE,
    then answers per-window queries via numpy searchsorted instead of
    rebuilding a pandas groupby over the entire historical dataframe on
    every window. Same output semantics as
    compute_temporal_features_for_window (verified in
    tests/test_features.py) — just built for real-data scale.
    """

    def __init__(self, df: pd.DataFrame):
        combined = pd.concat(
            [
                df[["sender", "timestamp"]].rename(columns={"sender": "account"}),
                df[["receiver", "timestamp"]].rename(columns={"receiver": "account"}),
            ],
            ignore_index=True,
        )
        self.account_times: dict = {
            account: np.sort(group.to_numpy(dtype="datetime64[ns]").astype(np.int64))
            for account, group in combined.groupby("account")["timestamp"]
        }

        first_seen = combined.groupby("account")["timestamp"].min().sort_values()
        self._accounts_by_first_seen = first_seen.index.to_numpy()
        self._first_seen_ns = first_seen.to_numpy(dtype="datetime64[ns]").astype(np.int64)

    def _active_accounts_before(self, window_end: pd.Timestamp) -> np.ndarray:
        end_ns = np.int64(pd.Timestamp(window_end).value)
        idx = np.searchsorted(self._first_seen_ns, end_ns, side="left")
        return self._accounts_by_first_seen[:idx]

    def compute_for_window(
        self, window_id: int, window_start: pd.Timestamp, window_end: pd.Timestamp,
        all_window_bounds: list, lookback: int = 3,
    ) -> pd.DataFrame:
        accounts = self._active_accounts_before(window_end)
        if len(accounts) == 0:
            return pd.DataFrame()

        prior_bounds = [b for b in all_window_bounds if b.window_id < window_id]
        lookback_bounds = prior_bounds[-lookback:] if prior_bounds else []
        lookback_starts = [b.start for b in lookback_bounds]
        prior_window_bounds = prior_bounds[-1] if prior_bounds else None

        end_ns = np.int64(pd.Timestamp(window_end).value)
        lookback_bound_ns = [
            (np.int64(pd.Timestamp(b.start).value), np.int64(pd.Timestamp(b.end).value)) for b in lookback_bounds
        ]
        prior_ns = (
            (np.int64(pd.Timestamp(prior_window_bounds.start).value), np.int64(pd.Timestamp(prior_window_bounds.end).value))
            if prior_window_bounds is not None else None
        )

        rows = []
        for account in accounts:
            times_ns = self.account_times.get(account)
            if times_ns is None:
                continue
            cutoff = np.searchsorted(times_ns, end_ns, side="left")
            times_ns = times_ns[:cutoff]
            if len(times_ns) == 0:
                continue

            window_counts_by_start = {}
            for (start_ns, end_ns_b), b in zip(lookback_bound_ns, lookback_bounds):
                lo = np.searchsorted(times_ns, start_ns, side="left")
                hi = np.searchsorted(times_ns, end_ns_b, side="left")
                window_counts_by_start[b.start] = int(hi - lo)

            prior_count = None
            if prior_ns is not None:
                lo = np.searchsorted(times_ns, prior_ns[0], side="left")
                hi = np.searchsorted(times_ns, prior_ns[1], side="left")
                prior_count = int(hi - lo)

            all_times = pd.Series(pd.to_datetime(times_ns, utc=True))
            feat = _compute_temporal_features_numpy(
                account_id=account,
                times_ns=times_ns,
                window_start_ns=np.int64(pd.Timestamp(window_start).value),
                window_end_ns=end_ns,
                window_hours=max((window_end - window_start).total_seconds() / 3600.0, 1e-9),
                prior_window_count=prior_count,
                lookback_window_starts=lookback_starts,
                window_counts_by_start=window_counts_by_start,
            )
            rows.append(feat)

        result = pd.DataFrame(rows)
        if not result.empty:
            result.insert(0, "window_id", window_id)
        return result
