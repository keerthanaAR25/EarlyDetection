"""
AMLSim dataset adapter.

AMLSim (github.com/IBM/AMLSim) is a Java/Python multi-agent transaction
simulator — it is NOT a downloadable finished dataset. The user must
run the simulator themselves (see docs/dataset.md) and drop its output
CSVs under data/raw/amlsim/.

Confirmed output schema (IBM/AMLSim wiki, "Data Schema for Input
Parameters and Generated Data Set", accessed for this project):

transactions.csv:
    tran_id, orig_acct, bene_acct, tx_type, base_amt,
    tran_timestamp, is_sar, alert_id   (alert_id == -1 if not alerted)

alert_transactions.csv (subset, alerted transactions only):
    alert_id, alert_type, is_sar, tran_id, orig_acct, bene_acct,
    tx_type, base_amt, tran_timestamp

accounts.csv:
    acct_id, dsply_nm, type, acct_stat, acct_rptng_crncy,
    prior_sar_count, branch_id, open_dt, close_dt, initial_deposit,
    tx_behavior_id, bank_id, ... (optional PII columns omitted here)

IMPORTANT ASSUMPTION (documented in docs/dataset.md): earlier AMLSim
runs were observed to use `tran_timestamp` as a simulation *step*
index, not a wall-clock timestamp — that behaviour is preserved below
as a fallback. However, a real uploaded AMLSim run (audited directly,
2026-09) was found to write `tran_timestamp` as a genuine ISO-8601
date already (e.g. "2017-01-01"), with one step == one real calendar
day. This adapter now DETECTS which case it's in — by trying to parse
the column as a date first — rather than assuming step-index encoding
unconditionally, since blindly applying the step-offset conversion to
an already-real timestamp column would silently corrupt every date in
the dataset.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from src.data.base_adapter import BaseDatasetAdapter

logger = logging.getLogger(__name__)


class AMLSimAdapter(BaseDatasetAdapter):
    source_name = "amlsim"

    def __init__(
        self,
        raw_path: str | Path,
        transactions_file: str = "transactions.csv",
        alert_transactions_file: str = "alert_transactions.csv",
        sim_start_date: str = "2024-01-01",
        step_unit: str = "D",  # pandas offset alias: 'D' = 1 day per step
    ):
        super().__init__(raw_path)
        self.transactions_file = transactions_file
        self.alert_transactions_file = alert_transactions_file
        self.sim_start_date = pd.Timestamp(sim_start_date, tz="UTC")
        self.step_unit = step_unit

    def _resolve_timestamp(self, raw_column: pd.Series) -> pd.Series:
        """Real ISO dates if parseable as such; otherwise treat as a
        step index and apply the synthetic offset (documented fallback
        assumption above)."""
        parsed_as_dates = pd.to_datetime(raw_column, errors="coerce", utc=True)
        frac_parseable = parsed_as_dates.notna().mean()

        if frac_parseable > 0.99:
            logger.info(
                "tran_timestamp parses as real dates (%.1f%% of rows) — using "
                "directly, NOT applying the step->date synthetic offset.",
                frac_parseable * 100,
            )
            return parsed_as_dates

        logger.info(
            "tran_timestamp does not parse as dates (only %.1f%% would) — "
            "treating as a step index and applying the synthetic offset "
            "documented in this module's docstring.",
            frac_parseable * 100,
        )
        step_offset = pd.to_timedelta(raw_column.astype(float), unit=self.step_unit)
        return self.sim_start_date + step_offset

    def _load_raw(self) -> pd.DataFrame:
        tx_path = self.raw_path / self.transactions_file
        if not tx_path.exists():
            raise FileNotFoundError(
                f"AMLSim transactions file not found at {tx_path}. "
                f"Run the AMLSim simulator first and copy its output "
                f"here — see docs/dataset.md."
            )

        tx = pd.read_csv(tx_path)

        required = {"tran_id", "orig_acct", "bene_acct", "base_amt", "tran_timestamp"}
        missing = required - set(tx.columns)
        if missing:
            raise ValueError(
                f"AMLSim transactions.csv is missing expected columns {missing}. "
                f"This adapter targets the schema documented in the IBM/AMLSim "
                f"wiki; if your simulator run used a custom schema.json, adjust "
                f"this adapter's column mapping accordingly."
            )

        if "is_sar" not in tx.columns:
            tx["is_sar"] = False
        if "alert_id" not in tx.columns:
            tx["alert_id"] = -1

        timestamp = self._resolve_timestamp(tx["tran_timestamp"])

        alert_id = tx["alert_id"].astype("Int64")
        has_alert = alert_id.notna() & (alert_id != -1)

        out = pd.DataFrame(
            {
                "transaction_id": tx["tran_id"].astype(str),
                "sender": tx["orig_acct"].astype(str),
                "receiver": tx["bene_acct"].astype(str),
                "amount": tx["base_amt"],
                "timestamp": timestamp,
                "label": tx["is_sar"].astype(bool).astype(int),
                # AMLSim's alert_id groups all transactions belonging to one
                # generated laundering typology instance — that maps
                # naturally to both scenario_id and ring_id in our schema.
                "scenario_id": alert_id.astype(str).where(has_alert, ""),
                "ring_id": alert_id.astype(str).where(has_alert, ""),
            }
        )
        return out

    def load_accounts(self, accounts_file: str = "accounts.csv") -> pd.DataFrame | None:
        """Optional: account metadata, used by feature engineering later
        (e.g. account open/close dates) but not part of the canonical
        transaction schema."""
        path = self.raw_path / accounts_file
        if not path.exists():
            logger.warning("AMLSim accounts file not found at %s; skipping.", path)
            return None
        return pd.read_csv(path)
