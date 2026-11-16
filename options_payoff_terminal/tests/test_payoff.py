"""
tests/test_payoff.py

Tests for engine/payoff.py:
- Breakeven correctness for a known vertical spread (closed-form comparison)
- Max Profit/Loss correctness for a bounded strategy (vertical spread) and
  an unbounded one (long call / short call)
- Position Greeks aggregation sanity (long call vs. long put signs, covered
  call combining stock + short call correctly)
- Probability of Profit sanity (ATM straddle ~50/50-ish under lognormal,
  deep ITM/OTM edge cases)
- As-of-date payoff reflects remaining extrinsic value (not a naive linear
  interpolation between today and expiration)
- Net entry cost sign conventions (debit vs. credit)
"""

from __future__ import annotations

import numpy as np
import pytest

from engine.payoff import (
    compute_stats,
    expiration_payoff,
    find_breakevens,
    max_profit_loss,
    net_entry_cost,
    position_greeks,
    price_grid,
    price_legs,
    probability_of_profit,
    asof_payoff,
)
from engine.strategies import Leg, build_strategy_legs

SPOT = 100.0
R = 0.05
Q = 0.0


def flat_iv_fn(strike, spot, dte_days, iv=0.30):
    """A trivial constant-IV function, used so payoff-engine tests don't
    depend on MarketSimulator's skew shape -- keeps these tests focused on
    payoff math correctness."""
    return iv


# ---------------------------------------------------------------------------
# Breakeven correctness: known vertical spread
# ---------------------------------------------------------------------------


def test_bull_call_spread_breakeven_matches_closed_form():
    """For a bull call spread (long K1 call, short K2 call, K1<K2), the
    breakeven at expiration is K1 + net_debit_per_share -- a well-known
    closed-form result we can check the generic root-finder against."""
    legs = [
        Leg("call", +1, 1, 100.0, 30),
        Leg("call", -1, 1, 110.0, 30),
    ]
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    cost = net_entry_cost(priced)  # positive = debit paid, in dollars (x100 multiplier)
    net_debit_per_share = cost / 100.0

    S = price_grid(SPOT, price_range_pct=0.5, n_points=500)
    pnl = expiration_payoff(priced, S)
    breakevens = find_breakevens(S, pnl)

    expected_breakeven = 100.0 + net_debit_per_share
    assert len(breakevens) == 1
    assert breakevens[0] == pytest.approx(expected_breakeven, abs=0.05)


def test_bull_put_spread_breakeven_matches_closed_form():
    """Bull put spread (short K2 put, long K1 put, K1<K2): breakeven at
    expiration is K2 - net_credit_per_share."""
    legs = [
        Leg("put", +1, 1, 90.0, 30),
        Leg("put", -1, 1, 100.0, 30),
    ]
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    cost = net_entry_cost(priced)  # negative = net credit received
    net_credit_per_share = -cost / 100.0

    S = price_grid(SPOT, price_range_pct=0.5, n_points=500)
    pnl = expiration_payoff(priced, S)
    breakevens = find_breakevens(S, pnl)

    expected_breakeven = 100.0 - net_credit_per_share
    assert len(breakevens) == 1
    assert breakevens[0] == pytest.approx(expected_breakeven, abs=0.05)


def test_long_straddle_has_two_breakevens_symmetric_around_strike():
    legs = build_strategy_legs("Long Straddle", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    S = price_grid(SPOT, price_range_pct=0.6, n_points=600)
    pnl = expiration_payoff(priced, S)
    breakevens = find_breakevens(S, pnl)
    assert len(breakevens) == 2
    strike = legs[0].strike
    cost_per_share = net_entry_cost(priced) / 100.0
    lower_expected = strike - cost_per_share
    upper_expected = strike + cost_per_share
    assert breakevens[0] == pytest.approx(lower_expected, abs=0.1)
    assert breakevens[1] == pytest.approx(upper_expected, abs=0.1)


def test_iron_condor_has_two_breakevens():
    legs = build_strategy_legs("Iron Condor", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    S = price_grid(SPOT, price_range_pct=0.4, n_points=500)
    pnl = expiration_payoff(priced, S)
    breakevens = find_breakevens(S, pnl)
    assert len(breakevens) == 2
    assert breakevens[0] < SPOT < breakevens[1]


def test_breakeven_generic_root_finder_works_on_custom_combination():
    """A deliberately unusual, non-preset combination (2 long calls at
    different strikes, 1 short put) to confirm the root-finder doesn't
    assume any particular leg count/shape."""
    legs = [
        Leg("call", +1, 1, 95.0, 30),
        Leg("call", +1, 1, 115.0, 30),
        Leg("put", -1, 1, 90.0, 30),
    ]
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    S = price_grid(SPOT, price_range_pct=0.5, n_points=800)
    pnl = expiration_payoff(priced, S)
    breakevens = find_breakevens(S, pnl)
    # Just confirm it finds at least one breakeven and each is a genuine
    # sign change in the interpolated P&L.
    assert len(breakevens) >= 1
    for be in breakevens:
        pnl_at_be = np.interp(be, S, pnl)
        assert abs(pnl_at_be) < 1.0  # near zero at the located breakeven


# ---------------------------------------------------------------------------
# Max Profit / Max Loss: bounded strategy
# ---------------------------------------------------------------------------


def test_bull_call_spread_max_profit_and_loss_bounded():
    """Bull call spread: Max Loss = net debit paid; Max Profit = spread
    width - net debit paid. Both bounded (not unlimited)."""
    legs = [
        Leg("call", +1, 1, 100.0, 30),
        Leg("call", -1, 1, 110.0, 30),
    ]
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    cost = net_entry_cost(priced)  # net debit, dollars
    S = price_grid(SPOT, price_range_pct=0.5, n_points=500)
    pnl = expiration_payoff(priced, S)
    max_profit, max_loss = max_profit_loss(priced, S, pnl)

    assert not max_profit.is_unbounded
    assert not max_loss.is_unbounded

    spread_width_dollars = (110.0 - 100.0) * 100.0
    expected_max_profit = spread_width_dollars - cost
    expected_max_loss = -cost

    assert max_profit.value == pytest.approx(expected_max_profit, abs=1.0)
    assert max_loss.value == pytest.approx(expected_max_loss, abs=1.0)


def test_iron_condor_max_profit_and_loss_bounded():
    legs = build_strategy_legs("Iron Condor", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    S = price_grid(SPOT, price_range_pct=0.4, n_points=500)
    pnl = expiration_payoff(priced, S)
    max_profit, max_loss = max_profit_loss(priced, S, pnl)
    assert not max_profit.is_unbounded
    assert not max_loss.is_unbounded
    # Max profit for an iron condor = net credit received (positive)
    cost = net_entry_cost(priced)
    assert max_profit.value == pytest.approx(-cost, abs=1.0)


# ---------------------------------------------------------------------------
# Max Profit / Max Loss: unbounded strategy
# ---------------------------------------------------------------------------


def test_long_call_max_profit_unbounded_max_loss_bounded():
    legs = build_strategy_legs("Long Call", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    S = price_grid(SPOT, price_range_pct=0.5, n_points=400)
    pnl = expiration_payoff(priced, S)
    max_profit, max_loss = max_profit_loss(priced, S, pnl)

    assert max_profit.is_unbounded
    assert max_profit.value is None
    assert not max_loss.is_unbounded
    # Max loss on a long call = premium paid (negative P&L)
    cost = net_entry_cost(priced)
    assert max_loss.value == pytest.approx(-cost, abs=1.0)


def test_short_call_max_loss_unbounded_max_profit_bounded():
    legs = build_strategy_legs("Short Call", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    S = price_grid(SPOT, price_range_pct=0.5, n_points=400)
    pnl = expiration_payoff(priced, S)
    max_profit, max_loss = max_profit_loss(priced, S, pnl)

    assert max_loss.is_unbounded
    assert max_loss.value is None
    assert not max_profit.is_unbounded
    cost = net_entry_cost(priced)  # negative (credit received)
    assert max_profit.value == pytest.approx(-cost, abs=1.0)


def test_long_put_max_profit_bounded_by_strike_going_to_zero():
    """A long put's max profit is bounded (price can't go below 0), and
    should equal (strike - 0)*100 - premium paid, achieved as S -> 0. This
    must hold even from a chart window that is zoomed in and does NOT
    itself reach all the way down to S=0 (max_profit_loss must compute the
    true S=0 value analytically, not just read the visible grid's min)."""
    legs = build_strategy_legs("Long Put", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    S = price_grid(SPOT, price_range_pct=0.3, n_points=400)  # zoomed in, does not reach S=0
    pnl = expiration_payoff(priced, S)
    max_profit, max_loss = max_profit_loss(priced, S, pnl)

    assert not max_profit.is_unbounded  # bounded because S can't go negative
    assert not max_loss.is_unbounded
    strike = legs[0].strike
    cost = net_entry_cost(priced)
    expected_max_profit = strike * 100.0 - cost
    assert max_profit.value == pytest.approx(expected_max_profit, rel=0.02)


def test_long_stock_unbounded_profit_bounded_loss():
    """Long stock: profit is unbounded as price rises without limit, but
    loss is bounded -- the worst case is the stock going to $0, capping
    the loss at the entry cost (100% loss of position value), never
    'Infinity'. This must hold even when the chart is zoomed to a window
    that doesn't itself reach S=0."""
    legs = build_strategy_legs("Long Stock", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    S = price_grid(SPOT, price_range_pct=0.3, n_points=300)  # zoomed in, does not reach S=0
    pnl = expiration_payoff(priced, S)
    max_profit, max_loss = max_profit_loss(priced, S, pnl)
    assert max_profit.is_unbounded
    assert not max_loss.is_unbounded
    cost = net_entry_cost(priced)  # positive, dollars paid for the stock
    assert max_loss.value == pytest.approx(-cost, abs=1.0)


# ---------------------------------------------------------------------------
# Position Greeks aggregation
# ---------------------------------------------------------------------------


def test_long_call_position_delta_positive_and_bounded():
    legs = build_strategy_legs("Long Call", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    greeks = position_greeks(priced, SPOT, R, Q, flat_iv_fn)
    assert 0 < greeks.delta < 100  # single ATM call, 100-share multiplier


def test_long_put_position_delta_negative():
    legs = build_strategy_legs("Long Put", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    greeks = position_greeks(priced, SPOT, R, Q, flat_iv_fn)
    assert -100 < greeks.delta < 0


def test_covered_call_delta_between_zero_and_stock_delta():
    """Covered call = long 100 shares (delta +100) + short 1 call (delta
    negative contribution) -> net delta should be positive but less than
    the pure stock position's +100."""
    legs = build_strategy_legs("Covered Call", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    greeks = position_greeks(priced, SPOT, R, Q, flat_iv_fn)
    assert 0 < greeks.delta < 100


def test_long_straddle_theta_negative_and_delta_near_zero_atm():
    legs = build_strategy_legs("Long Straddle", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    greeks = position_greeks(priced, SPOT, R, Q, flat_iv_fn)
    assert greeks.theta < 0  # long premium, time decay hurts
    assert abs(greeks.delta) < 15  # roughly delta-neutral ATM (call+put deltas ~cancel)


def test_short_straddle_theta_positive():
    legs = build_strategy_legs("Short Straddle", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    greeks = position_greeks(priced, SPOT, R, Q, flat_iv_fn)
    assert greeks.theta > 0  # short premium collects time decay


def test_stock_leg_contributes_only_delta():
    legs = [Leg("stock", +1, 1, SPOT, 0)]
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    greeks = position_greeks(priced, SPOT, R, Q, flat_iv_fn)
    assert greeks.delta == pytest.approx(100.0)
    assert greeks.gamma == 0
    assert greeks.theta == 0
    assert greeks.vega == 0
    assert greeks.rho == 0


# ---------------------------------------------------------------------------
# Net entry cost sign conventions
# ---------------------------------------------------------------------------


def test_long_call_net_cost_is_positive_debit():
    legs = build_strategy_legs("Long Call", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    assert net_entry_cost(priced) > 0


def test_short_call_net_cost_is_negative_credit():
    legs = build_strategy_legs("Short Call", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    assert net_entry_cost(priced) < 0


def test_iron_condor_net_cost_is_negative_credit():
    """A textbook iron condor (short inner strikes, long outer wings) is
    typically opened for a net credit."""
    legs = build_strategy_legs("Iron Condor", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    assert net_entry_cost(priced) < 0


# ---------------------------------------------------------------------------
# Probability of Profit
# ---------------------------------------------------------------------------


def test_pop_between_zero_and_one():
    legs = build_strategy_legs("Long Call", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    S = price_grid(SPOT, price_range_pct=1.5, n_points=1000)
    pnl = expiration_payoff(priced, S)
    pop = probability_of_profit(S, pnl, SPOT, iv=0.30, dte_days=30, r=R)
    assert 0.0 <= pop <= 1.0


def test_pop_long_call_less_than_half_when_otm_breakeven_above_spot():
    """A long ATM call must overcome its premium to become profitable, so
    its breakeven sits above spot -> POP should be well under 50%."""
    legs = build_strategy_legs("Long Call", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    S = price_grid(SPOT, price_range_pct=1.5, n_points=1000)
    pnl = expiration_payoff(priced, S)
    pop = probability_of_profit(S, pnl, SPOT, iv=0.30, dte_days=30, r=R)
    assert pop < 0.5


def test_pop_short_call_greater_than_half():
    """Mirror image: a short ATM call profits unless price rises past
    breakeven, so POP should be well over 50%."""
    legs = build_strategy_legs("Short Call", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    S = price_grid(SPOT, price_range_pct=1.5, n_points=1000)
    pnl = expiration_payoff(priced, S)
    pop = probability_of_profit(S, pnl, SPOT, iv=0.30, dte_days=30, r=R)
    assert pop > 0.5


def test_pop_zero_dte_reduces_to_certainty():
    legs = build_strategy_legs("Long Call", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    S = price_grid(SPOT, price_range_pct=0.5, n_points=500)
    pnl = expiration_payoff(priced, S)
    pop = probability_of_profit(S, pnl, SPOT, iv=0.30, dte_days=0, r=R)
    assert pop in (0.0, 1.0)


# ---------------------------------------------------------------------------
# "As of" date payoff reflects remaining extrinsic value, not linear interp
# ---------------------------------------------------------------------------


def test_asof_payoff_differs_from_linear_interpolation():
    """The 'as of' curve partway through a trade's life should NOT equal a
    naive linear blend of the day-0 P&L and the expiration P&L -- it must
    reflect genuine BSM re-pricing (remaining extrinsic value), which is
    a nonlinear function of time. We verify this by checking that the
    as-of curve, away from the money, differs meaningfully from the
    straight-line interpolation between t=0 P&L (which is 0 everywhere by
    definition, since nothing has moved yet) and expiration P&L."""
    legs = build_strategy_legs("Long Call", SPOT, 5.0, 60.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    S = price_grid(SPOT, price_range_pct=0.3, n_points=300)

    expiration_pnl = expiration_payoff(priced, S)
    halfway_days = 30.0  # halfway through a 60 DTE trade
    asof_pnl = asof_payoff(priced, S, R, Q, flat_iv_fn, SPOT, halfway_days)

    # Naive linear interpolation would predict halfway_pnl = 0.5 * expiration_pnl
    # (since day-0 P&L is identically zero everywhere by construction).
    naive_linear_pnl = 0.5 * expiration_pnl

    # The true BSM-based as-of curve should differ from the naive linear
    # blend by a non-trivial amount somewhere on the grid (extrinsic value
    # decays nonlinearly, especially near the money).
    max_abs_diff = np.max(np.abs(asof_pnl - naive_linear_pnl))
    assert max_abs_diff > 5.0  # dollars; comfortably above numerical noise


def test_asof_payoff_at_zero_days_elapsed_is_near_zero_pnl():
    """At day 0 (no time elapsed, price unchanged), P&L should be ~0
    everywhere since the position is priced the same way it was entered."""
    legs = build_strategy_legs("Long Straddle", SPOT, 5.0, 45.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    S = np.array([SPOT])
    asof_pnl = asof_payoff(priced, S, R, Q, flat_iv_fn, SPOT, days_elapsed=0.0)
    assert asof_pnl[0] == pytest.approx(0.0, abs=0.01)


def test_asof_payoff_converges_to_expiration_payoff_at_full_dte():
    """When days_elapsed == the leg's full DTE, the as-of curve should
    match the expiration curve (both reduce to intrinsic value)."""
    legs = build_strategy_legs("Bull Call Spread", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    S = price_grid(SPOT, price_range_pct=0.4, n_points=300)
    expiration_pnl = expiration_payoff(priced, S)
    asof_pnl_at_expiry = asof_payoff(priced, S, R, Q, flat_iv_fn, SPOT, days_elapsed=30.0)
    np.testing.assert_allclose(asof_pnl_at_expiry, expiration_pnl, atol=0.5)


# ---------------------------------------------------------------------------
# compute_stats bundle sanity
# ---------------------------------------------------------------------------


def test_compute_stats_bundle_consistent_with_individual_calls():
    legs = build_strategy_legs("Bull Call Spread", SPOT, 5.0, 30.0)
    priced = price_legs(legs, SPOT, R, Q, flat_iv_fn)
    S = price_grid(SPOT, price_range_pct=0.4, n_points=400)
    pnl = expiration_payoff(priced, S)

    stats = compute_stats(
        priced, S, pnl, SPOT, R, Q, flat_iv_fn, position_iv_estimate=0.30, max_dte_days=30.0
    )
    expected_cost = net_entry_cost(priced)
    expected_breakevens = find_breakevens(S, pnl)
    expected_max_profit, expected_max_loss = max_profit_loss(priced, S, pnl)

    assert stats.net_entry_cost == pytest.approx(expected_cost)
    assert stats.breakevens == expected_breakevens
    assert stats.max_profit.value == expected_max_profit.value
    assert stats.max_loss.value == expected_max_loss.value
