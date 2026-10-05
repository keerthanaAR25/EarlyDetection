"""
Data Quality Engine.

Runs comprehensive validation over a canonical-schema transaction
DataFrame (src/data/schema.py) and produces a structured report:
    - dataset-level statistics (counts, ranges, distributions)
    - row-level issue counts, by category
    - a sample of offending rows per category (capped, for inspection)

This module only DETECTS and REPORTS issues — it does not fix or drop
anything. Fixing/dropping happens in src/preprocessing/cleaning.py
(Phase 4) and every transformation it makes must be logged, per the
project's non-negotiable rule against silently dropping rows.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_MAX_SAMPLE_ROWS = 20


@dataclass
class IssueCategory:
    name: str
    description: str
    count: int
    pct_of_rows: float
    sample_transaction_ids: list[str] = field(default_factory=list)


class DataQualityEngine:
    def __init__(self, df: pd.DataFrame, dataset_label: str = "unknown"):
        self.df = df
        self.dataset_label = dataset_label
        self.n_rows = len(df)

    # ------------------------------------------------------------ helpers
    def _issue(self, name: str, description: str, mask: pd.Series) -> IssueCategory:
        count = int(mask.sum())
        pct = round(100.0 * count / self.n_rows, 4) if self.n_rows else 0.0
        sample_ids = []
        if count and "transaction_id" in self.df.columns:
            sample_ids = self.df.loc[mask, "transaction_id"].astype(str).head(_MAX_SAMPLE_ROWS).tolist()
        return IssueCategory(name, description, count, pct, sample_ids)

    # ------------------------------------------------------------ checks
    def _check_missing_values(self) -> dict[str, IssueCategory]:
        issues = {}
        for col in self.df.columns:
            mask = self.df[col].isna()
            if col in ("scenario_id", "ring_id"):
                # empty string is the documented "no value" sentinel for these,
                # not a data-quality problem — only true nulls count.
                pass
            issues[f"missing_{col}"] = self._issue(
                f"missing_{col}", f"Null/NaN values in '{col}'", mask
            )
        return issues

    def _check_duplicates(self) -> dict[str, IssueCategory]:
        dup_id_mask = self.df.duplicated(subset=["transaction_id"], keep=False)
        compare_cols = [c for c in ["sender", "receiver", "amount", "timestamp"] if c in self.df.columns]
        dup_full_mask = self.df.duplicated(subset=compare_cols, keep=False) if compare_cols else pd.Series(False, index=self.df.index)
        return {
            "duplicate_transaction_ids": self._issue(
                "duplicate_transaction_ids", "transaction_id appears more than once", dup_id_mask
            ),
            "duplicate_transaction_content": self._issue(
                "duplicate_transaction_content",
                "Identical sender/receiver/amount/timestamp appears more than once",
                dup_full_mask,
            ),
        }

    def _check_amounts(self) -> dict[str, IssueCategory]:
        amt = pd.to_numeric(self.df.get("amount"), errors="coerce")
        return {
            "invalid_amount_nan": self._issue("invalid_amount_nan", "amount is missing or non-numeric", amt.isna()),
            "negative_amount": self._issue("negative_amount", "amount < 0", amt < 0),
            "zero_amount": self._issue("zero_amount", "amount == 0", amt == 0),
        }

    def _check_accounts(self) -> dict[str, IssueCategory]:
        sender = self.df.get("sender")
        receiver = self.df.get("receiver")
        malformed_sender = sender.isna() | (sender.astype(str).str.strip() == "")
        malformed_receiver = receiver.isna() | (receiver.astype(str).str.strip() == "")
        self_tx = (sender.astype(str) == receiver.astype(str)) & ~malformed_sender & ~malformed_receiver
        return {
            "missing_sender": self._issue("missing_sender", "sender is null/empty", malformed_sender),
            "missing_receiver": self._issue("missing_receiver", "receiver is null/empty", malformed_receiver),
            "self_transaction": self._issue("self_transaction", "sender == receiver", self_tx),
        }

    def _check_timestamps(self) -> dict[str, IssueCategory]:
        ts = pd.to_datetime(self.df.get("timestamp"), errors="coerce", utc=True)
        invalid_ts = ts.isna()

        now = pd.Timestamp.now(tz="UTC")
        future_ts = ts.notna() & (ts > now + pd.Timedelta(days=1))  # 1-day buffer for clock skew

        # Chronological-order check: how many rows are out of order relative to
        # file order (purely informational at this stage — sorting happens in
        # preprocessing, this only flags that it's needed).
        valid_ts = ts.dropna().reset_index(drop=True)
        out_of_order_count = int((valid_ts.diff().dt.total_seconds() < 0).sum()) if len(valid_ts) > 1 else 0

        issues = {
            "invalid_timestamp": self._issue("invalid_timestamp", "timestamp is missing or unparseable", invalid_ts),
            "future_timestamp": self._issue("future_timestamp", "timestamp is in the future", future_ts),
        }
        issues["_out_of_order_count"] = out_of_order_count  # not an IssueCategory; surfaced separately in report
        return issues

    def _check_label_scenario_consistency(self) -> dict[str, IssueCategory]:
        label = pd.to_numeric(self.df.get("label"), errors="coerce")
        invalid_label = ~label.isin([-1, 0, 1])

        ring_id = self.df.get("ring_id", pd.Series("", index=self.df.index)).fillna("").astype(str)
        scenario_id = self.df.get("scenario_id", pd.Series("", index=self.df.index)).fillna("").astype(str)
        has_ring_no_scenario = (ring_id != "") & (scenario_id == "")
        labeled_no_ring = (label == 1) & (ring_id == "")

        return {
            "invalid_label_value": self._issue("invalid_label_value", "label not in {-1,0,1}", invalid_label),
            "ring_without_scenario": self._issue(
                "ring_without_scenario", "ring_id set but scenario_id empty", has_ring_no_scenario
            ),
            "positive_label_without_ring": self._issue(
                "positive_label_without_ring", "label==1 but no ring_id assigned", labeled_no_ring
            ),
        }

    # ------------------------------------------------------------ summary
    def _summary_stats(self) -> dict[str, Any]:
        amt = pd.to_numeric(self.df.get("amount"), errors="coerce")
        ts = pd.to_datetime(self.df.get("timestamp"), errors="coerce", utc=True)
        accounts = pd.concat([self.df.get("sender"), self.df.get("receiver")]).dropna().astype(str)

        label = pd.to_numeric(self.df.get("label"), errors="coerce")
        class_dist = label.value_counts(dropna=False).to_dict()
        class_dist = {str(k): int(v) for k, v in class_dist.items()}

        scenario_dist = {}
        if "scenario_id" in self.df.columns:
            sc = self.df["scenario_id"].fillna("").astype(str)
            sc = sc[sc != ""]
            scenario_dist = {str(k): int(v) for k, v in sc.value_counts().head(50).to_dict().items()}

        return {
            "row_count": int(self.n_rows),
            "column_count": int(self.df.shape[1]),
            "unique_transactions": int(self.df["transaction_id"].nunique()) if "transaction_id" in self.df else None,
            "unique_accounts": int(accounts.nunique()),
            "timestamp_range": {
                "min": ts.min().isoformat() if ts.notna().any() else None,
                "max": ts.max().isoformat() if ts.notna().any() else None,
            },
            "amount_statistics": {
                "count": int(amt.notna().sum()),
                "mean": float(amt.mean()) if amt.notna().any() else None,
                "median": float(amt.median()) if amt.notna().any() else None,
                "std": float(amt.std()) if amt.notna().any() else None,
                "min": float(amt.min()) if amt.notna().any() else None,
                "max": float(amt.max()) if amt.notna().any() else None,
            },
            "class_distribution": class_dist,
            "scenario_distribution_top50": scenario_dist,
        }

    # ------------------------------------------------------------ run
    def run(self) -> dict[str, Any]:
        issue_groups = {}
        issue_groups.update(self._check_missing_values())
        issue_groups.update(self._check_duplicates())
        issue_groups.update(self._check_amounts())
        issue_groups.update(self._check_accounts())

        ts_issues = self._check_timestamps()
        out_of_order_count = ts_issues.pop("_out_of_order_count")
        issue_groups.update(ts_issues)

        issue_groups.update(self._check_label_scenario_consistency())

        report = {
            "dataset_label": self.dataset_label,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": self._summary_stats(),
            "timestamp_out_of_order_rows": out_of_order_count,
            "issues": {
                name: {
                    "description": cat.description,
                    "count": cat.count,
                    "pct_of_rows": cat.pct_of_rows,
                    "sample_transaction_ids": cat.sample_transaction_ids,
                }
                for name, cat in issue_groups.items()
            },
            "total_issue_categories_with_findings": sum(1 for c in issue_groups.values() if c.count > 0),
        }
        return report

    # ------------------------------------------------------------ output
    def write_json(self, path: str | Path, report: dict | None = None) -> dict:
        report = report or self.run()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        return report

    def write_html(self, path: str | Path, report: dict | None = None) -> dict:
        report = report or self.run()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        s = report["summary"]
        rows_html = ""
        for name, info in report["issues"].items():
            flag = "⚠️" if info["count"] > 0 else "✅"
            rows_html += (
                f"<tr><td>{flag}</td><td>{name}</td><td>{info['description']}</td>"
                f"<td>{info['count']}</td><td>{info['pct_of_rows']}%</td></tr>\n"
            )

        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Data Quality Report — {report['dataset_label']}</title>
<style>
body {{ font-family: -apple-system, Segoe UI, Arial, sans-serif; margin: 2rem; color: #1a1a2e; background: #f7f8fb; }}
h1 {{ margin-bottom: 0.2rem; }}
.meta {{ color: #666; margin-bottom: 1.5rem; }}
.cards {{ display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 2rem; }}
.card {{ background: white; border-radius: 8px; padding: 1rem 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08); min-width: 160px; }}
.card .label {{ font-size: 0.75rem; color: #888; text-transform: uppercase; letter-spacing: 0.03em; }}
.card .value {{ font-size: 1.5rem; font-weight: 600; margin-top: 0.25rem; }}
table {{ border-collapse: collapse; width: 100%; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
th, td {{ padding: 0.5rem 0.9rem; text-align: left; border-bottom: 1px solid #eee; font-size: 0.9rem; }}
th {{ background: #eef1fa; }}
</style></head>
<body>
<h1>Data Quality Report</h1>
<div class="meta">Dataset: <b>{report['dataset_label']}</b> &middot; Generated: {report['generated_at']}</div>
<div class="cards">
  <div class="card"><div class="label">Rows</div><div class="value">{s['row_count']:,}</div></div>
  <div class="card"><div class="label">Unique Accounts</div><div class="value">{s['unique_accounts']:,}</div></div>
  <div class="card"><div class="label">Timestamp Range</div><div class="value" style="font-size:0.95rem">{s['timestamp_range']['min']} &rarr; {s['timestamp_range']['max']}</div></div>
  <div class="card"><div class="label">Issue Categories Flagged</div><div class="value">{report['total_issue_categories_with_findings']} / {len(report['issues'])}</div></div>
  <div class="card"><div class="label">Out-of-order Rows</div><div class="value">{report['timestamp_out_of_order_rows']:,}</div></div>
</div>
<h2>Issue Breakdown</h2>
<table>
<tr><th></th><th>Category</th><th>Description</th><th>Count</th><th>% of rows</th></tr>
{rows_html}
</table>
</body></html>"""
        with open(path, "w") as f:
            f.write(html)
        return report
