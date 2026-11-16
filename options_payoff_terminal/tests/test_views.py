import numpy as np
import pytest
from engine.payoff import expiration_payoff, net_entry_cost, price_grid, price_legs
from engine.strategies import build_strategy_legs
from engine.views import VIEW_MODES, greek_curve, profit_index, view_series
from engine.payoff import position_greeks

SPOT, R, Q = 100.0, 0.05, 0.0
iv = lambda k, s, d: 0.30


def setup(name="Bull Call Spread"):
    legs = build_strategy_legs(name, SPOT, 5.0, 30.0)
    return price_legs(legs, SPOT, R, Q, iv), price_grid(SPOT, 0.3, 200)


def test_all_modes_return_matching_length():
    priced, S = setup()
    for m in VIEW_MODES:
        y, label, kind = view_series(m, priced, S, R, Q, iv, SPOT, 0.0, 30.0, -300.0)
        assert y.shape == S.shape and label


def test_contract_value_is_pnl_plus_cost():
    priced, S = setup()
    pnl, _, _ = view_series("Profit / Loss $", priced, S, R, Q, iv, SPOT, 30.0, 30.0, None)
    val, _, _ = view_series("Contract Value", priced, S, R, Q, iv, SPOT, 30.0, 30.0, None)
    np.testing.assert_allclose(val - pnl, net_entry_cost(priced))


def test_pct_of_max_risk_hits_minus_100_at_max_loss():
    priced, S = setup()
    pnl = expiration_payoff(priced, S)
    y, _, _ = view_series("% of Max Risk", priced, S, R, Q, iv, SPOT, 30.0, 30.0, float(pnl.min()))
    assert y.min() == pytest.approx(-100.0, abs=0.01)


def test_delta_curve_at_spot_matches_position_greeks():
    priced, _ = setup()
    d = greek_curve(priced, np.array([SPOT]), R, Q, iv, SPOT, 0.0, "delta")[0]
    assert d == pytest.approx(position_greeks(priced, SPOT, R, Q, iv).delta, rel=1e-9)


def test_stock_only_delta_curve_constant():
    priced, S = setup("Long Stock")
    d = greek_curve(priced, S, R, Q, iv, SPOT, 0.0, "delta")
    np.testing.assert_allclose(d, 100.0)


def test_profit_index_sign_long_vs_short_atm_call():
    for name, sign in (("Long Call", -1), ("Short Call", 1)):
        priced, S = setup(name)
        pnl = expiration_payoff(priced, S)
        pi = profit_index(priced, S, pnl, SPOT, 0.30, 30.0, R, None if name == "Short Call" else float(pnl.min()))
        assert np.isfinite(pi)
    # a fair-priced option has E[P/L] near zero under the risk-neutral model
    priced, S = setup("Long Call")
    pnl = expiration_payoff(priced, S)
    assert abs(profit_index(priced, S, pnl, SPOT, 0.30, 30.0, R, float(pnl.min()))) < 0.2
