import numpy as np
import pytest

from engine.payoff import leg_entry_price, leg_price_at
from engine.pricing import bsm_price, exercise_style, option_price
from engine.strategies import Leg

S = np.linspace(60, 140, 21)


def test_default_is_european_and_scoped():
    assert np.allclose(option_price(S, 100, 0.05, 0.0, 0.3, 0.5, "put"), bsm_price(S, 100, 0.05, 0.0, 0.3, 0.5, "put"))
    with exercise_style("american"):
        am = option_price(S, 100, 0.05, 0.0, 0.3, 0.5, "put")
    assert np.all(am >= bsm_price(S, 100, 0.05, 0.0, 0.3, 0.5, "put") - 5e-3)  # 80-step tree error and am[0] > bsm_price(60, 100, 0.05, 0.0, 0.3, 0.5, "put")
    assert np.allclose(option_price(S, 100, 0.05, 0.0, 0.3, 0.5, "put"), bsm_price(S, 100, 0.05, 0.0, 0.3, 0.5, "put"))  # restored


def test_call_no_dividend_fast_path_exact():
    with exercise_style("american"):
        assert np.array_equal(option_price(S, 100, 0.05, 0.0, 0.3, 0.5, "call"), bsm_price(S, 100, 0.05, 0.0, 0.3, 0.5, "call"))


def test_payoff_layer_honours_style():
    leg = Leg("put", 1, 1, 100.0, 30.0)
    eu = leg_entry_price(leg, 80.0, 0.3, 0.05, 0.0)
    with exercise_style("american"):
        am = leg_entry_price(leg, 80.0, 0.3, 0.05, 0.0)
        curve = leg_price_at(leg, S, 0.05, 0.0, 0.3, 10.0)
    assert am > eu and curve.shape == S.shape


def test_invalid_style():
    with pytest.raises(ValueError):
        with exercise_style("bermudan"):
            pass
