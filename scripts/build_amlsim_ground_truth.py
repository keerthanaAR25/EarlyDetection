#!/usr/bin/env python3
"""
Build ground truth for the real AMLSim dataset, analogous to the demo
generator's ring_ground_truth.json: per alert_id, the accounts
involved and observable_time (max tran_timestamp among that alert's
transactions — per the dataset audit's finding that alert_accounts'
start/end fields are degenerate placeholders, not real timestamps).

Usage:
    python scripts/build_amlsim_ground_truth.py
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    alert_tx = pd.read_csv(ROOT / "data" / "raw" / "amlsim" / "alert_transactions.csv")
    alert_tx["tran_timestamp"] = pd.to_datetime(alert_tx["tran_timestamp"], utc=True)

    ground_truth = []
    for alert_id, group in alert_tx.groupby("alert_id"):
        accounts = sorted(set(group["orig_acct"].astype(str)) | set(group["bene_acct"].astype(str)))
        ground_truth.append({
            "ring_id": str(alert_id),
            "scenario_id": str(alert_id),
            "alert_type": group["alert_type"].iloc[0],
            "accounts": accounts,
            "start_date": group["tran_timestamp"].min().date().isoformat(),
            "observable_time": group["tran_timestamp"].max().date().isoformat(),
            "n_transactions": len(group),
        })

    out_path = ROOT / "data" / "raw" / "amlsim" / "ground_truth.json"
    with open(out_path, "w") as f:
        json.dump(ground_truth, f, indent=2)

    print(f"Built ground truth for {len(ground_truth)} alerts")
    for typ in set(g["alert_type"] for g in ground_truth):
        n = sum(1 for g in ground_truth if g["alert_type"] == typ)
        print(f"  {typ}: {n} alerts")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
