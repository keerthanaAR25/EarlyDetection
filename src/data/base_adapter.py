"""
Abstract interface for dataset adapters.

Each adapter's job is narrow: read a dataset's native raw format and
map it onto the canonical schema (src/data/schema.py). Adapters must
NOT invent labels, fabricate columns, or silently drop rows — anything
it cannot map, it must leave as null/-1/"" per the schema's documented
defaults and let src/preprocessing/ decide what to do about it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

from src.data.schema import coerce_to_schema, validate_schema, SchemaValidationResult


class BaseDatasetAdapter(ABC):
    """Every adapter exposes: name, raw path, load(), and validate()."""

    #: dataset_source value written into every row this adapter produces
    source_name: str = "unknown"

    def __init__(self, raw_path: str | Path):
        self.raw_path = Path(raw_path)

    @abstractmethod
    def _load_raw(self) -> pd.DataFrame:
        """Read the dataset's native files and return a DataFrame with
        at least sender/receiver/amount/timestamp mapped, using
        whatever column names make sense before schema coercion."""
        raise NotImplementedError

    def load(self) -> pd.DataFrame:
        """Public entry point: load raw data and coerce to canonical schema."""
        raw = self._load_raw()
        return coerce_to_schema(raw, dataset_source=self.source_name)

    def validate(self, df: pd.DataFrame | None = None) -> SchemaValidationResult:
        if df is None:
            df = self.load()
        return validate_schema(df)

    def describe(self) -> dict:
        """Lightweight provenance info surfaced in docs/dataset.md and
        the data quality report — never guessed, only what's actually
        known about this adapter's source."""
        return {
            "source_name": self.source_name,
            "raw_path": str(self.raw_path),
            "raw_path_exists": self.raw_path.exists(),
        }
