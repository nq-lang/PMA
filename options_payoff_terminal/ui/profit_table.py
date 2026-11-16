"""
ui/profit_table.py
===================

The "Profit $" table: a price (rows) x date (columns) grid, heat-colored
green for profit / red for loss, matching the reference terminal's
bottom-panel table. Each cell is the as-of-date P&L at that price and that
date, computed via the same `engine.payoff.asof_payoff` used for the
dashed chart overlay -- so the table and chart can never silently
disagree.
"""

from __future__ import annotations

import numpy as np
from nicegui import ui

from engine.payoff import PricedLeg, asof_payoff
from ui.theme import PALETTE


def build_profit_table_data(
    priced_legs: list[PricedLeg],
    price_rows: np.ndarray,
    date_cols_days: np.ndarray,
    spot: float,
    r: float,
    q: float,
    iv_fn,
) -> tuple[list[str], list[list[float]]]:
    """Compute the full price x date P&L grid.

    Returns (column_headers, rows) where `rows[i]` is the P&L across every
    date column for `price_rows[i]`, i.e. rows are prices (as in the
    reference screenshot) and columns are days-from-now.
    """
    column_headers = [f"+{int(d)}d" if d > 0 else "Today" for d in date_cols_days]
    rows: list[list[float]] = []
    for price in price_rows:
        row_values = []
        for days_elapsed in date_cols_days:
            S_point = np.array([price])
            pnl = asof_payoff(priced_legs, S_point, r, q, iv_fn, spot, float(days_elapsed))
            row_values.append(float(pnl[0]))
        rows.append(row_values)
    return column_headers, rows


def _heat_color(value: float, scale: float) -> str:
    """Map a P&L value to a background color: green fading in for profit,
    red fading in for loss, intensity scaled by `scale` (typically the
    max absolute P&L in the table, so the most extreme cells are fully
    saturated and cells near zero are close to the panel background)."""
    if scale <= 0:
        scale = 1.0
    intensity = min(abs(value) / scale, 1.0)
    if value >= 0:
        # blend from panel background to profit green
        return f"rgba(32, 214, 123, {0.08 + 0.55 * intensity:.3f})"
    return f"rgba(255, 92, 92, {0.08 + 0.55 * intensity:.3f})"


def profit_table(
    price_rows: np.ndarray,
    column_headers: list[str],
    rows: list[list[float]],
    spot: float,
) -> ui.element:
    """Render the profit table as a scrollable HTML table with heat-map
    cell coloring. Rows are sorted highest price first (matching the
    reference screenshot's top-to-bottom descending price order)."""
    all_values = [v for row in rows for v in row]
    scale = max((abs(v) for v in all_values), default=1.0)

    order = sorted(range(len(price_rows)), key=lambda i: price_rows[i], reverse=True)

    with ui.element("div").classes("w-full overflow-x-auto opt-panel") as container:
        with ui.element("table").style(
            "border-collapse: collapse; width: 100%; font-family: monospace; font-size: 12px;"
        ):
            with ui.element("thead"):
                with ui.element("tr"):
                    with ui.element("th").style(
                        f"text-align:left; padding:4px 8px; color:{PALETTE.text_secondary}; "
                        f"position: sticky; left: 0; background:{PALETTE.bg_panel};"
                    ):
                        ui.label("Price $")
                    for header in column_headers:
                        with ui.element("th").style(
                            f"text-align:right; padding:4px 8px; color:{PALETTE.text_secondary};"
                        ):
                            ui.label(header)
            with ui.element("tbody"):
                for i in order:
                    price = price_rows[i]
                    row_values = rows[i]
                    is_spot_row = abs(price - spot) < (price_rows[1] - price_rows[0]) / 2 if len(price_rows) > 1 else False
                    with ui.element("tr"):
                        label_style = (
                            f"text-align:left; padding:4px 8px; font-weight:600; "
                            f"position: sticky; left: 0; background:{PALETTE.bg_panel}; "
                            f"color:{PALETTE.accent_blue if is_spot_row else PALETTE.text_primary};"
                        )
                        with ui.element("td").style(label_style):
                            ui.label(f"${price:,.2f}")
                        for value in row_values:
                            bg = _heat_color(value, scale)
                            with ui.element("td").style(
                                f"text-align:right; padding:4px 8px; background-color:{bg};"
                            ):
                                ui.label(f"{value:,.0f}")
    return container
