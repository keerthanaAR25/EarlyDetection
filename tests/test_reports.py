"""
Phase 17 tests: report rendering utilities.

Run with: pytest tests/test_reports.py -v
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.evaluation.report_utils import render_report, df_to_html_table


def test_render_report_includes_title_and_cards():
    html = render_report(
        "Test Report", "meta info", [("Rows", 100), ("Positives", 5)], [("Section 1", "<p>body</p>")]
    )
    assert "<title>Test Report</title>" in html
    assert "Rows" in html and "100" in html
    assert "Section 1" in html
    assert "<p>body</p>" in html


def test_render_report_handles_no_cards_or_sections():
    html = render_report("Empty", "meta", [], [])
    assert "<title>Empty</title>" in html


def test_df_to_html_table_renders_rows():
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    html = df_to_html_table(df)
    assert "<table" in html
    assert "x" in html and "y" in html


def test_df_to_html_table_handles_empty_dataframe():
    html = df_to_html_table(pd.DataFrame())
    assert "No rows" in html


def test_df_to_html_table_respects_max_rows():
    df = pd.DataFrame({"a": range(200)})
    html = df_to_html_table(df, max_rows=5)
    assert html.count("<tr>") < 50
