"""Adapter for the generated synthetic demo dataset (src/data/demo_generator.py)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data.base_adapter import BaseDatasetAdapter


class DemoAdapter(BaseDatasetAdapter):
    source_name = "demo"

    def __init__(self, raw_path: str | Path, transactions_file: str = "transactions.csv"):
        super().__init__(raw_path)
        self.transactions_file = transactions_file

    def _load_raw(self) -> pd.DataFrame:
        path = self.raw_path / self.transactions_file
        if not path.exists():
            raise FileNotFoundError(
                f"Demo transactions file not found at {path}. Run "
                f"`python scripts/generate_demo_data.py` first."
            )
        df = pd.read_csv(path, parse_dates=["timestamp"])
        return df

    def load_ground_truth(self, filename: str = "ring_ground_truth.json") -> list[dict]:
        import json

        path = self.raw_path / filename
        if not path.exists():
            return []
        with open(path) as f:
            return json.load(f)
