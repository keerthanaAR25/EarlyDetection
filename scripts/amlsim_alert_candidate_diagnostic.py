import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CAND_PATH = ROOT / "results" / "ring_candidates.json"
ALERT_TX_PATH = ROOT / "data" / "raw" / "amlsim" / "alert_transactions.csv"
OUT_PATH = ROOT / "results" / "amlsim_alert_candidate_diagnostic.csv"

candidates = json.loads(CAND_PATH.read_text(encoding="utf-8"))
alerts = pd.read_csv(ALERT_TX_PATH, dtype=str)

alerts["orig_acct"] = alerts["orig_acct"].astype(str).str.strip()
alerts["bene_acct"] = alerts["bene_acct"].astype(str).str.strip()
alerts["tran_id"] = alerts["tran_id"].astype(str).str.strip()
alerts["tran_timestamp"] = pd.to_datetime(alerts["tran_timestamp"], errors="coerce", utc=True)

def clean_id(x):
    if x is None:
        return None
    s = str(x).strip()
    if s.endswith(".0"):
        try:
            s = str(int(float(s)))
        except Exception:
            pass
    return s

def candidate_accounts(c):
    return {clean_id(x) for x in c.get("accounts", []) if clean_id(x)}

def candidate_txids(c):
    return {clean_id(x) for x in c.get("transaction_ids", []) if clean_id(x)}

def candidate_span(c):
    span = c.get("time_span") or []
    if len(span) >= 2:
        a = pd.to_datetime(span[0], errors="coerce", utc=True)
        b = pd.to_datetime(span[1], errors="coerce", utc=True)
        return a, b
    return pd.NaT, pd.NaT

# Build one ground-truth alert record per AMLSim alert.
gt = []
for alert_id, g in alerts.groupby("alert_id", sort=True):
    participants = set(g["orig_acct"].dropna()) | set(g["bene_acct"].dropna())
    participants.discard("")
    first_ts = g["tran_timestamp"].min()
    last_ts = g["tran_timestamp"].max()
    txids = set(g["tran_id"].dropna())
    gt.append({
        "alert_id": str(alert_id),
        "alert_type": str(g["alert_type"].iloc[0]),
        "gt_accounts": participants,
        "gt_txids": txids,
        "gt_start": first_ts,
        "gt_end": last_ts,
        "gt_n_accounts": len(participants),
        "gt_n_transactions": len(txids),
    })

rows = []

for item in gt:
    best = None

    for c in candidates:
        cid = c.get("candidate_ring_id", c.get("candidate_id", "UNKNOWN"))
        ca = candidate_accounts(c)
        ctx = candidate_txids(c)
        cs, ce = candidate_span(c)

        shared = item["gt_accounts"] & ca
        n_shared = len(shared)

        if item["gt_accounts"]:
            account_recall = n_shared / len(item["gt_accounts"])
        else:
            account_recall = 0.0

        candidate_precision = n_shared / len(ca) if ca else 0.0
        union = item["gt_accounts"] | ca
        jaccard = n_shared / len(union) if union else 0.0

        exact_tx = item["gt_txids"] & ctx

        overlap = False
        overlap_days = 0.0
        gap_days = None

        if pd.notna(cs) and pd.notna(ce) and pd.notna(item["gt_start"]) and pd.notna(item["gt_end"]):
            if cs <= item["gt_end"] and item["gt_start"] <= ce:
                overlap = True
                start = max(cs, item["gt_start"])
                end = min(ce, item["gt_end"])
                overlap_days = max(0.0, (end - start).total_seconds() / 86400.0)
                gap_days = 0.0
            elif ce < item["gt_start"]:
                gap_days = max(0.0, (item["gt_start"] - ce).total_seconds() / 86400.0)
            elif item["gt_end"] < cs:
                gap_days = max(0.0, (cs - item["gt_end"]).total_seconds() / 86400.0)

        strict = n_shared >= 2 and overlap
        moderate = n_shared >= 2 and (not overlap) and gap_days is not None and gap_days <= 10.0

        score = (
            n_shared,
            account_recall,
            len(exact_tx),
            1 if overlap else 0,
            -999999 if gap_days is None else -gap_days,
            jaccard,
        )

        rec = {
            "alert_id": item["alert_id"],
            "alert_type": item["alert_type"],
            "gt_n_accounts": item["gt_n_accounts"],
            "gt_n_transactions": item["gt_n_transactions"],
            "candidate_id": cid,
            "candidate_n_accounts": len(ca),
            "n_shared_accounts": n_shared,
            "account_recall": round(account_recall, 4),
            "candidate_precision": round(candidate_precision, 4),
            "jaccard": round(jaccard, 4),
            "exact_shared_transactions": len(exact_tx),
            "gt_start": item["gt_start"],
            "gt_end": item["gt_end"],
            "candidate_start": cs,
            "candidate_end": ce,
            "temporal_overlap": overlap,
            "temporal_overlap_days": round(overlap_days, 2),
            "temporal_gap_days": None if gap_days is None else round(gap_days, 2),
            "strict_match": strict,
            "moderate_match": moderate,
            "candidate_patterns": ",".join(c.get("patterns", [])),
            "formation_stage": c.get("formation_stage"),
            "risk_score": c.get("risk_score"),
        }

        if best is None or score > best[0]:
            best = (score, rec)

    if best:
        rows.append(best[1])

df = pd.DataFrame(rows)
df.to_csv(OUT_PATH, index=False)

print("\n=== AMLSim ALERT → CANDIDATE DIAGNOSTIC ===")
print(f"Alerts: {len(df)}")
print(f"Candidates: {len(candidates)}")
print(f"Alerts with >=1 shared account: {(df.n_shared_accounts >= 1).sum()}")
print(f"Alerts with >=2 shared accounts: {(df.n_shared_accounts >= 2).sum()}")
print(f"Alerts with exact transaction overlap: {(df.exact_shared_transactions >= 1).sum()}")
print(f"Strict matches (>=2 accounts + temporal overlap): {df.strict_match.sum()}")
print(f"Moderate matches (>=2 accounts + gap <=10d): {df.moderate_match.sum()}")
print(f"Alerts with >=2 accounts but NO temporal overlap: {((df.n_shared_accounts >= 2) & (~df.temporal_overlap)).sum()}")
print("\nTop 15 alerts by shared accounts:")
cols = [
    "alert_id", "alert_type", "candidate_id", "n_shared_accounts",
    "gt_n_accounts", "account_recall", "candidate_precision",
    "exact_shared_transactions", "temporal_overlap",
    "temporal_gap_days", "candidate_patterns", "formation_stage", "risk_score"
]
print(df.sort_values(
    ["n_shared_accounts", "exact_shared_transactions", "account_recall"],
    ascending=[False, False, False]
)[cols].head(15).to_string(index=False))

print(f"\nSaved: {OUT_PATH}")
