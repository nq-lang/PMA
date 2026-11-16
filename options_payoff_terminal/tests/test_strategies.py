"""
tests/test_strategies.py

Tests for engine/strategies.py: every strategy in the Section 4 library
must be present in the registry, produce a non-crashing leg set (except
"Custom", which is intentionally empty), and have leg counts / net
long-short composition matching its textbook definition.
"""

from __future__ import annotations

import pytest

from engine.strategies import (
    STRATEGY_GROUPS,
    STRATEGY_REGISTRY,
    Leg,
    build_strategy_legs,
    clone_legs,
)

SPOT = 100.0
INC = 5.0
DTE = 30.0

REQUIRED_STRATEGIES = [
    # Single-leg
    "Long Call",
    "Short Call",
    "Long Put",
    "Short Put",
    "Long Stock",
    "Short Stock",
    # Vertical spreads
    "Bull Call Spread",
    "Bear Call Spread",
    "Bull Put Spread",
    "Bear Put Spread",
    # Volatility / straddle family
    "Long Straddle",
    "Short Straddle",
    "Long Strangle",
    "Short Strangle",
    "Strap",
    "Strip",
    # Time spreads
    "Calendar Call Spread",
    "Calendar Put Spread",
    "Diagonal Spread",
    # Wing / butterfly / condor family
    "Long Call Butterfly",
    "Long Put Butterfly",
    "Iron Butterfly",
    "Long Call Condor",
    "Long Put Condor",
    "Iron Condor",
    # Combo / synthetic / collar family
    "Collar",
    "Covered Call",
    "Protective Put",
    "Married Put",
    "Synthetic Long Stock",
    "Synthetic Short Stock",
    "Ratio Call Spread",
    "Ratio Put Spread",
    # Custom
    "Custom",
]


def test_all_required_strategies_present_in_registry():
    missing = [s for s in REQUIRED_STRATEGIES if s not in STRATEGY_REGISTRY]
    assert not missing, f"Missing strategies: {missing}"


def test_all_registry_entries_are_in_required_list_or_documented():
    """Guard against silent registry drift: every registered strategy
    should be one we intended to support."""
    extra = [s for s in STRATEGY_REGISTRY if s not in REQUIRED_STRATEGIES]
    assert not extra, f"Undocumented extra strategies: {extra}"


@pytest.mark.parametrize("name", REQUIRED_STRATEGIES)
def test_strategy_builds_without_error(name):
    legs = build_strategy_legs(name, SPOT, INC, DTE)
    assert isinstance(legs, list)
    for leg in legs:
        assert isinstance(leg, Leg)
        assert leg.kind in ("call", "put", "stock")
        assert leg.direction in (1, -1)
        assert leg.quantity > 0


def test_custom_strategy_is_empty():
    legs = build_strategy_legs("Custom", SPOT, INC, DTE)
    assert legs == []


def test_unknown_strategy_raises_keyerror():
    with pytest.raises(KeyError):
        build_strategy_legs("Not A Real Strategy", SPOT, INC, DTE)


# ---------------------------------------------------------------------------
# Structural correctness checks for specific strategies
# ---------------------------------------------------------------------------


def test_long_call_is_single_long_call_leg():
    legs = build_strategy_legs("Long Call", SPOT, INC, DTE)
    assert len(legs) == 1
    assert legs[0].kind == "call"
    assert legs[0].direction == 1


def test_bull_call_spread_is_long_lower_short_higher_call():
    legs = build_strategy_legs("Bull Call Spread", SPOT, INC, DTE)
    assert len(legs) == 2
    long_legs = [l for l in legs if l.direction == 1]
    short_legs = [l for l in legs if l.direction == -1]
    assert len(long_legs) == 1 and len(short_legs) == 1
    assert all(l.kind == "call" for l in legs)
    assert long_legs[0].strike < short_legs[0].strike


def test_bear_put_spread_is_long_higher_short_lower_put():
    legs = build_strategy_legs("Bear Put Spread", SPOT, INC, DTE)
    long_legs = [l for l in legs if l.direction == 1]
    short_legs = [l for l in legs if l.direction == -1]
    assert all(l.kind == "put" for l in legs)
    assert long_legs[0].strike > short_legs[0].strike


def test_long_straddle_same_strike_call_and_put():
    legs = build_strategy_legs("Long Straddle", SPOT, INC, DTE)
    assert len(legs) == 2
    kinds = {l.kind for l in legs}
    assert kinds == {"call", "put"}
    strikes = {l.strike for l in legs}
    assert len(strikes) == 1  # same strike
    assert all(l.direction == 1 for l in legs)


def test_long_strangle_different_strikes():
    legs = build_strategy_legs("Long Strangle", SPOT, INC, DTE)
    call_leg = next(l for l in legs if l.kind == "call")
    put_leg = next(l for l in legs if l.kind == "put")
    assert call_leg.strike > put_leg.strike
    assert call_leg.direction == 1 and put_leg.direction == 1


def test_strap_has_two_calls_one_put():
    legs = build_strategy_legs("Strap", SPOT, INC, DTE)
    call_leg = next(l for l in legs if l.kind == "call")
    put_leg = next(l for l in legs if l.kind == "put")
    assert call_leg.quantity == 2
    assert put_leg.quantity == 1
    assert call_leg.strike == put_leg.strike


def test_strip_has_two_puts_one_call():
    legs = build_strategy_legs("Strip", SPOT, INC, DTE)
    call_leg = next(l for l in legs if l.kind == "call")
    put_leg = next(l for l in legs if l.kind == "put")
    assert put_leg.quantity == 2
    assert call_leg.quantity == 1


def test_iron_condor_has_four_legs_two_puts_two_calls():
    legs = build_strategy_legs("Iron Condor", SPOT, INC, DTE)
    assert len(legs) == 4
    puts = [l for l in legs if l.kind == "put"]
    calls = [l for l in legs if l.kind == "call"]
    assert len(puts) == 2 and len(calls) == 2
    # net credit structure: short strikes closer to spot than long strikes
    long_put = next(l for l in puts if l.direction == 1)
    short_put = next(l for l in puts if l.direction == -1)
    short_call = next(l for l in calls if l.direction == -1)
    long_call = next(l for l in calls if l.direction == 1)
    assert long_put.strike < short_put.strike < short_call.strike < long_call.strike


def test_iron_butterfly_center_strikes_match():
    legs = build_strategy_legs("Iron Butterfly", SPOT, INC, DTE)
    short_put = next(l for l in legs if l.kind == "put" and l.direction == -1)
    short_call = next(l for l in legs if l.kind == "call" and l.direction == -1)
    assert short_put.strike == short_call.strike  # both at ATM


def test_long_call_butterfly_wing_symmetry_and_body_quantity():
    legs = build_strategy_legs("Long Call Butterfly", SPOT, INC, DTE)
    assert len(legs) == 3
    body = next(l for l in legs if l.direction == -1)
    wings = [l for l in legs if l.direction == 1]
    assert body.quantity == 2
    assert len(wings) == 2
    low_wing, high_wing = sorted(wings, key=lambda l: l.strike)
    # symmetric distance from body strike
    assert (body.strike - low_wing.strike) == pytest.approx(high_wing.strike - body.strike)


def test_covered_call_is_long_stock_plus_short_call():
    legs = build_strategy_legs("Covered Call", SPOT, INC, DTE)
    assert len(legs) == 2
    stock_leg = next(l for l in legs if l.kind == "stock")
    call_leg = next(l for l in legs if l.kind == "call")
    assert stock_leg.direction == 1
    assert call_leg.direction == -1


def test_protective_put_is_long_stock_plus_long_put():
    legs = build_strategy_legs("Protective Put", SPOT, INC, DTE)
    stock_leg = next(l for l in legs if l.kind == "stock")
    put_leg = next(l for l in legs if l.kind == "put")
    assert stock_leg.direction == 1
    assert put_leg.direction == 1


def test_synthetic_long_stock_is_long_call_short_put_same_strike():
    legs = build_strategy_legs("Synthetic Long Stock", SPOT, INC, DTE)
    call_leg = next(l for l in legs if l.kind == "call")
    put_leg = next(l for l in legs if l.kind == "put")
    assert call_leg.direction == 1
    assert put_leg.direction == -1
    assert call_leg.strike == put_leg.strike


def test_collar_has_stock_long_put_short_call():
    legs = build_strategy_legs("Collar", SPOT, INC, DTE)
    assert len(legs) == 3
    stock_leg = next(l for l in legs if l.kind == "stock")
    put_leg = next(l for l in legs if l.kind == "put")
    call_leg = next(l for l in legs if l.kind == "call")
    assert stock_leg.direction == 1
    assert put_leg.direction == 1
    assert call_leg.direction == -1
    assert put_leg.strike < call_leg.strike


def test_calendar_call_spread_has_two_different_expirations():
    legs = build_strategy_legs("Calendar Call Spread", SPOT, INC, DTE)
    assert len(legs) == 2
    dtes = {l.dte_days for l in legs}
    assert len(dtes) == 2  # different expirations
    short_leg = next(l for l in legs if l.direction == -1)
    long_leg = next(l for l in legs if l.direction == 1)
    assert short_leg.dte_days < long_leg.dte_days
    assert short_leg.strike == long_leg.strike  # same strike (calendar, not diagonal)


def test_ratio_call_spread_backspread_quantities():
    legs = build_strategy_legs("Ratio Call Spread", SPOT, INC, DTE)
    short_leg = next(l for l in legs if l.direction == -1)
    long_leg = next(l for l in legs if l.direction == 1)
    assert short_leg.quantity == 1
    assert long_leg.quantity == 2
    assert long_leg.strike > short_leg.strike


# ---------------------------------------------------------------------------
# Custom leg-builder can reproduce presets manually (acceptance criterion #3)
# ---------------------------------------------------------------------------


def test_manually_built_bull_call_spread_matches_preset():
    """The custom leg-builder is just a list of Leg objects -- verify that
    manually constructing the same legs as the 'Bull Call Spread' preset
    produces an equivalent (field-for-field) leg set."""
    preset_legs = build_strategy_legs("Bull Call Spread", SPOT, INC, DTE)
    manual_legs = [
        Leg("call", +1, 1, 100.0, DTE),
        Leg("call", -1, 1, 110.0, DTE),
    ]
    assert len(preset_legs) == len(manual_legs)
    for p, m in zip(
        sorted(preset_legs, key=lambda l: l.strike),
        sorted(manual_legs, key=lambda l: l.strike),
    ):
        assert p.kind == m.kind
        assert p.direction == m.direction
        assert p.quantity == m.quantity
        assert p.strike == m.strike
        assert p.dte_days == m.dte_days


def test_clone_legs_is_independent_copy():
    legs = build_strategy_legs("Long Straddle", SPOT, INC, DTE)
    cloned = clone_legs(legs)
    cloned[0].strike = 999.0
    assert legs[0].strike != 999.0


def test_strategy_groups_cover_full_registry():
    grouped = {name for names in STRATEGY_GROUPS.values() for name in names}
    assert grouped == set(STRATEGY_REGISTRY.keys())


def test_leg_label_formatting():
    call_leg = Leg("call", 1, 1, 280.0, 30)
    assert call_leg.label() == "280C"
    short_put_leg = Leg("put", -1, 2, 280.0, 30)
    assert short_put_leg.label() == "-280P x2"
    stock_leg = Leg("stock", 1, 1, 100.0, 0)
    assert "Stock" in stock_leg.label()
