import numpy as np
import pytest

from engine import futures as f

ES, NQ, ZN, CL = (f.get_spec(s) for s in ("ES", "NQ", "ZN", "CL"))


def test_tick_values_exact():
    assert ES.tick_value == 12.5 and NQ.tick_value == 5.0
    assert ZN.tick_value == pytest.approx(15.625) and CL.tick_value == 10.0
    assert f.get_spec("mes").tick_value == 1.25


def test_pnl_long_short_and_per_point():
    long = f.FuturesPosition(ES, 2, 5000.0)
    assert long.pnl(5010.0) == 1000.0 and long.dollars_per_point == 100 and long.dollars_per_tick == 25
    assert f.FuturesPosition(ES, -1, 5000.0).pnl(4990.0) == 500.0


def test_breakeven_with_fees():
    p = f.FuturesPosition(ES, 1, 5000.0, fee_per_side=2.5)
    assert p.breakeven() == pytest.approx(5000.1)
    assert p.pnl(p.breakeven(), include_fees=True) == pytest.approx(0, abs=1e-9)
    assert f.FuturesPosition(ES, -1, 5000.0, 2.5).breakeven() == pytest.approx(4999.9)


def test_liquidation_and_drawdown_levels():
    p = f.FuturesPosition(ES, 1, 5000.0)
    # equity 30k, maint 20k -> 10k cushion = 200 pts
    assert p.liquidation_price(30000) == pytest.approx(4800.0)
    assert f.FuturesPosition(ES, -1, 5000.0).liquidation_price(30000) == pytest.approx(5200.0)
    assert p.drawdown_price(2500) == pytest.approx(4950.0)


def test_scaling_average_entry():
    p = f.scale(f.FuturesPosition(ES, 1, 5000.0), [(1, 4980.0), (2, 4960.0)])
    assert p.qty == 4 and p.entry == pytest.approx((5000 + 4980 + 2 * 4960) / 4)
    r = f.scale(p, [(-2, 5000.0)])
    assert r.qty == 2 and r.entry == p.entry
    flip = f.scale(f.FuturesPosition(ES, 1, 5000.0), [(-3, 5010.0)])
    assert flip.qty == -2 and flip.entry == 5010.0


def test_bracket():
    b = f.bracket(f.FuturesPosition(NQ, 1, 20000.0), stop=19950.0, target=20150.0)
    assert (b.risk_dollars, b.reward_dollars, b.risk_reward) == (1000.0, 3000.0, 3.0)
    with pytest.raises(ValueError):
        f.bracket(f.FuturesPosition(NQ, 1, 20000.0), stop=20010.0, target=20150.0)


def test_roll_and_calendar():
    ra = f.roll_analysis(ES, 5000.0, 5040.0, 91, spot=4990.0, r=0.05, q=0.013, days_front=30)
    assert ra.spread == 40.0 and ra.spread_dollars == 2000.0 and ra.fair_spread > 0
    assert f.calendar_spread_pnl(ES, 2, 40.0, 45.0) == 500.0


def test_black76_parity_and_composite():
    F, K, r, s, T = 5000.0, 5000.0, 0.04, 0.2, 0.25
    c, p = (f.black76_price(F, K, r, s, T, k) for k in ("call", "put"))
    assert c - p == pytest.approx(np.exp(-r * T) * (F - K), abs=1e-9)
    pos = f.FuturesPosition(ES, 1, 5000.0)
    g = np.linspace(4800, 5200, 5)
    opt = [dict(kind="put", strike=4900.0, qty=1, iv=0.2, T=0.0, entry=20.0)]
    comp = f.futures_option_composite_pnl(pos, opt, g)
    assert comp[0] == pytest.approx(pos.pnl(4800.0) + (100 - 20) * 50)  # protective put floor
    assert comp[-1] == pytest.approx(pos.pnl(5200.0) - 20 * 50)


def test_margin_update_and_unknown():
    with pytest.raises(KeyError):
        f.get_spec("XX")
    with pytest.raises(ValueError):
        f.update_margins("ES", 100, 200, "x")
