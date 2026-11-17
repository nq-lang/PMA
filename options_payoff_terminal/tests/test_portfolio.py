import numpy as np
import pytest

from engine.portfolio import Holding, Ledger
from engine import portfolio_risk as pr


def stock(sym="AAPL", beta=1.2):
    return Holding(sym, "equity", sym, 0, 0, beta=beta, sleeve="tech")


def test_equity_roundtrip_pnl_and_nlv():
    L = Ledger(cash=100_000)
    L.apply_fill(stock(), 100, 150.0, fee=1.0)
    assert L.cash == pytest.approx(100_000 - 15_000 - 1)
    L.apply_tick("AAPL", 160.0)
    assert L.unrealized == 1000.0
    assert L.nlv == pytest.approx(100_000 - 1 + 1000)      # only fees + unrealized move NLV
    r = L.apply_fill(stock(), -100, 160.0, fee=1.0)
    assert r == 1000.0 and not L.holdings and L.realized == 1000.0
    assert L.nlv == pytest.approx(100_000 + 1000 - 2)


def test_average_up_reduce_and_flip():
    L = Ledger(cash=0)
    L.apply_fill(stock(), 100, 10.0)
    L.apply_fill(stock(), 100, 20.0)
    assert L.holdings["AAPL"].avg_cost == 15.0
    assert L.apply_fill(stock(), -50, 20.0) == 250.0
    r = L.apply_fill(stock(), -250, 30.0)            # closes 150, flips short 100
    assert r == 150 * 15.0 and L.holdings["AAPL"].qty == -100 and L.holdings["AAPL"].avg_cost == 30.0


def test_futures_cash_only_on_realized():
    L = Ledger(cash=50_000)
    es = Holding("ES", "future", "ES", 0, 0, multiplier=50.0)
    L.apply_fill(es, 2, 5000.0, fee=5.0)
    assert L.cash == 50_000 - 5
    L.apply_tick("ES", 5010.0)
    assert L.nlv == pytest.approx(50_000 - 5 + 1000)
    L.apply_fill(es, -2, 5010.0, fee=5.0)
    assert L.cash == pytest.approx(50_000 - 10 + 1000) and L.realized == 1000.0
    assert L.nlv == pytest.approx(L.cash)


def test_option_expiry_and_dividend_and_borrow():
    L = Ledger(cash=10_000)
    call = Holding("AAPL 150C", "option", "AAPL", 0, 0, multiplier=100.0, strike=150.0, right="call")
    L.apply_fill(call, 1, 5.0)                       # pay 500
    r = L.expire_option("AAPL 150C", 160.0)          # intrinsic 10 -> +500 pnl
    assert r == 500.0 and L.cash == pytest.approx(10_000 + 500)
    L.apply_fill(stock("XYZ"), -100, 50.0)
    L.borrow_rates["XYZ"] = 0.36
    assert L.apply_dividend("XYZ", 0.5) == -50.0
    assert L.accrue_carry(10) == pytest.approx(5000 * 0.36 * 10 / 365)


def test_margin_groups_beta_and_events():
    L = Ledger(cash=100_000)
    seen = []
    L.subscribe(lambda s: seen.append(s))
    L.apply_fill(stock(), 100, 100.0)
    L.apply_fill(Holding("ES", "future", "ES", 0, 0, multiplier=50.0), 1, 5000.0)
    init, maint = L.margin()
    assert init == pytest.approx(5000 + 22000) and maint == pytest.approx(2500 + 20000)
    assert L.beta_weighted_exposure() == pytest.approx(100 * 100 * 1.2 + 5000 * 50 * 1.0)
    g = L.group_by("asset_class")
    assert set(g) == {"equity", "future"}
    assert L.apply_tick("AAPL", 100.0) == set()      # unchanged price -> no event
    assert L.apply_tick("AAPL", 101.0) == {"AAPL"} and seen[-1] == {"AAPL"}
    with pytest.raises(ValueError):
        L.group_by("nonsense")


def test_risk_metrics():
    r = np.array([0.01, -0.02, 0.015, 0.0, -0.005, 0.02])
    assert pr.max_drawdown([100, 110, 99, 105]) == pytest.approx(99 / 110 - 1)
    assert pr.cvar(r, 0.8) == pytest.approx(-0.0125)  # worst 2 of 6
    assert pr.sharpe(r) > 0 and pr.sortino(r) > pr.sharpe(r) * 0  # finite
    rng = np.random.default_rng(1)
    a = rng.normal(0, .01, 500); b = a + rng.normal(0, .002, 500)
    names, C = pr.correlation_matrix({"A": a, "B": b})
    assert C[0, 1] > 0.95
    names, cov = pr.covariance_matrix({"A": a, "B": b})
    out = pr.trade_impact(names, cov, {"A": 1e5}, {"B": 1e5}, nlv=2e5, margin_before=5e4, margin_added=1e4)
    assert out["vol_after"] > out["vol_before"] * 1.9      # correlated adds ~double vol
    assert out["cushion_after"] == 2e5 - 6e4
    assert pr.concentration({"A": 90, "B": 10})["top"] == "A"
