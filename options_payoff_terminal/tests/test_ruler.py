from engine.strategies import build_strategy_legs
from ui.ruler import build_ruler_html, ruler_bounds, snap_strike


def test_bounds_contain_all_strikes_and_spot():
    legs = build_strategy_legs("Iron Condor", 100.0, 5.0, 30.0)
    lo, hi = ruler_bounds(legs, 100.0, 5.0)
    assert lo < min(l.strike for l in legs) and hi > max(l.strike for l in legs)
    assert lo <= 100.0 <= hi and lo % 5 == 0 and hi % 5 == 0


def test_snap_strike_rounds_and_clamps():
    assert snap_strike(50, 150, 0.5, 5) == 100
    assert snap_strike(50, 150, 0.512, 5) == 100
    assert snap_strike(50, 150, -1, 5) == 50 and snap_strike(50, 150, 2, 5) == 150


def test_one_chip_per_option_leg_and_none_for_stock():
    legs = build_strategy_legs("Covered Call", 100.0, 5.0, 30.0)
    html = build_ruler_html(legs, 100.0, 5.0)
    assert html.count("ruler-chip ") == 1  # stock leg has no chip
    legs = build_strategy_legs("Iron Condor", 100.0, 5.0, 30.0)
    html = build_ruler_html(legs, 100.0, 5.0)
    assert html.count('class="ruler-chip') == 4 and 'data-idx="3"' in html
    assert "long" in html and "short" in html


def test_same_strike_chips_stack_vertically():
    legs = build_strategy_legs("Long Straddle", 100.0, 5.0, 30.0)
    html = build_ruler_html(legs, 100.0, 5.0)
    assert "top:20px" in html and "top:46px" in html


def test_nearby_chips_spread_to_different_rows():
    from engine.strategies import Leg
    legs = [Leg("call", 1, 1, 100.0, 30), Leg("call", -1, 1, 105.0, 30), Leg("call", 1, 1, 200.0, 30)]
    html = build_ruler_html(legs, 100.0, 5.0)
    assert "top:20px" in html and "top:46px" in html
