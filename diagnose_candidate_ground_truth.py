from pathlib import Path
import json
import pandas as pd


ROOT = Path(__file__).resolve().parent

CANDIDATES = ROOT / "results" / "ring_candidates.json"
ALERT_ACCOUNTS = ROOT / "data" / "raw" / "amlsim" / "alert_accounts.csv"


def main():

    print("=" * 70)
    print("RING CANDIDATE GROUND-TRUTH DIAGNOSTIC")
    print("=" * 70)

    # ---------------------------------------------------------
    # Load candidates
    # ---------------------------------------------------------

    if not CANDIDATES.exists():
        raise FileNotFoundError(
            f"Missing: {CANDIDATES}"
        )

    with open(CANDIDATES, "r", encoding="utf-8") as f:
        candidates = json.load(f)

    print(f"\nRing candidates: {len(candidates)}")

    # ---------------------------------------------------------
    # Load AML ground truth
    # ---------------------------------------------------------

    if not ALERT_ACCOUNTS.exists():
        raise FileNotFoundError(
            f"Missing: {ALERT_ACCOUNTS}"
        )

    aml_df = pd.read_csv(
        ALERT_ACCOUNTS,
        dtype=str
    )

    print(
        f"Ground-truth alert rows: {len(aml_df)}"
    )

    # ---------------------------------------------------------
    # Find account column
    # ---------------------------------------------------------

    possible_columns = [
    "acct_id",
    "account_id",
    "account",
    "accountId",
    "node_id",
    "node",
    ]

    account_column = None

    for col in possible_columns:

        if col in aml_df.columns:
            account_column = col
            break

    if account_column is None:

        print("\nAvailable columns:")
        print(list(aml_df.columns))

        raise ValueError(
            "Could not identify AML account column."
        )

    aml_accounts = set(
        aml_df[account_column]
        .dropna()
        .astype(str)
        .str.strip()
    )

    print(
        f"Unique known AML accounts: {len(aml_accounts)}"
    )

    # ---------------------------------------------------------
    # Evaluate candidates
    # ---------------------------------------------------------

    results = []

    for candidate in candidates:

        candidate_id = candidate.get(
            "candidate_ring_id",
            "UNKNOWN"
        )

        accounts = {
            str(a).strip()
            for a in candidate.get(
                "accounts",
                []
            )
        }

        overlap = accounts & aml_accounts

        overlap_count = len(overlap)

        overlap_ratio = (
            overlap_count / len(accounts)
            if accounts
            else 0.0
        )

        results.append(
            {
                "candidate_ring_id": candidate_id,
                "n_accounts": len(accounts),
                "n_aml_accounts": overlap_count,
                "aml_overlap_ratio": round(
                    overlap_ratio,
                    4
                ),
                "patterns": ",".join(
                    candidate.get(
                        "patterns",
                        []
                    )
                ),
                "formation_stage": candidate.get(
                    "formation_stage"
                ),
                "source_trajectory_id": candidate.get(
                    "source_trajectory_id"
                ),
            }
        )

    result_df = pd.DataFrame(results)

    # ---------------------------------------------------------
    # Summary
    # ---------------------------------------------------------

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print(
        f"Total candidates: {len(result_df)}"
    )

    print(
        "Candidates with >=1 AML account:",
        int(
            (
                result_df["n_aml_accounts"] >= 1
            ).sum()
        )
    )

    print(
        "Candidates with >=2 AML accounts:",
        int(
            (
                result_df["n_aml_accounts"] >= 2
            ).sum()
        )
    )

    print(
        "Candidates with >=3 AML accounts:",
        int(
            (
                result_df["n_aml_accounts"] >= 3
            ).sum()
        )
    )

    print(
        "Candidates with >=5 AML accounts:",
        int(
            (
                result_df["n_aml_accounts"] >= 5
            ).sum()
        )
    )

    print(
        "Candidates with >=10 AML accounts:",
        int(
            (
                result_df["n_aml_accounts"] >= 10
            ).sum()
        )
    )

    # ---------------------------------------------------------
    # Top candidates by AML overlap
    # ---------------------------------------------------------

    print("\n" + "=" * 70)
    print("TOP 20 CANDIDATES BY AML ACCOUNT OVERLAP")
    print("=" * 70)

    top = result_df.sort_values(
        [
            "n_aml_accounts",
            "aml_overlap_ratio",
            "n_accounts",
        ],
        ascending=[
            False,
            False,
            False,
        ],
    ).head(20)

    print(
        top.to_string(index=False)
    )

    # ---------------------------------------------------------
    # Candidates with no AML overlap
    # ---------------------------------------------------------

    no_overlap = result_df[
        result_df["n_aml_accounts"] == 0
    ]

    print("\n" + "=" * 70)
    print("NO-OVERLAP CANDIDATES")
    print("=" * 70)

    print(
        f"Candidates with zero AML overlap: "
        f"{len(no_overlap)}"
    )

    # ---------------------------------------------------------
    # Account-size distribution
    # ---------------------------------------------------------

    print("\n" + "=" * 70)
    print("ACCOUNT SIZE DISTRIBUTION")
    print("=" * 70)

    print(
        result_df["n_accounts"]
        .describe()
        .to_string()
    )

    print(
        "\nCandidates >= 50 accounts:",
        int(
            (
                result_df["n_accounts"] >= 50
            ).sum()
        )
    )

    print(
        "Candidates >= 75 accounts:",
        int(
            (
                result_df["n_accounts"] >= 75
            ).sum()
        )
    )

    print(
        "Candidates exactly 100 accounts:",
        int(
            (
                result_df["n_accounts"] == 100
            ).sum()
        )
    )

    # ---------------------------------------------------------
    # Save diagnostic
    # ---------------------------------------------------------

    output = (
        ROOT
        / "results"
        / "candidate_ground_truth_diagnostic.csv"
    )

    result_df.to_csv(
        output,
        index=False
    )

    print(
        f"\nSaved: {output}"
    )

    print("\nDONE.")


if __name__ == "__main__":
    main()