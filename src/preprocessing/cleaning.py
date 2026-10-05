"""
Data Preprocessing Pipeline.

Turns a raw canonical-schema DataFrame (as produced by src/data/*_adapter.py)
into a clean, chronologically-sorted dataset ready for graph construction.

Non-negotiable rule (from the project spec): do not blindly drop rows.
Every transformation this pipeline makes is recorded in a structured
log (step name, reason, rows_before, rows_affected, rows_after) and
written to data/processed/preprocessing_log.json alongside the output,
so every row that leaves the dataset is accounted for.

Design principle: rows are dropped only when the row is structurally
unusable for the rest of the system (no valid sender/receiver, no
parseable timestamp, no usable amount, exact duplicate). Anything that
is unusual but structurally valid (self-transactions, zero amounts in
some legitimate account-maintenance contexts) is flagged and counted,
not silently removed, unless explicitly configured to be dropped.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.data.schema import SCHEMA_COLUMNS, validate_schema


@dataclass
class PreprocessingStep:
    step: str
    reason: str
    rows_before: int
    rows_affected: int
    rows_after: int
    details: dict = field(default_factory=dict)


class DataPreprocessor:
    """
    Usage:
        pre = DataPreprocessor(raw_df, dataset_label="demo")
        clean_df, log = pre.run()
        pre.write(clean_df, log, out_dir="data/processed")
    """

    def __init__(
        self,
        df: pd.DataFrame,
        dataset_label: str = "unknown",
        drop_zero_amount: bool = True,
        drop_negative_amount: bool = True,
        drop_self_transactions: bool = False,  # flagged, not dropped, by default
    ):
        self.df = df.copy()
        self.dataset_label = dataset_label
        self.drop_zero_amount = drop_zero_amount
        self.drop_negative_amount = drop_negative_amount
        self.drop_self_transactions = drop_self_transactions
        self.log: list[PreprocessingStep] = []

    # ------------------------------------------------------------ helper
    def _record(self, step: str, reason: str, before: int, after: int, details: dict | None = None):
        self.log.append(
            PreprocessingStep(
                step=step,
                reason=reason,
                rows_before=before,
                rows_affected=before - after,
                rows_after=after,
                details=details or {},
            )
        )

    # ------------------------------------------------------------ steps
    def _step_validate_schema(self, df: pd.DataFrame) -> pd.DataFrame:
        result = validate_schema(df)
        if not result.is_valid:
            raise ValueError(
                f"Input to preprocessing does not conform to canonical schema: "
                f"missing={result.missing_columns} dtype_errors={result.dtype_errors}. "
                f"Run the appropriate dataset adapter first."
            )
        self._record("validate_schema", "Confirmed input matches canonical schema before proceeding", len(df), len(df))
        return df

    def _step_parse_timestamps(self, df: pd.DataFrame) -> pd.DataFrame:
        before = len(df)
        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
        n_unparseable = int(df["timestamp"].isna().sum())
        after_drop = df[df["timestamp"].notna()]
        self._record(
            "parse_and_drop_invalid_timestamps",
            "Rows with a timestamp that cannot be parsed cannot be placed in the "
            "temporal graph and are structurally unusable downstream; dropped.",
            before,
            len(after_drop),
            {"unparseable_count": n_unparseable},
        )
        return after_drop.reset_index(drop=True)

    def _step_drop_missing_endpoints(self, df: pd.DataFrame) -> pd.DataFrame:
        before = len(df)
        sender_ok = df["sender"].notna() & (df["sender"].astype(str).str.strip() != "")
        receiver_ok = df["receiver"].notna() & (df["receiver"].astype(str).str.strip() != "")
        after = df[sender_ok & receiver_ok].reset_index(drop=True)
        self._record(
            "drop_missing_endpoints",
            "A transaction with no valid sender or receiver has no edge to place "
            "in the account graph; dropped rather than guessed.",
            before,
            len(after),
        )
        return after

    def _step_handle_amounts(self, df: pd.DataFrame) -> pd.DataFrame:
        before = len(df)
        df = df.copy()
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

        nan_mask = df["amount"].isna()
        n_nan = int(nan_mask.sum())
        df = df[~nan_mask]
        self._record(
            "drop_nonnumeric_amount",
            "amount could not be parsed as a number; no safe substitute exists "
            "(Elliptic rows with amount=NaN by design are handled separately, "
            "see note below).",
            before,
            len(df),
            {"nan_count": n_nan, "note": "Elliptic adapter intentionally sets amount=NaN; "
             "those runs should not enable this drop step if amount-based features are unused."},
        )

        if self.drop_zero_amount:
            before2 = len(df)
            df = df[df["amount"] != 0]
            self._record(
                "drop_zero_amount",
                "A zero-value transfer carries no fund-flow signal for this "
                "system's purpose and is configured to be dropped "
                "(drop_zero_amount=True).",
                before2,
                len(df),
            )

        if self.drop_negative_amount:
            before3 = len(df)
            df = df[df["amount"] >= 0]
            self._record(
                "drop_negative_amount",
                "Negative amounts are not valid in this schema's semantics "
                "(direction is encoded by sender->receiver, not sign); "
                "configured to be dropped (drop_negative_amount=True).",
                before3,
                len(df),
            )

        return df.reset_index(drop=True)

    def _step_flag_self_transactions(self, df: pd.DataFrame) -> pd.DataFrame:
        before = len(df)
        self_tx_mask = df["sender"].astype(str) == df["receiver"].astype(str)
        n_self = int(self_tx_mask.sum())

        if self.drop_self_transactions:
            df = df[~self_tx_mask].reset_index(drop=True)
            reason = (
                "Self-transactions configured to be dropped (drop_self_transactions=True)."
            )
        else:
            reason = (
                "Self-transactions are flagged and counted but NOT dropped by default: "
                "they can reflect legitimate account-to-account transfers within one "
                "entity's own accounts. Set drop_self_transactions=True to remove them."
            )
        self._record("flag_self_transactions", reason, before, len(df), {"self_transaction_count": n_self})
        return df

    def _step_deduplicate(self, df: pd.DataFrame) -> pd.DataFrame:
        before = len(df)
        n_dup_ids = int(df.duplicated(subset=["transaction_id"], keep="first").sum())
        df = df.drop_duplicates(subset=["transaction_id"], keep="first").reset_index(drop=True)
        self._record(
            "deduplicate_transaction_ids",
            "Exact transaction_id duplicates are assumed to be re-ingestion "
            "artifacts, not distinct transactions; kept the first occurrence.",
            before,
            len(df),
            {"duplicate_ids_removed": n_dup_ids},
        )
        return df

    def _step_sort_chronologically(self, df: pd.DataFrame) -> pd.DataFrame:
        before = len(df)
        df = df.sort_values("timestamp", kind="mergesort").reset_index(drop=True)  # stable sort
        self._record(
            "sort_chronologically",
            "Mandatory for temporal graph construction and to prevent training/"
            "evaluation leakage — every downstream module assumes row order is "
            "non-decreasing in timestamp.",
            before,
            len(df),
        )
        return df

    def _step_preserve_labels(self, df: pd.DataFrame) -> pd.DataFrame:
        # No transformation — this step exists to make explicit, auditable,
        # that label/scenario_id/ring_id are carried through untouched.
        before = len(df)
        assert df["label"].isin([-1, 0, 1]).all(), "invalid label reached preservation step"
        self._record(
            "preserve_labels",
            "label/scenario_id/ring_id are carried through unmodified from the "
            "adapter output — this pipeline never assigns or infers a label.",
            before,
            before,
        )
        return df

    # ------------------------------------------------------------ run
    def run(self) -> tuple[pd.DataFrame, list[PreprocessingStep]]:
        df = self.df
        df = self._step_validate_schema(df)
        df = self._step_parse_timestamps(df)
        df = self._step_drop_missing_endpoints(df)
        df = self._step_handle_amounts(df)
        df = self._step_flag_self_transactions(df)
        df = self._step_deduplicate(df)
        df = self._step_sort_chronologically(df)
        df = self._step_preserve_labels(df)
        return df[SCHEMA_COLUMNS], self.log

    # ------------------------------------------------------------ output
    def write(self, clean_df: pd.DataFrame, log: list[PreprocessingStep], out_dir: str | Path) -> dict:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        clean_path = out_dir / "transactions_clean.csv"
        clean_df.to_csv(clean_path, index=False)

        log_record = {
            "dataset_label": self.dataset_label,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "rows_in": int(self.log[0].rows_before) if self.log else len(self.df),
            "rows_out": len(clean_df),
            "steps": [
                {
                    "step": s.step,
                    "reason": s.reason,
                    "rows_before": s.rows_before,
                    "rows_affected": s.rows_affected,
                    "rows_after": s.rows_after,
                    "details": s.details,
                }
                for s in log
            ],
        }
        log_path = out_dir / "preprocessing_log.json"
        with open(log_path, "w") as f:
            json.dump(log_record, f, indent=2, default=str)

        return {"clean_path": str(clean_path), "log_path": str(log_path), "log_record": log_record}
