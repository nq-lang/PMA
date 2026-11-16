import numpy as np
import pytest

from engine.american import american_price, early_exercise_premium
from engine.pricing import bsm_price


def test_european_limit_call_no_dividend():
    # American call on non-dividend stock == European call
    a = american_price(100, 100, 0.05, 0.0, 0.2, 1.0, "call", steps=400)
    assert a == pytest.approx(bsm_price(100, 100, 0.05, 0.0, 0.2, 1.0, "call"), abs=5e-3)


def test_known_american_put_value():
    # S=K=100, r=5%, q=0, sigma=20%, T=1 -> ~6.09 (converged reference)
    assert american_price(100, 100, 0.05, 0.0, 0.2, 1.0, "put", steps=800) == pytest.approx(6.09, abs=0.02)


def test_put_floor_and_premium_nonneg():
    S = np.linspace(60, 140, 41)
    a = american_price(S, 100, 0.05, 0.0, 0.25, 0.5, "put", steps=200)
    assert np.all(a >= np.maximum(100 - S, 0) - 1e-12)
    assert np.all(early_exercise_premium(S, 100, 0.05, 0.0, 0.25, 0.5, "put") >= -5e-3)


def test_dividend_call_has_early_exercise_value():
    assert early_exercise_premium(150, 100, 0.02, 0.08, 0.2, 1.0, "call", steps=300) > 0.01


def test_expiry_is_intrinsic_and_array_scalar_shapes():
    assert american_price(90, 100, 0.05, 0, 0.2, 0.0, "put") == 10.0
    assert american_price(np.array([90.0, 110.0]), 100, 0.05, 0, 0.2, 0.5, "call").shape == (2,)
