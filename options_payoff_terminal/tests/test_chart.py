"""
tests/test_chart.py

Tests for ui/chart.py's pure data-shaping functions (no NiceGUI server
needed): zero-crossing insertion for the gradient-fill split, and basic
shape/keys of the generated ECharts option dict.
"""

from __future__ import annotations

import numpy as np

from ui.chart import _split_by_sign, build_payoff_chart_options


def _lines(option):
    return [s for s in option["series"] if not s["name"].startswith("_")]


def test_split_by_sign_inserts_exact_zero_crossing():
    S = np.array([90.0, 100.0, 110.0])
    pnl = np.array([-10.0, 0.0, 10.0])
    points = _split_by_sign(S, pnl)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    assert 100.0 in xs
    assert ys[xs.index(100.0)] == 0.0


def test_split_by_sign_interpolates_when_no_exact_zero_grid_point():
    S = np.array([90.0, 110.0])
    pnl = np.array([-10.0, 10.0])
    points = _split_by_sign(S, pnl)
    # Should have inserted a crossing point at x=100 (linear interpolation)
    assert len(points) == 3
    crossing = points[1]
    assert crossing[0] == 100.0
    assert crossing[1] == 0.0


def test_split_by_sign_no_crossing_when_all_same_sign():
    S = np.array([100.0, 110.0, 120.0])
    pnl = np.array([5.0, 10.0, 15.0])
    points = _split_by_sign(S, pnl)
    assert len(points) == 3  # no extra points inserted


def test_build_chart_options_has_required_keys():
    S = np.linspace(80, 120, 50)
    pnl = S - 100.0
    option = build_payoff_chart_options(S, pnl, spot=100.0, breakevens=[100.0])
    assert "series" in option
    assert "xAxis" in option
    assert "yAxis" in option
    assert len(_lines(option)) == 1  # no as-of overlay requested


def test_build_chart_options_includes_asof_series_when_provided():
    S = np.linspace(80, 120, 50)
    pnl = S - 100.0
    asof = 0.5 * (S - 100.0)
    option = build_payoff_chart_options(S, pnl, spot=100.0, breakevens=[100.0], asof_pnl=asof)
    assert len(_lines(option)) == 2
    names = {s["name"] for s in option["series"]}
    assert "As Of Date" in names


def test_build_chart_options_marklines_include_spot_and_breakevens():
    S = np.linspace(80, 120, 50)
    pnl = S - 100.0
    option = build_payoff_chart_options(S, pnl, spot=105.0, breakevens=[100.0, 110.0])
    mark_line_data = option["series"][0]["markLine"]["data"]
    x_values = [d.get("xAxis") for d in mark_line_data if "xAxis" in d]
    assert 105.0 in x_values
    assert 100.0 in x_values
    assert 110.0 in x_values


def test_fills_are_clipped_at_zero():
    S = np.linspace(80, 120, 41)
    pnl = S - 100.0
    opt = build_payoff_chart_options(S, pnl, spot=100.0, breakevens=[100.0])
    prof = next(s for s in opt["series"] if s["name"] == "_profit_fill")
    loss = next(s for s in opt["series"] if s["name"] == "_loss_fill")
    assert min(p[1] for p in prof["data"]) >= 0.0
    assert max(p[1] for p in loss["data"]) <= 0.0


def test_hover_and_breakeven_markers_present():
    from ui.chart import hover_texts
    S = np.linspace(80, 120, 5)
    pnl = S - 100.0
    g = {k: np.ones(5) for k in ("delta", "gamma", "theta", "vega")}
    h = hover_texts(S, pnl, 100.0, 50.0, g, "money")
    opt = build_payoff_chart_options(S, pnl, 100.0, [100.0], hover=h)
    assert len(opt["series"][0]["data"][0]) == 3 and "Dominant Greek" in h[0]
    assert ":formatter" in opt["tooltip"]
    assert opt["series"][0]["markPoint"]["data"][0]["explain"]


def test_dominant_greek_choice():
    from ui.chart import dominant_greek
    assert dominant_greek(100, 0.0, 0.0, 0.0, 100) == "Delta"
    assert dominant_greek(0, 0, -50, 0, 100) == "Theta"
