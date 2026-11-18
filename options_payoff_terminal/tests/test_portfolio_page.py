import numpy as np
import pytest

from ui.portfolio_page import build_demo_ledger, rows_for, step_ticks


def test_demo_ledger_is_consistent():
    L = build_demo_ledger()
    assert set(g.asset_class for g in L.holdings.values()) == {"equity", "etf", "option", "future"}
    s = L.summary()
    assert s["nlv"] > 0 and s["init_margin"] >= s["maint_margin"] > 0
    assert sum(r["mv"] for r in rows_for(L, "(none)")) == pytest.approx(sum(r["mv"] for r in rows_for(L, "asset_class")))


def test_ticks_emit_only_changed_and_nlv_tracks():
    L = build_demo_ledger()
    seen = []
    L.subscribe(seen.append)
    before = L.nlv
    changed = step_ticks(L, np.random.default_rng(3))
    assert changed and all(s <= changed for s in seen)
    assert L.nlv != before


def test_money_format():
    from ui.portfolio_page import money
    assert money(-69331.2) == "-$69,331" and money(1234.5, 2) == "$1,234.50"


def test_thread_rows_demo_wheel():
    from ui.portfolio_page import demo_fills, thread_rows
    (r,) = thread_rows(demo_fills(), "2026-11-17", {("stock",): 50.0})
    assert r["name"] == "DEMO · Covered call" and r["rolls"] == 1 and r["basis"] == "46.00"
