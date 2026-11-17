import numpy as np
import pytest

from ui.futures_page import _chart_options, compute_view


def test_compute_view_es_long():
    v = compute_view("ES", 1, 5000.0, 5010.0, 2.5, 30000.0, 4980.0, 5060.0)
    assert v["unrealized"] == 500.0
    assert v["breakeven"] == pytest.approx(5000.1)
    assert v["liquidation"] == pytest.approx(4800.0)
    assert v["bracket"].risk_reward == pytest.approx(3.0)
    assert np.all(np.diff(v["grid"]) >= 0) and len(v["grid"]) == len(v["pnl"])
    opts = _chart_options(v, 5010.0, 4980.0, 5060.0)
    assert len(opts["series"][0]["markLine"]["data"]) == 6


def test_compute_view_flat_and_bad_bracket():
    v = compute_view("NQ", 0, 20000.0, 20000.0, 2.0, 50000.0, 19900.0, 20100.0)
    assert v["unrealized"] == 0.0 and v["liquidation"] is None and v["bracket"] is None
    v2 = compute_view("NQ", 1, 20000.0, 20000.0, 2.0, 50000.0, 20100.0, 20200.0)  # stop above entry
    assert v2["bracket"] is None
