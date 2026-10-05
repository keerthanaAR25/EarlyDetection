#!/usr/bin/env python3

"""
ALERT-TRANSACTION TEMPORAL GROUND TRUTH
=======================================

Uses AMLSim alert_transactions.csv as the temporal
ground truth source.

Why?
-----
alert_accounts.csv contains 742 AML accounts but its
start/end columns are empty.

alert_transactions.csv contains 671 actual AML alert
transactions with:

    alert_id
    tran_id
    orig_acct
    bene_acct
    tran_timestamp

Therefore:

    AML observable time
        =
    earliest transaction timestamp belonging to an alert.

This script compares those AML alert events against
our generated ring candidates.

Outputs
-------
results/alert_transaction_ground_truth.csv
results/alert_transaction_ground_truth_summary.json
results/early_warning_ground_truth.csv
"""

from pathlib import Path
import json
import pandas as pd


# ============================================================
# PROJECT PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent

RESULTS_DIR = ROOT / "results"

ALERT_TRANSACTIONS = (
    ROOT
    / "data"
    / "raw"
    / "amlsim"
    / "alert_transactions.csv"
)

RING_CANDIDATES = (
    RESULTS_DIR
    / "ring_candidates.json"
)

OUTPUT_CSV = (
    RESULTS_DIR
    / "alert_transaction_ground_truth.csv"
)

OUTPUT_JSON = (
    RESULTS_DIR
    / "alert_transaction_ground_truth_summary.json"
)

LEAD_TIME_CSV = (
    RESULTS_DIR
    / "early_warning_ground_truth.csv"
)


# ============================================================
# TIMESTAMP
# ============================================================

def parse_timestamp(value):

    if value is None:
        return pd.NaT

    if pd.isna(value):
        return pd.NaT

    return pd.to_datetime(
        value,
        errors="coerce",
        utc=True
    )


# ============================================================
# LOAD ALERT TRANSACTIONS
# ============================================================

def load_alert_transactions():

    print()
    print("=" * 70)
    print("LOADING AML ALERT TRANSACTIONS")
    print("=" * 70)

    print(
        "Path:",
        ALERT_TRANSACTIONS
    )

    if not ALERT_TRANSACTIONS.exists():

        raise FileNotFoundError(
            f"\nFile not found:\n"
            f"{ALERT_TRANSACTIONS}"
        )

    df = pd.read_csv(
        ALERT_TRANSACTIONS,
        dtype=str
    )

    print(
        f"Rows: {len(df):,}"
    )

    print(
        "Columns:",
        df.columns.tolist()
    )

    required = [
        "alert_id",
        "tran_id",
        "orig_acct",
        "bene_acct",
        "tran_timestamp"
    ]

    missing = [
        c
        for c in required
        if c not in df.columns
    ]

    if missing:

        raise ValueError(
            "Missing required columns: "
            + ", ".join(missing)
        )

    # --------------------------------------------------------
    # NORMALIZE
    # --------------------------------------------------------

    df["alert_id"] = (
        df["alert_id"]
        .astype(str)
        .str.strip()
    )

    df["tran_id"] = (
        df["tran_id"]
        .astype(str)
        .str.strip()
    )

    df["orig_acct"] = (
        df["orig_acct"]
        .astype(str)
        .str.strip()
    )

    df["bene_acct"] = (
        df["bene_acct"]
        .astype(str)
        .str.strip()
    )

    df["tran_timestamp"] = (
        df["tran_timestamp"]
        .apply(parse_timestamp)
    )

    # --------------------------------------------------------
    # TIMESTAMP DIAGNOSTICS
    # --------------------------------------------------------

    print()
    print(
        "Valid timestamps:",
        int(
            df["tran_timestamp"]
            .notna()
            .sum()
        )
    )

    print(
        "Invalid timestamps:",
        int(
            df["tran_timestamp"]
            .isna()
            .sum()
        )
    )

    print(
        "Unique alerts:",
        df["alert_id"].nunique()
    )

    print(
        "Unique transactions:",
        df["tran_id"].nunique()
    )

    print(
        "Unique origin accounts:",
        df["orig_acct"].nunique()
    )

    print(
        "Unique beneficiary accounts:",
        df["bene_acct"].nunique()
    )

    return df


# ============================================================
# BUILD AML ALERT EVENTS
# ============================================================

def build_alert_events(alert_transactions):

    print()
    print("=" * 70)
    print("BUILDING AML ALERT EVENTS")
    print("=" * 70)

    events = []

    for alert_id, group in (
        alert_transactions
        .groupby("alert_id")
    ):

        valid = group[
            group["tran_timestamp"].notna()
        ].copy()

        if valid.empty:
            continue

        # ----------------------------------------------------
        # Temporal boundaries
        # ----------------------------------------------------

        first_time = (
            valid["tran_timestamp"]
            .min()
        )

        last_time = (
            valid["tran_timestamp"]
            .max()
        )

        # ----------------------------------------------------
        # Alert participants
        # ----------------------------------------------------

        participants = set()

        for account in valid["orig_acct"]:

            if (
                pd.notna(account)
                and str(account).strip()
            ):

                participants.add(
                    str(account).strip()
                )

        for account in valid["bene_acct"]:

            if (
                pd.notna(account)
                and str(account).strip()
            ):

                participants.add(
                    str(account).strip()
                )

        # ----------------------------------------------------
        # Transaction IDs
        # ----------------------------------------------------

        transaction_ids = set(
            valid["tran_id"]
            .astype(str)
            .tolist()
        )

        # ----------------------------------------------------
        # Alert type
        # ----------------------------------------------------

        alert_type = ""

        if "alert_type" in valid.columns:

            values = (
                valid["alert_type"]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )

            if values:
                alert_type = values[0]

        # ----------------------------------------------------
        # SAR
        # ----------------------------------------------------

        is_sar = ""

        if "is_sar" in valid.columns:

            values = (
                valid["is_sar"]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )

            if values:
                is_sar = values[0]

        # ----------------------------------------------------
        # Store event
        # ----------------------------------------------------

        events.append(
            {
                "alert_id": str(alert_id),

                "alert_type": alert_type,

                "is_sar": is_sar,

                "first_alert_time": first_time,

                "last_alert_time": last_time,

                "n_alert_transactions":
                    len(transaction_ids),

                "n_alert_accounts":
                    len(participants),

                "participants":
                    sorted(participants),

                "transaction_ids":
                    sorted(transaction_ids)
            }
        )

    result = pd.DataFrame(events)

    print(
        "Valid AML alert events:",
        len(result)
    )

    if not result.empty:

        print(
            "Earliest AML alert time:",
            result["first_alert_time"].min()
        )

        print(
            "Latest AML alert time:",
            result["last_alert_time"].max()
        )

    return result


# ============================================================
# LOAD RING CANDIDATES
# ============================================================

def load_ring_candidates():

    print()
    print("=" * 70)
    print("LOADING RING CANDIDATES")
    print("=" * 70)

    print(
        "Path:",
        RING_CANDIDATES
    )

    if not RING_CANDIDATES.exists():

        raise FileNotFoundError(
            f"\nFile not found:\n"
            f"{RING_CANDIDATES}"
        )

    with open(
        RING_CANDIDATES,
        "r",
        encoding="utf-8"
    ) as f:

        candidates = json.load(f)

    print(
        f"Candidates: {len(candidates)}"
    )

    return candidates


# ============================================================
# CANDIDATE ACCOUNTS
# ============================================================

def get_candidate_accounts(candidate):

    accounts = candidate.get(
        "accounts",
        []
    )

    if accounts is None:
        return set()

    return {
        str(a).strip()
        for a in accounts
        if pd.notna(a)
        and str(a).strip()
    }


# ============================================================
# CANDIDATE TIME
# ============================================================

def get_candidate_time(candidate):

    time_span = candidate.get(
        "time_span"
    )

    if not isinstance(
        time_span,
        (list, tuple)
    ):

        return pd.NaT, pd.NaT

    if len(time_span) < 2:

        return pd.NaT, pd.NaT

    start = parse_timestamp(
        time_span[0]
    )

    end = parse_timestamp(
        time_span[1]
    )

    return start, end


# ============================================================
# INTERVAL OVERLAP
# ============================================================

def interval_overlap_seconds(
    start1,
    end1,
    start2,
    end2
):

    if (
        pd.isna(start1)
        or pd.isna(end1)
        or pd.isna(start2)
        or pd.isna(end2)
    ):

        return 0.0

    overlap_start = max(
        start1,
        start2
    )

    overlap_end = min(
        end1,
        end2
    )

    if overlap_end <= overlap_start:

        return 0.0

    return (
        overlap_end - overlap_start
    ).total_seconds()


# ============================================================
# ANALYZE CANDIDATE AGAINST ALERT
# ============================================================

def analyze_pair(
    candidate,
    alert
):

    candidate_id = candidate.get(
        "candidate_ring_id",
        "UNKNOWN"
    )

    candidate_accounts = (
        get_candidate_accounts(
            candidate
        )
    )

    candidate_start, candidate_end = (
        get_candidate_time(candidate)
    )

    alert_accounts = set(
        alert["participants"]
    )

    # --------------------------------------------------------
    # ACCOUNT INTERSECTION
    # --------------------------------------------------------

    common_accounts = (
        candidate_accounts
        &
        alert_accounts
    )

    n_common = len(
        common_accounts
    )

    # --------------------------------------------------------
    # TEMPORAL OVERLAP
    # --------------------------------------------------------

    overlap_seconds = (
        interval_overlap_seconds(
            candidate_start,
            candidate_end,
            alert["first_alert_time"],
            alert["last_alert_time"]
        )
    )

    # --------------------------------------------------------
    # ALERT OCCURS AFTER CANDIDATE START
    # --------------------------------------------------------

    lead_time_seconds = None

    if (
        not pd.isna(candidate_start)
        and not pd.isna(
            alert["first_alert_time"]
        )
    ):

        lead_time_seconds = (
            alert["first_alert_time"]
            -
            candidate_start
        ).total_seconds()

    # --------------------------------------------------------
    # QUALIFICATION
    # --------------------------------------------------------
    #
    # We use >=2 common accounts because a single
    # shared account is too weak to claim that a
    # candidate corresponds to an AML alert.
    #
    # Temporal overlap is required for temporal matching.
    #
    # --------------------------------------------------------

    if (
        n_common >= 2
        and overlap_seconds > 0
    ):

        match_status = (
            "TEMPORAL_GROUND_TRUTH_MATCH"
        )

    elif n_common >= 2:

        match_status = (
            "ACCOUNT_MATCH_NO_TEMPORAL_OVERLAP"
        )

    elif n_common == 1:

        match_status = (
            "SINGLE_ACCOUNT_MATCH"
        )

    else:

        match_status = "NO_MATCH"

    # --------------------------------------------------------
    # EARLY WARNING
    # --------------------------------------------------------

    early_warning = False

    if (
        n_common >= 2
        and lead_time_seconds is not None
        and lead_time_seconds > 0
    ):

        early_warning = True

    # --------------------------------------------------------
    # PATTERNS
    # --------------------------------------------------------

    patterns = candidate.get(
        "patterns",
        []
    )

    if isinstance(patterns, list):

        patterns = ",".join(
            str(x)
            for x in patterns
        )

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    return {

        "candidate_ring_id":
            candidate_id,

        "alert_id":
            alert["alert_id"],

        "alert_type":
            alert["alert_type"],

        "is_sar":
            alert["is_sar"],

        "candidate_accounts":
            len(candidate_accounts),

        "alert_accounts":
            len(alert_accounts),

        "common_accounts":
            n_common,

        "account_overlap_ratio":
            round(
                n_common
                /
                len(candidate_accounts)
                if candidate_accounts
                else 0,
                4
            ),

        "candidate_start":
            (
                candidate_start.isoformat()
                if not pd.isna(candidate_start)
                else ""
            ),

        "candidate_end":
            (
                candidate_end.isoformat()
                if not pd.isna(candidate_end)
                else ""
            ),

        "alert_first_time":
            alert[
                "first_alert_time"
            ].isoformat(),

        "alert_last_time":
            alert[
                "last_alert_time"
            ].isoformat(),

        "n_alert_transactions":
            alert[
                "n_alert_transactions"
            ],

        "overlap_hours":
            round(
                overlap_seconds / 3600,
                4
            ),

        "lead_time_hours":
            (
                round(
                    lead_time_seconds / 3600,
                    4
                )
                if lead_time_seconds is not None
                else None
            ),

        "early_warning":
            early_warning,

        "match_status":
            match_status,

        "patterns":
            patterns,

        "formation_stage":
            candidate.get(
                "formation_stage",
                ""
            ),

        "risk_score":
            candidate.get(
                "risk_score",
                None
            ),

        "common_accounts_list":
            ",".join(
                sorted(common_accounts)
            )
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print(
        "AMLSIM ALERT-TRANSACTION "
        "TEMPORAL GROUND TRUTH"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # LOAD
    # --------------------------------------------------------

    alert_transactions = (
        load_alert_transactions()
    )

    alert_events = (
        build_alert_events(
            alert_transactions
        )
    )

    candidates = (
        load_ring_candidates()
    )

    # --------------------------------------------------------
    # COMPARE
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("COMPARING CANDIDATES WITH AML ALERTS")
    print("=" * 70)

    results = []

    for candidate in candidates:

        for _, alert in (
            alert_events.iterrows()
        ):

            results.append(
                analyze_pair(
                    candidate,
                    alert
                )
            )

    pair_df = pd.DataFrame(
        results
    )

    # --------------------------------------------------------
    # BEST MATCH PER CANDIDATE
    # --------------------------------------------------------
    #
    # One candidate may correspond to several alerts.
    # Select the strongest temporal/account match.
    #
    # Priority:
    #   1. common accounts
    #   2. temporal overlap
    #   3. earliest alert
    #
    # --------------------------------------------------------

    if not pair_df.empty:

        pair_df = pair_df.sort_values(
            by=[
                "common_accounts",
                "overlap_hours"
            ],
            ascending=False
        )

        best_df = (
            pair_df
            .drop_duplicates(
                subset=[
                    "candidate_ring_id"
                ],
                keep="first"
            )
            .copy()
        )

    else:

        best_df = pd.DataFrame()

    # --------------------------------------------------------
    # COUNTS
    # --------------------------------------------------------

    total_candidates = len(
        candidates
    )

    temporal_matches = 0

    account_matches = 0

    single_matches = 0

    no_matches = 0

    early_warnings = 0

    if not best_df.empty:

        temporal_matches = int(
            (
                best_df["match_status"]
                ==
                "TEMPORAL_GROUND_TRUTH_MATCH"
            ).sum()
        )

        account_matches = int(
            (
                best_df["match_status"]
                ==
                "ACCOUNT_MATCH_NO_TEMPORAL_OVERLAP"
            ).sum()
        )

        single_matches = int(
            (
                best_df["match_status"]
                ==
                "SINGLE_ACCOUNT_MATCH"
            ).sum()
        )

        no_matches = int(
            (
                best_df["match_status"]
                ==
                "NO_MATCH"
            ).sum()
        )

        early_warnings = int(
            best_df[
                "early_warning"
            ].fillna(False).sum()
        )

    # --------------------------------------------------------
    # PRINT
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("GROUND TRUTH RESULT")
    print("=" * 70)

    print(
        f"AML alert transactions: "
        f"{len(alert_transactions):,}"
    )

    print(
        f"AML alert events: "
        f"{len(alert_events):,}"
    )

    print(
        f"Ring candidates: "
        f"{total_candidates:,}"
    )

    print()

    print(
        f"Temporal ground-truth matches: "
        f"{temporal_matches:,}"
    )

    print(
        f"Account matches without temporal overlap: "
        f"{account_matches:,}"
    )

    print(
        f"Single-account matches: "
        f"{single_matches:,}"
    )

    print(
        f"No matches: "
        f"{no_matches:,}"
    )

    print(
        f"Potential early warnings: "
        f"{early_warnings:,}"
    )

    # --------------------------------------------------------
    # SAVE PAIR RESULTS
    # --------------------------------------------------------

    pair_df.to_csv(
        OUTPUT_CSV,
        index=False
    )

    # --------------------------------------------------------
    # SAVE BEST MATCH / LEAD TIME
    # --------------------------------------------------------

    if not best_df.empty:

        best_df.to_csv(
            LEAD_TIME_CSV,
            index=False
        )

    else:

        pd.DataFrame().to_csv(
            LEAD_TIME_CSV,
            index=False
        )

    # --------------------------------------------------------
    # LEAD TIME STATISTICS
    # --------------------------------------------------------

    lead_times = pd.Series(
        dtype=float
    )

    if not best_df.empty:

        lead_times = (
            best_df[
                "lead_time_hours"
            ]
            .dropna()
        )

        lead_times = lead_times[
            lead_times > 0
        ]

    lead_summary = {

        "n_positive_lead_time_candidates":
            int(len(lead_times)),

        "mean_lead_time_hours":
            (
                float(
                    lead_times.mean()
                )
                if len(lead_times) > 0
                else None
            ),

        "median_lead_time_hours":
            (
                float(
                    lead_times.median()
                )
                if len(lead_times) > 0
                else None
            ),

        "max_lead_time_hours":
            (
                float(
                    lead_times.max()
                )
                if len(lead_times) > 0
                else None
            ),

        "min_lead_time_hours":
            (
                float(
                    lead_times.min()
                )
                if len(lead_times) > 0
                else None
            )
    }

    # --------------------------------------------------------
    # SUMMARY JSON
    # --------------------------------------------------------

    summary = {

        "alert_transactions":
            int(len(alert_transactions)),

        "alert_events":
            int(len(alert_events)),

        "ring_candidates":
            int(total_candidates),

        "temporal_ground_truth_matches":
            int(temporal_matches),

        "account_matches_without_temporal_overlap":
            int(account_matches),

        "single_account_matches":
            int(single_matches),

        "no_matches":
            int(no_matches),

        "potential_early_warnings":
            int(early_warnings),

        "lead_time_statistics":
            lead_summary,

        "ground_truth_definition":
            (
                "An AML observable event is defined "
                "by the earliest transaction timestamp "
                "among transactions belonging to an "
                "AMLSim alert_id. Alert participants "
                "are the union of orig_acct and bene_acct. "
                "A candidate is considered a temporal "
                "ground-truth match when it shares at "
                "least two participant accounts with an "
                "AML alert and its candidate time span "
                "overlaps the alert transaction interval."
            )
    }

    with open(
        OUTPUT_JSON,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            summary,
            f,
            indent=2
        )

    # --------------------------------------------------------
    # TOP MATCHES
    # --------------------------------------------------------

    if not best_df.empty:

        print()
        print("=" * 70)
        print("TOP TEMPORAL GROUND-TRUTH MATCHES")
        print("=" * 70)

        display_columns = [
            "candidate_ring_id",
            "alert_id",
            "alert_type",
            "common_accounts",
            "account_overlap_ratio",
            "overlap_hours",
            "lead_time_hours",
            "early_warning",
            "match_status",
            "patterns"
        ]

        print(
            best_df[
                display_columns
            ]
            .head(20)
            .to_string(
                index=False
            )
        )

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("FILES CREATED")
    print("=" * 70)

    print(
        OUTPUT_CSV
    )

    print(
        LEAD_TIME_CSV
    )

    print(
        OUTPUT_JSON
    )

    print()
    print("DONE.")


if __name__ == "__main__":
    main()