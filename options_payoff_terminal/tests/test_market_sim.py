"""
tests/test_market_sim.py

Tests for engine/market_sim.py: determinism/reproducibility given the same
ticker (or explicit seed), and internal consistency of the fabricated
snapshot fields (day range brackets spot, 52-week range brackets day
range, etc.) per spec §5.1.
"""

from __future__ import annotations

from engine.market_sim import MarketSimulator


def test_same_ticker_reproducible_snapshot():
    snap1 = MarketSimulator("TSLA").snapshot()
    snap2 = MarketSimulator("TSLA").snapshot()
    assert snap1 == snap2


def test_ticker_case_and_whitespace_insensitive():
    snap1 = MarketSimulator("tsla").snapshot()
    snap2 = MarketSimulator("  TSLA  ").snapshot()
    assert snap1 == snap2


def test_different_tickers_generally_differ():
    snap_a = MarketSimulator("AAPL").snapshot()
    snap_b = MarketSimulator("TSLA").snapshot()
    assert snap_a.price != snap_b.price


def test_explicit_seed_overrides_ticker_hash():
    snap1 = MarketSimulator("TSLA", seed=42).snapshot()
    snap2 = MarketSimulator("TSLA", seed=42).snapshot()
    snap3 = MarketSimulator("TSLA", seed=43).snapshot()
    assert snap1 == snap2
    assert snap1 != snap3


def test_day_range_brackets_spot():
    for ticker in ["AAPL", "TSLA", "SPY", "GME", "NVDA", "XYZ123"]:
        snap = MarketSimulator(ticker).snapshot()
        assert snap.day_low <= snap.price <= snap.day_high


def test_year_range_brackets_day_range():
    for ticker in ["AAPL", "TSLA", "SPY", "GME", "NVDA", "XYZ123"]:
        snap = MarketSimulator(ticker).snapshot()
        assert snap.year_low <= snap.day_low
        assert snap.year_high >= snap.day_high


def test_moving_averages_within_year_range():
    for ticker in ["AAPL", "TSLA", "SPY", "GME", "NVDA", "XYZ123"]:
        snap = MarketSimulator(ticker).snapshot()
        assert snap.year_low <= snap.ma_50 <= snap.year_high
        assert snap.year_low <= snap.ma_200 <= snap.year_high


def test_price_and_market_cap_positive():
    snap = MarketSimulator("MSFT").snapshot()
    assert snap.price > 0
    assert snap.market_cap > 0
    assert snap.base_iv > 0
    assert snap.risk_free_rate > 0
    assert snap.dividend_yield >= 0


def test_default_ticker_fallback_on_empty_string():
    snap = MarketSimulator("").snapshot()
    assert snap.ticker == "AAPL"


def test_implied_vol_positive_and_bounded():
    sim = MarketSimulator("SPY")
    snap = sim.snapshot()
    for strike_mult in [0.5, 0.8, 1.0, 1.2, 2.0]:
        for dte in [1, 7, 30, 90, 365]:
            iv = sim.implied_vol(snap.price * strike_mult, snap.price, dte)
            assert 0.05 <= iv <= 2.5


def test_implied_vol_deterministic():
    sim1 = MarketSimulator("SPY")
    sim2 = MarketSimulator("SPY")
    snap = sim1.snapshot()
    iv1 = sim1.implied_vol(snap.price * 1.1, snap.price, 30)
    iv2 = sim2.implied_vol(snap.price * 1.1, snap.price, 30)
    assert iv1 == iv2


def test_implied_vol_skew_shape_otm_puts_richer_than_atm():
    """Classic equity skew: downside (OTM put side) strikes should carry
    higher IV than ATM, all else equal — a smoke test of the skew shape,
    not a claim about real markets."""
    sim = MarketSimulator("SPY")
    snap = sim.snapshot()
    iv_atm = sim.implied_vol(snap.price, snap.price, 30)
    iv_otm_put_side = sim.implied_vol(snap.price * 0.85, snap.price, 30)
    assert iv_otm_put_side > iv_atm


def test_flow_tape_deterministic_and_consistent():
    sim = MarketSimulator("TSLA")
    snap = sim.snapshot()
    a, b = sim.flow_tape(snap, n=8), MarketSimulator("TSLA").flow_tape(snap, n=8)
    assert a == b and len(a) == 8
    assert all(r.option_type in ("CALL", "PUT") and r.price > 0 and r.size > 0 for r in a)
    assert sim.snapshot() == snap  # flow draws never perturb the snapshot
