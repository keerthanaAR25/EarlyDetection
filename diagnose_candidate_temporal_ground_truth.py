#!/usr/bin/env python3

from pathlib import Path
import json
import pandas as pd


# ============================================================
# PROJECT PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent

RESULTS_DIR = ROOT / "results"

RING_CANDIDATES = RESULTS_DIR / "ring_candidates.json"

ALERT_ACCOUNTS = (
    ROOT
    / "data"
    / "raw"
    / "amlsim"
    / "alert_accounts.csv"
)

OUTPUT_CSV = (
    ROOT
    / "results"
    / "candidate_temporal_ground_truth.csv"
)

OUTPUT_JSON = (
    ROOT
    / "results"
    / "candidate_temporal_ground_truth_summary.json"
)


# ============================================================
# TIMESTAMP PARSER
# ============================================================

def parse_timestamp(value):
    """
    Convert timestamp to UTC-aware pandas Timestamp.

    Invalid / empty values become NaT.
    """

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
# LOAD RING CANDIDATES
# ============================================================

def load_ring_candidates():

    print("\nLoading ring candidates...")

    print("Path:")
    print(RING_CANDIDATES)

    if not RING_CANDIDATES.exists():

        raise FileNotFoundError(
            "\nring_candidates.json was not found.\n"
            "Expected location:\n"
            f"{RING_CANDIDATES}\n\n"
            "First run:\n"
            "python scripts/build_ring_candidates.py"
        )

    with open(
        RING_CANDIDATES,
        "r",
        encoding="utf-8"
    ) as file:

        candidates = json.load(file)

    if not isinstance(candidates, list):

        raise ValueError(
            "ring_candidates.json must contain a JSON list."
        )

    print(
        f"Ring candidates loaded: {len(candidates)}"
    )

    return candidates


# ============================================================
# LOAD AML ALERT ACCOUNTS
# ============================================================

def load_alert_accounts():

    print("\nLoading AMLSim alert accounts...")

    print("Path:")
    print(ALERT_ACCOUNTS)

    if not ALERT_ACCOUNTS.exists():

        raise FileNotFoundError(
            "\nalert_accounts.csv was not found.\n"
            "Expected location:\n"
            f"{ALERT_ACCOUNTS}"
        )

    alerts = pd.read_csv(
        ALERT_ACCOUNTS,
        dtype=str
    )

    print(
        f"Alert rows: {len(alerts)}"
    )

    print(
        "Columns:",
        list(alerts.columns)
    )

    # --------------------------------------------------------
    # CHECK REQUIRED COLUMN
    # --------------------------------------------------------

    if "acct_id" not in alerts.columns:

        raise ValueError(
            "Column 'acct_id' was not found "
            "in alert_accounts.csv."
        )

    # --------------------------------------------------------
    # NORMALIZE ACCOUNT ID
    # --------------------------------------------------------

    alerts["acct_id"] = (
        alerts["acct_id"]
        .astype("string")
        .str.strip()
    )

    # --------------------------------------------------------
    # TIMESTAMP PARSING
    # --------------------------------------------------------

    if "start" in alerts.columns:

        alerts["start"] = alerts["start"].apply(
            parse_timestamp
        )

    else:

        alerts["start"] = pd.NaT

    if "end" in alerts.columns:

        alerts["end"] = alerts["end"].apply(
            parse_timestamp
        )

    else:

        alerts["end"] = pd.NaT

    # --------------------------------------------------------
    # DIAGNOSTICS
    # --------------------------------------------------------

    valid_start = alerts["start"].notna()

    valid_end = alerts["end"].notna()

    valid_interval = (
        valid_start
        &
        valid_end
    )

    print()
    print("Timestamp diagnostics")
    print("--------------------")

    print(
        "Valid start:",
        int(valid_start.sum())
    )

    print(
        "Valid end:",
        int(valid_end.sum())
    )

    print(
        "Valid start + end:",
        int(valid_interval.sum())
    )

    print(
        "Unique AML accounts:",
        alerts["acct_id"].nunique()
    )

    print(
        "Unique AML accounts with valid intervals:",
        alerts.loc[
            valid_interval,
            "acct_id"
        ].nunique()
    )

    return alerts


# ============================================================
# CREATE AML ACCOUNT INDEX
# ============================================================

def build_alert_index(alerts):

    index = {}

    for _, row in alerts.iterrows():

        account = row["acct_id"]

        if pd.isna(account):
            continue

        account = str(account).strip()

        if not account:
            continue

        if account not in index:

            index[account] = []

        index[account].append(
            {
                "alert_id": row.get(
                    "alert_id",
                    ""
                ),

                "alert_type": row.get(
                    "alert_type",
                    ""
                ),

                "start": row["start"],

                "end": row["end"]
            }
        )

    return index


# ============================================================
# GET CANDIDATE ACCOUNTS
# ============================================================

def candidate_accounts(candidate):

    accounts = candidate.get(
        "accounts",
        []
    )

    if accounts is None:
        return set()

    result = set()

    for account in accounts:

        if account is None:
            continue

        account = str(account).strip()

        if account:
            result.add(account)

    return result


# ============================================================
# GET CANDIDATE TIME RANGE
# ============================================================

def candidate_times(candidate):

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
# TEMPORAL OVERLAP
# ============================================================

def calculate_overlap(
    candidate_start,
    candidate_end,
    alert_start,
    alert_end
):

    if pd.isna(candidate_start):
        return 0.0

    if pd.isna(candidate_end):
        return 0.0

    if pd.isna(alert_start):
        return 0.0

    if pd.isna(alert_end):
        return 0.0

    # Both are UTC-aware because parse_timestamp()
    # always uses utc=True.

    overlap_start = max(
        candidate_start,
        alert_start
    )

    overlap_end = min(
        candidate_end,
        alert_end
    )

    if overlap_end <= overlap_start:

        return 0.0

    return (
        overlap_end - overlap_start
    ).total_seconds()


# ============================================================
# ANALYZE ONE CANDIDATE
# ============================================================

def analyze_candidate(
    candidate,
    alert_index
):

    ring_id = candidate.get(
        "candidate_ring_id",
        "UNKNOWN"
    )

    accounts = candidate_accounts(
        candidate
    )

    candidate_start, candidate_end = (
        candidate_times(candidate)
    )

    # --------------------------------------------------------
    # ACCOUNT OVERLAP
    # --------------------------------------------------------

    matched_accounts = set()

    temporal_accounts = set()

    alert_ids = set()

    temporal_alert_ids = set()

    max_overlap_seconds = 0.0

    for account in accounts:

        if account not in alert_index:
            continue

        # Account exists in AML ground truth.
        matched_accounts.add(account)

        for alert in alert_index[account]:

            alert_id = str(
                alert["alert_id"]
            )

            if alert_id:
                alert_ids.add(
                    alert_id
                )

            overlap = calculate_overlap(
                candidate_start,
                candidate_end,
                alert["start"],
                alert["end"]
            )

            if overlap > max_overlap_seconds:

                max_overlap_seconds = overlap

            if overlap > 0:

                temporal_accounts.add(
                    account
                )

                if alert_id:

                    temporal_alert_ids.add(
                        alert_id
                    )

    # --------------------------------------------------------
    # RATIOS
    # --------------------------------------------------------

    account_ratio = (
        len(matched_accounts)
        /
        len(accounts)
        if len(accounts) > 0
        else 0.0
    )

    temporal_ratio = (
        len(temporal_accounts)
        /
        len(accounts)
        if len(accounts) > 0
        else 0.0
    )

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    if len(temporal_accounts) >= 3:

        status = "STRONG_TEMPORAL_MATCH"

    elif len(temporal_accounts) >= 2:

        status = "TEMPORAL_MATCH"

    elif len(matched_accounts) >= 2:

        status = (
            "ACCOUNT_MATCH_NO_TEMPORAL_OVERLAP"
        )

    elif len(matched_accounts) == 1:

        status = "SINGLE_ACCOUNT_MATCH"

    else:

        status = "NO_MATCH"

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

    else:

        patterns = str(patterns)

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    return {

        "candidate_ring_id":
            ring_id,

        "n_accounts":
            len(accounts),

        "n_transactions":
            len(
                candidate.get(
                    "transaction_ids",
                    []
                )
            ),

        "patterns":
            patterns,

        "formation_stage":
            candidate.get(
                "formation_stage",
                ""
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

        "n_account_overlap":
            len(matched_accounts),

        "account_overlap_ratio":
            round(
                account_ratio,
                4
            ),

        "n_temporal_overlap_accounts":
            len(temporal_accounts),

        "temporal_overlap_ratio":
            round(
                temporal_ratio,
                4
            ),

        "n_alert_ids":
            len(alert_ids),

        "n_temporal_alert_ids":
            len(temporal_alert_ids),

        "max_temporal_overlap_hours":
            round(
                max_overlap_seconds / 3600,
                4
            ),

        "match_status":
            status,

        "matched_accounts":
            ",".join(
                sorted(matched_accounts)
            ),

        "temporal_matched_accounts":
            ",".join(
                sorted(temporal_accounts)
            ),

        "alert_ids":
            ",".join(
                sorted(alert_ids)
            ),

        "temporal_alert_ids":
            ",".join(
                sorted(temporal_alert_ids)
            )
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print(
        "TEMPORAL RING CANDIDATE "
        "GROUND-TRUTH DIAGNOSTIC"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # LOAD
    # --------------------------------------------------------

    candidates = load_ring_candidates()

    alerts = load_alert_accounts()

    alert_index = build_alert_index(
        alerts
    )

    # --------------------------------------------------------
    # ANALYZE
    # --------------------------------------------------------

    print()
    print("Analyzing candidates...")

    results = []

    for candidate in candidates:

        results.append(
            analyze_candidate(
                candidate,
                alert_index
            )
        )

    df = pd.DataFrame(
        results
    )

    # --------------------------------------------------------
    # SUMMARY COUNTS
    # --------------------------------------------------------

    total = len(df)

    any_account_overlap = int(
        (
            df["n_account_overlap"] >= 1
        ).sum()
    )

    two_account_overlap = int(
        (
            df["n_account_overlap"] >= 2
        ).sum()
    )

    any_temporal_overlap = int(
        (
            df[
                "n_temporal_overlap_accounts"
            ] >= 1
        ).sum()
    )

    two_temporal_overlap = int(
        (
            df[
                "n_temporal_overlap_accounts"
            ] >= 2
        ).sum()
    )

    three_temporal_overlap = int(
        (
            df[
                "n_temporal_overlap_accounts"
            ] >= 3
        ).sum()
    )

    zero_overlap = int(
        (
            df["n_account_overlap"] == 0
        ).sum()
    )

    # --------------------------------------------------------
    # PRINT SUMMARY
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("RESULT")
    print("=" * 70)

    print(
        f"Ring candidates: {total}"
    )

    print(
        f"AML alert rows: {len(alerts)}"
    )

    print(
        "Unique AML accounts:",
        alerts["acct_id"].nunique()
    )

    valid_intervals = int(
        (
            alerts["start"].notna()
            &
            alerts["end"].notna()
        ).sum()
    )

    print(
        f"Valid AML alert intervals: "
        f"{valid_intervals}"
    )

    print()

    print(
        f"Candidates with >=1 AML account: "
        f"{any_account_overlap}"
    )

    print(
        f"Candidates with >=2 AML accounts: "
        f"{two_account_overlap}"
    )

    print(
        f"Candidates with >=1 temporal AML account: "
        f"{any_temporal_overlap}"
    )

    print(
        f"Candidates with >=2 temporal AML accounts: "
        f"{two_temporal_overlap}"
    )

    print(
        f"Candidates with >=3 temporal AML accounts: "
        f"{three_temporal_overlap}"
    )

    print(
        f"Candidates with zero AML overlap: "
        f"{zero_overlap}"
    )

    # --------------------------------------------------------
    # STATUS DISTRIBUTION
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("MATCH STATUS DISTRIBUTION")
    print("=" * 70)

    status_counts = (
        df["match_status"]
        .value_counts()
    )

    for status, count in status_counts.items():

        print(
            f"{status}: {count}"
        )

    # --------------------------------------------------------
    # TOP MATCHES
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("TOP CANDIDATES")
    print("=" * 70)

    top = df.sort_values(
        by=[
            "n_temporal_overlap_accounts",
            "n_account_overlap"
        ],
        ascending=False
    )

    print(
        top[
            [
                "candidate_ring_id",
                "n_accounts",
                "n_account_overlap",
                "n_temporal_overlap_accounts",
                "account_overlap_ratio",
                "temporal_overlap_ratio",
                "max_temporal_overlap_hours",
                "match_status",
                "patterns"
            ]
        ]
        .head(15)
        .to_string(
            index=False
        )
    )

    # --------------------------------------------------------
    # SAVE CSV
    # --------------------------------------------------------

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    df.to_csv(
        OUTPUT_CSV,
        index=False
    )

    # --------------------------------------------------------
    # SAVE SUMMARY JSON
    # --------------------------------------------------------

    summary = {

        "ring_candidates":
            total,

        "aml_alert_rows":
            int(len(alerts)),

        "unique_aml_accounts":
            int(
                alerts[
                    "acct_id"
                ].nunique()
            ),

        "valid_aml_alert_intervals":
            valid_intervals,

        "candidates_with_any_account_overlap":
            any_account_overlap,

        "candidates_with_at_least_two_account_overlap":
            two_account_overlap,

        "candidates_with_any_temporal_overlap":
            any_temporal_overlap,

        "candidates_with_at_least_two_temporal_overlap":
            two_temporal_overlap,

        "candidates_with_at_least_three_temporal_overlap":
            three_temporal_overlap,

        "candidates_with_zero_account_overlap":
            zero_overlap,

        "status_distribution":
            {
                str(k): int(v)
                for k, v
                in status_counts.items()
            }
    }

    with open(
        OUTPUT_JSON,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            summary,
            file,
            indent=2
        )

    # --------------------------------------------------------
    # FINISHED
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("FILES CREATED")
    print("=" * 70)

    print(
        OUTPUT_CSV
    )

    print(
        OUTPUT_JSON
    )

    print()
    print("DONE.")


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()