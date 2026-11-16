"""Regression guards for the BSM kernel (ndtr-based fast path)."""
import numpy as np
from scipy.stats import norm

from engine.pricing import bsm_greeks, bsm_price

S = np.linspace(50, 900, 400)


def test_put_call_parity():
    r, q, sg, T, K = 0.045, 0.012, 0.3, 0.4, 500.0
    c = bsm_price(S, K, r, q, sg, T, "call")
    p = bsm_price(S, K, r, q, sg, T, "put")
    assert np.allclose(c - p, S * np.exp(-q * T) - K * np.exp(-r * T), atol=1e-9)


def test_matches_scipy_stats_reference():
    r, q, sg, T, K = 0.04, 0.01, 0.25, 0.2, 480.0
    sq = sg * np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sg**2) * T) / sq
    d2 = d1 - sq
    ref = S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    assert np.allclose(bsm_price(S, K, r, q, sg, T, "call"), ref, atol=1e-12)
    g = bsm_greeks(S, K, r, q, sg, T, "call")
    assert np.allclose(g.delta, np.exp(-q * T) * norm.cdf(d1), atol=1e-12)
    assert np.allclose(g.gamma, np.exp(-q * T) * norm.pdf(d1) / (S * sq), atol=1e-12)


def test_expiry_limit_is_intrinsic():
    assert np.allclose(bsm_price(S, 500.0, 0.04, 0.0, 0.3, 0.0, "put"), np.maximum(500 - S, 0))
