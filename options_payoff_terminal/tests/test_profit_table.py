"""
tests/test_profit_table.py

Tests for ui/profit_table.py's pure data-building function: the price x
date grid must agree with engine.payoff.asof_payoff at every cell (no
separate/divergent calculation path), and must have the right shape.
"""

from __future__ import annotations

import numpy as np
import pytest

from engine.payoff import asof_payoff, price_legs
from engine.strategies import build_strategy_legs
from ui.profit_table import build_profit_table_data, _heat_color

SPOT = 100.0
R = 0.05
Q = 0.0


def flat_iv_fn(strike, spot, dte_days, iv=0.30):
    return iv


def test_profit_table_shape_matches_rows_and_columns():
    legs = build_strategy_legs("Long Call", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    price_rows = np.array([90.0, 100.0, 110.0])
    date_cols = np.array([0, 10, 20, 30])
    headers, rows = build_profit_table_data(priced, price_rows, date_cols, SPOT, R, Q, flat_iv_fn)
    assert len(headers) == 4
    assert len(rows) == 3
    assert all(len(r) == 4 for r in rows)


def test_profit_table_cells_match_asof_payoff_directly():
    """Every cell in the table must be numerically identical to calling
    asof_payoff directly for that (price, day) pair -- no separate
    calculation path that could silently drift from the chart's numbers."""
    legs = build_strategy_legs("Bull Call Spread", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    price_rows = np.array([95.0, 105.0])
    date_cols = np.array([0, 15])
    headers, rows = build_profit_table_data(priced, price_rows, date_cols, SPOT, R, Q, flat_iv_fn)

    for i, price in enumerate(price_rows):
        for j, days in enumerate(date_cols):
            expected = asof_payoff(priced, np.array([price]), R, Q, flat_iv_fn, SPOT, float(days))[0]
            assert rows[i][j] == pytest.approx(float(expected))


def test_today_column_header_labeled_today():
    legs = build_strategy_legs("Long Call", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    headers, _ = build_profit_table_data(
        priced, np.array([100.0]), np.array([0, 5]), SPOT, R, Q, flat_iv_fn
    )
    assert headers[0] == "Today"
    assert headers[1] == "+5d"


def test_heat_color_profit_vs_loss_distinct():
    profit_color = _heat_color(500.0, scale=1000.0)
    loss_color = _heat_color(-500.0, scale=1000.0)
    assert "32, 214, 123" in profit_color  # profit green
    assert "255, 92, 92" in loss_color  # loss red


def test_heat_color_zero_scale_does_not_crash():
    # all-zero table (e.g. a fully hedged position at a single instant)
    color = _heat_color(0.0, scale=0.0)
    assert color  # just confirm it returns something sane, no ZeroDivisionError
