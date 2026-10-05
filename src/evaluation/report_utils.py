"""
Lightweight HTML report rendering shared by scripts/generate_reports.py.
"""
from __future__ import annotations

import pandas as pd

_STYLE = """
<style>
body { font-family: -apple-system, Segoe UI, Arial, sans-serif; margin: 2rem; color: #1a1a2e; background: #f7f8fb; }
h1 { margin-bottom: 0.2rem; } h2 { margin-top: 2rem; }
.meta { color: #666; margin-bottom: 1.5rem; }
.cards { display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.5rem; }
.card { background: white; border-radius: 8px; padding: 1rem 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08); min-width: 150px; }
.card .label { font-size: 0.75rem; color: #888; text-transform: uppercase; letter-spacing: 0.03em; }
.card .value { font-size: 1.5rem; font-weight: 600; margin-top: 0.25rem; }
table { border-collapse: collapse; width: 100%; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 1.5rem; }
th, td { padding: 0.5rem 0.9rem; text-align: left; border-bottom: 1px solid #eee; font-size: 0.9rem; }
th { background: #eef1fa; }
.note { font-size: 0.85rem; color: #888; font-style: italic; }
</style>
"""


def render_report(title: str, meta_line: str, cards: list, sections: list) -> str:
    cards_html = "".join(
        f'<div class="card"><div class="label">{label}</div><div class="value">{value}</div></div>'
        for label, value in cards
    )
    sections_html = "".join(f"<h2>{heading}</h2>{body}" for heading, body in sections)

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title>{_STYLE}</head>
<body>
<h1>{title}</h1>
<div class="meta">{meta_line}</div>
<div class="cards">{cards_html}</div>
{sections_html}
</body></html>"""


def df_to_html_table(df: pd.DataFrame, max_rows: int = 100) -> str:
    if df.empty:
        return "<p class='note'>No rows.</p>"
    return df.head(max_rows).to_html(index=False, border=0, na_rep="—")
