import pytest

from engine.lifecycle import Fill, build_threads, classify


def F(ts, kind, qty, price, strike=None, expiry=None, note="", fee=0.0, und="XYZ"):
    return Fill(ts, und, kind, qty, price, strike, expiry, fee, note)


def wheel():
    return [
        F("2026-01-05", "put", -1, 2.00, 50, "2026-01-30"),                      # sell CSP, +200
        F("2026-01-30", "put", 1, 0.0, 50, "2026-01-30", "assigned"),            # assigned
        F("2026-01-30", "stock", 100, 50.0, note="assigned"),                    # -5000
        F("2026-02-02", "call", -1, 1.50, 52, "2026-02-27"),                     # covered call +150
        F("2026-02-25", "call", 1, 2.50, 52, "2026-02-27"),                      # BTC -250 \ roll
        F("2026-02-25", "call", -1, 3.00, 54, "2026-03-20"),                     # STO +300 /
    ]


def test_wheel_thread_basis_and_roll():
    (t,) = build_threads(wheel())
    assert t.was_wheel and t.end is None and t.archetype == "Covered call"
    assert t.shares == 100
    # (5000 stock outlay - (200 + 150 - 250 + 300) option credits) / 100
    assert t.adjusted_cost_basis() == pytest.approx((5000 - 400) / 100)
    assert len(t.rolls) == 1
    r = t.rolls[0]
    assert (r.from_leg, r.to_leg) == (("call", 52, "2026-02-27"), ("call", 54, "2026-03-20"))
    assert r.net_cash == pytest.approx(50.0)                                      # +0.50/sh credit roll


def test_annualized_return_uses_peak_capital():
    (t,) = build_threads(wheel())
    assert t.peak_capital == pytest.approx(5000)                                  # CSP collateral == stock cost
    assert t.net_pnl() == pytest.approx(100)          # +200 put, -100 closed 52C; open 54C marked at cost
    ar = t.annualized_return(as_of="2026-03-06", marks={("stock",): 50.0})
    days = (__import__("datetime").date(2026, 3, 6) - __import__("datetime").date(2026, 1, 5)).days
    assert ar == pytest.approx(100 / 5000 * 365 / days)
    # 54C marked 1.00 vs sold 3.00 -> +200 unrealized
    assert t.net_pnl({("call", 54, "2026-03-20"): 1.0}) == pytest.approx(300)


def test_thread_closes_when_flat_and_new_one_starts():
    fills = wheel() + [
        F("2026-03-20", "call", 1, 0.0, 54, "2026-03-20", "expired"),
        F("2026-03-20", "stock", -100, 51.0),
        F("2026-04-01", "put", -1, 1.0, 49, "2026-04-17"),
    ]
    t1, t2 = build_threads(fills)
    assert t1.end == "2026-03-20" and t1.archetype == "Wheel (closed)"
    assert t1.realized == pytest.approx(400 + 100)                                # premium + stock gain
    assert t2.start == "2026-04-01" and t2.archetype == "Cash-secured put"


def test_classify_archetypes():
    S = ("stock",)
    assert classify({S: [100, 50], ("call", 55, "x"): [-1, 1]}) == "Covered call"
    assert classify({S: [200, 50], ("call", 55, "x"): [-2, 1], ("put", 45, "x"): [2, 1]}) == "Protective collar"
    assert classify({S: [100, 50], ("put", 45, "x"): [1, 1]}) == "Protective put"
    assert classify({("put", 45, "x"): [-1, 1]}) == "Cash-secured put"
    assert classify({S: [50, 10]}) == "Custom"


def test_independent_underlyings_and_short_stock_flip_pnl():
    fills = [F("2026-01-02", "stock", 100, 10, und="A"), F("2026-01-03", "stock", -100, 12, und="A"),
             F("2026-01-02", "stock", 10, 5, und="B")]
    ta, tb = build_threads(fills)
    assert ta.underlying == "A" and ta.end == "2026-01-03" and ta.realized == 200
    assert tb.underlying == "B" and tb.end is None
