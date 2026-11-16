"""
tests/test_pricing.py

Unit tests for engine/pricing.py:
- BSM price sanity checks against known/independently-computable reference values
- Put-call parity
- Greek sign checks (e.g., long call delta in (0,1))
- Greeks cross-checked against finite differences
- Expiration (T->0) limit behavior
"""

from __future__ import annotations

import numpy as np
import pytest

from engine.pricing import bsm_greeks, bsm_price, d1_d2, intrinsic_value


# ---------------------------------------------------------------------------
# Reference-value sanity checks
# ---------------------------------------------------------------------------


def test_atm_call_put_price_positive_and_reasonable():
    """A 1-year ATM option with 20% vol should have a price that's a
    plausible fraction of spot (textbook ballpark: ATM straddle ~ 0.8 * S *
    sigma * sqrt(T) for small r,q). Loose bounds only — this just guards
    against gross unit errors (e.g., forgetting to convert % to decimal)."""
    S, K, r, q, sigma, T = 100.0, 100.0, 0.05, 0.0, 0.20, 1.0
    call = bsm_price(S, K, r, q, sigma, T, "call")
    put = bsm_price(S, K, r, q, sigma, T, "put")

    assert 5.0 < call < 15.0
    assert 3.0 < put < 15.0


def test_known_reference_value_hull_style():
    """Classic textbook example (Hull-style parameters):
    S=42, K=40, r=10%, sigma=20%, T=0.5, q=0 -> call ~= 4.76, put ~= 0.81
    (Hull, 'Options, Futures, and Other Derivatives', worked BSM example).
    """
    S, K, r, q, sigma, T = 42.0, 40.0, 0.10, 0.0, 0.20, 0.5
    call = bsm_price(S, K, r, q, sigma, T, "call")
    put = bsm_price(S, K, r, q, sigma, T, "put")

    assert call == pytest.approx(4.759, abs=0.01)
    assert put == pytest.approx(0.809, abs=0.01)


def test_deep_itm_call_converges_to_intrinsic_minus_discount():
    """A very deep ITM call with tiny vol should be close to S - K*exp(-rT)."""
    S, K, r, q, sigma, T = 200.0, 50.0, 0.03, 0.0, 0.05, 1.0
    call = bsm_price(S, K, r, q, sigma, T, "call")
    expected = S - K * np.exp(-r * T)
    assert call == pytest.approx(expected, rel=0.01)


def test_deep_otm_option_near_zero():
    S, K, r, q, sigma, T = 100.0, 300.0, 0.03, 0.0, 0.15, 0.25
    call = bsm_price(S, K, r, q, sigma, T, "call")
    assert call < 0.01


# ---------------------------------------------------------------------------
# Put-call parity: C - P = S*e^-qT - K*e^-rT
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "S,K,r,q,sigma,T",
    [
        (100.0, 100.0, 0.05, 0.0, 0.25, 1.0),
        (150.0, 130.0, 0.03, 0.02, 0.40, 0.5),
        (55.0, 60.0, 0.01, 0.00, 0.60, 2.0),
        (280.0, 300.0, 0.045, 0.01, 0.635, 30 / 365),
    ],
)
def test_put_call_parity(S, K, r, q, sigma, T):
    call = bsm_price(S, K, r, q, sigma, T, "call")
    put = bsm_price(S, K, r, q, sigma, T, "put")
    lhs = call - put
    rhs = S * np.exp(-q * T) - K * np.exp(-r * T)
    assert lhs == pytest.approx(rhs, abs=1e-6)


def test_put_call_parity_vectorized_over_price_grid():
    """Parity must hold pointwise across an entire price grid (as used by
    the payoff chart), not just at a single spot value."""
    S = np.linspace(50, 250, 401)
    K, r, q, sigma, T = 150.0, 0.04, 0.015, 0.30, 0.75
    call = bsm_price(S, K, r, q, sigma, T, "call")
    put = bsm_price(S, K, r, q, sigma, T, "put")
    lhs = call - put
    rhs = S * np.exp(-q * T) - K * np.exp(-r * T)
    np.testing.assert_allclose(lhs, rhs, atol=1e-6)


# ---------------------------------------------------------------------------
# Expiration (T -> 0) limit: price collapses to intrinsic value
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("option_type", ["call", "put"])
def test_price_at_expiration_equals_intrinsic(option_type):
    S = np.array([80.0, 100.0, 100.0, 120.0])
    K = 100.0
    r, q, sigma = 0.05, 0.0, 0.30
    T = 0.0  # exactly at expiration
    price = bsm_price(S, K, r, q, sigma, T, option_type)
    expected = intrinsic_value(S, K, option_type)
    np.testing.assert_allclose(price, expected, atol=1e-9)


def test_price_never_negative_near_expiration_edge_cases():
    S = np.linspace(1, 500, 200)
    K = 250.0
    price = bsm_price(S, K, r=0.05, q=0.0, sigma=0.5, T=1e-9, option_type="put")
    assert np.all(price >= 0.0)


# ---------------------------------------------------------------------------
# Greek sign / bounds checks
# ---------------------------------------------------------------------------


def test_long_call_delta_bounds():
    S = np.linspace(50, 200, 100)
    g = bsm_greeks(S, 100.0, 0.05, 0.0, 0.3, 0.5, "call")
    assert np.all(g.delta > 0.0) and np.all(g.delta < 1.0)
    # Delta should be increasing in S (monotonic) for a call.
    assert np.all(np.diff(g.delta) >= -1e-9)


def test_long_put_delta_bounds():
    S = np.linspace(50, 200, 100)
    g = bsm_greeks(S, 100.0, 0.05, 0.0, 0.3, 0.5, "put")
    assert np.all(g.delta > -1.0) and np.all(g.delta < 0.0)
    # Delta should be increasing in S (less negative as S rises) for a put.
    assert np.all(np.diff(g.delta) >= -1e-9)


def test_gamma_positive_for_calls_and_puts():
    S = np.linspace(50, 200, 100)
    gc = bsm_greeks(S, 100.0, 0.05, 0.0, 0.3, 0.5, "call")
    gp = bsm_greeks(S, 100.0, 0.05, 0.0, 0.3, 0.5, "put")
    assert np.all(gc.gamma >= 0.0)
    assert np.all(gp.gamma >= 0.0)
    # Gamma for calls and puts at the same strike/vol/T must be identical.
    np.testing.assert_allclose(gc.gamma, gp.gamma, atol=1e-12)


def test_vega_positive_and_equal_for_calls_and_puts():
    S = np.linspace(50, 200, 100)
    gc = bsm_greeks(S, 100.0, 0.05, 0.0, 0.3, 0.5, "call")
    gp = bsm_greeks(S, 100.0, 0.05, 0.0, 0.3, 0.5, "put")
    assert np.all(gc.vega >= 0.0)
    np.testing.assert_allclose(gc.vega, gp.vega, atol=1e-12)


def test_long_call_theta_typically_negative_atm():
    """An ATM long call with meaningful time left should have negative
    theta (time decay hurts a long option holder)."""
    g = bsm_greeks(100.0, 100.0, 0.05, 0.0, 0.3, 0.5, "call")
    assert g.theta < 0.0


def test_rho_sign_call_vs_put():
    """A long call should have positive rho; a long put negative rho
    (higher rates help calls, hurt puts, all else equal)."""
    gc = bsm_greeks(100.0, 100.0, 0.05, 0.0, 0.3, 1.0, "call")
    gp = bsm_greeks(100.0, 100.0, 0.05, 0.0, 0.3, 1.0, "put")
    assert gc.rho > 0.0
    assert gp.rho < 0.0


def test_greeks_at_expiration_collapse_correctly():
    S = np.array([80.0, 120.0])
    K = 100.0
    g_call = bsm_greeks(S, K, 0.05, 0.0, 0.3, 0.0, "call")
    np.testing.assert_allclose(g_call.delta, [0.0, 1.0])
    np.testing.assert_allclose(g_call.gamma, [0.0, 0.0])
    np.testing.assert_allclose(g_call.vega, [0.0, 0.0])
    np.testing.assert_allclose(g_call.theta, [0.0, 0.0])
    np.testing.assert_allclose(g_call.rho, [0.0, 0.0])

    g_put = bsm_greeks(S, K, 0.05, 0.0, 0.3, 0.0, "put")
    np.testing.assert_allclose(g_put.delta, [-1.0, 0.0])


# ---------------------------------------------------------------------------
# Analytic Greeks cross-checked against finite differences
# ---------------------------------------------------------------------------


def test_delta_matches_finite_difference():
    S, K, r, q, sigma, T = 105.0, 100.0, 0.04, 0.01, 0.35, 0.6
    h = 1e-4
    for option_type in ("call", "put"):
        price_up = bsm_price(S + h, K, r, q, sigma, T, option_type)
        price_down = bsm_price(S - h, K, r, q, sigma, T, option_type)
        fd_delta = (price_up - price_down) / (2 * h)
        analytic = bsm_greeks(S, K, r, q, sigma, T, option_type).delta
        assert analytic == pytest.approx(fd_delta, abs=1e-4)


def test_gamma_matches_finite_difference():
    S, K, r, q, sigma, T = 105.0, 100.0, 0.04, 0.01, 0.35, 0.6
    h = 1e-2
    for option_type in ("call", "put"):
        price_up = bsm_price(S + h, K, r, q, sigma, T, option_type)
        price_mid = bsm_price(S, K, r, q, sigma, T, option_type)
        price_down = bsm_price(S - h, K, r, q, sigma, T, option_type)
        fd_gamma = (price_up - 2 * price_mid + price_down) / (h**2)
        analytic = bsm_greeks(S, K, r, q, sigma, T, option_type).gamma
        assert analytic == pytest.approx(fd_gamma, abs=1e-3)


def test_vega_matches_finite_difference():
    S, K, r, q, sigma, T = 105.0, 100.0, 0.04, 0.01, 0.35, 0.6
    h = 1e-4  # bump in raw sigma units
    for option_type in ("call", "put"):
        price_up = bsm_price(S, K, r, q, sigma + h, T, option_type)
        price_down = bsm_price(S, K, r, q, sigma - h, T, option_type)
        fd_vega_per_unit = (price_up - price_down) / (2 * h)
        fd_vega_per_point = fd_vega_per_unit * 0.01  # convert to "per 1 vol point"
        analytic = bsm_greeks(S, K, r, q, sigma, T, option_type).vega
        assert analytic == pytest.approx(fd_vega_per_point, abs=1e-4)


def test_theta_matches_finite_difference():
    """Theta is the sensitivity of price to *calendar time passing*, i.e.
    time-to-expiration T shrinking. So theta_per_year = d(price)/d(T) --
    NOT its negative -- because as T decreases (time passes), price
    decreases (for a long option), giving d(price)/dT > 0 and thus a
    *negative* theta only once we express it as decay-per-day-of-time-
    -passing. Concretely: theta_per_year := (price(T) - price(T-h)) / h,
    i.e. the ordinary forward difference of price with respect to T; this
    is positive for a long option (less time = less value = price(T-h) <
    price(T)), and dividing by 365 gives "dollars gained per extra day of
    time remaining" -- so we negate it to get the conventional "dollars
    lost per day of time decay" sign used throughout this codebase.
    """
    S, K, r, q, sigma, T = 105.0, 100.0, 0.04, 0.01, 0.35, 0.6
    h = 1e-5  # bump in years
    for option_type in ("call", "put"):
        price_at_T = bsm_price(S, K, r, q, sigma, T, option_type)
        price_at_T_minus_h = bsm_price(S, K, r, q, sigma, T - h, option_type)
        # d(price)/dT, forward difference: positive for a long option since
        # less time remaining (T-h) is worth less than more time (T).
        dprice_dT = (price_at_T - price_at_T_minus_h) / h
        # Theta (decay per day) is the negative of d(price)/dT, converted
        # from per-year to per-day.
        fd_theta_per_day = -dprice_dT / 365.0
        analytic = bsm_greeks(S, K, r, q, sigma, T, option_type).theta
        assert analytic == pytest.approx(fd_theta_per_day, abs=1e-3)


def test_rho_matches_finite_difference():
    S, K, r, q, sigma, T = 105.0, 100.0, 0.04, 0.01, 0.35, 0.6
    h = 1e-4
    for option_type in ("call", "put"):
        price_up = bsm_price(S, K, r + h, q, sigma, T, option_type)
        price_down = bsm_price(S, K, r - h, q, sigma, T, option_type)
        fd_rho_per_unit = (price_up - price_down) / (2 * h)
        fd_rho_per_point = fd_rho_per_unit * 0.01
        analytic = bsm_greeks(S, K, r, q, sigma, T, option_type).rho
        assert analytic == pytest.approx(fd_rho_per_point, abs=1e-4)


# ---------------------------------------------------------------------------
# d1/d2 helper sanity
# ---------------------------------------------------------------------------


def test_d1_greater_than_d2():
    d1, d2 = d1_d2(100.0, 100.0, 0.05, 0.0, 0.25, 1.0)
    assert d1 > d2


def test_intrinsic_value_shapes():
    S = np.array([90.0, 100.0, 110.0])
    K = 100.0
    call_intrinsic = intrinsic_value(S, K, "call")
    put_intrinsic = intrinsic_value(S, K, "put")
    np.testing.assert_allclose(call_intrinsic, [0.0, 0.0, 10.0])
    np.testing.assert_allclose(put_intrinsic, [10.0, 0.0, 0.0])


def test_invalid_option_type_raises():
    with pytest.raises(ValueError):
        bsm_price(100.0, 100.0, 0.05, 0.0, 0.2, 1.0, "banana")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        bsm_greeks(100.0, 100.0, 0.05, 0.0, 0.2, 1.0, "banana")  # type: ignore[arg-type]
