"""
ui/portfolio_page.py
=====================
Portfolio page (route: /portfolio) over ``engine.portfolio``.

The book shown is a SIMULATED demo ledger with random-walk ticks, labelled
as such on the page. Real positions/quotes arrive through the data adapters
later; the page only talks to ``Ledger`` events, so swapping the feed does
not change the UI.
"""
from __future__ import annotations

import numpy as np
from nicegui import ui

from engine.portfolio import Holding, Ledger
from engine import portfolio_risk as pr
from ui.theme import GLOBAL_CSS, PALETTE

GROUPS = ["(none)", "asset_class", "underlying", "sleeve", "strategy"]
SIM_PRICES = {"AAPL": 190.0, "MSFT": 420.0, "SPY": 520.0, "QQQ": 450.0, "ES": 5200.0, "NQ": 18400.0}


def money(x: float, decimals: int = 0) -> str:
    """-$1,234 (sign before the symbol)."""
    return f"{'-' if x < 0 else ''}${abs(x):,.{decimals}f}"


def build_demo_ledger() -> Ledger:
    """Deterministic simulated book mixing all four asset classes."""
    L = Ledger(cash=250_000.0)
    L.borrow_rates["QQQ"] = 0.02
    h = Holding
    L.apply_fill(h("AAPL", "equity", "AAPL", 0, 0, beta=1.2, sleeve="Mega-cap tech", strategy="Core"), 300, 185.0, 1.0)
    L.apply_fill(h("MSFT", "equity", "MSFT", 0, 0, beta=1.1, sleeve="Mega-cap tech", strategy="Core"), 100, 410.0, 1.0)
    L.apply_fill(h("SPY", "etf", "SPY", 0, 0, beta=1.0, sleeve="Index", strategy="Hedge"), -100, 515.0, 1.0)
    L.apply_fill(h("ES", "future", "ES", 0, 0, multiplier=50.0, sleeve="Index", strategy="Directional"), 1, 5180.0, 2.5)
    L.apply_fill(h("NQ", "future", "NQ", 0, 0, multiplier=20.0, sleeve="Index", strategy="Directional"), -1, 18500.0, 2.5)
    L.apply_fill(h("AAPL 200C", "option", "AAPL", 0, 0, multiplier=100.0, strike=200.0, right="call",
                   delta=0.35, underlying_mark=190.0, beta=1.2, sleeve="Mega-cap tech",
                   strategy="Covered call", expiry="2026-12-18"), -3, 4.2, 3.0)
    for sym, px in SIM_PRICES.items():
        L.apply_tick(sym, px, underlying=sym in ("AAPL",))
    L.holdings["AAPL 200C"].mark = 4.6
    return L


def rows_for(L: Ledger, group: str) -> list[dict]:
    if group != "(none)":
        return [{"name": k, "count": g["count"], "mv": round(g["market_value"], 2),
                 "upnl": round(g["unrealized"], 2), "delta_usd": round(g["delta_notional"], 2)}
                for k, g in sorted(L.group_by(group).items())]
    return [{"name": h.symbol, "count": h.qty, "mv": round(h.market_value, 2),
             "upnl": round(h.unrealized, 2), "delta_usd": round(h.delta_notional, 2)}
            for h in L.holdings.values()]


def step_ticks(L: Ledger, rng: np.random.Generator, vol: float = 0.0008) -> set[str]:
    """One simulated tick burst: random-walk a random subset of symbols."""
    changed: set[str] = set()
    for sym in rng.choice(list(SIM_PRICES), size=3, replace=False):
        h = L.holdings.get(sym)
        if h is not None:
            px = round(h.mark * float(np.exp(rng.normal(0, vol))), 2)
            changed |= L.apply_tick(sym, px, underlying=(sym == "AAPL"))
    return changed


def build_portfolio_page() -> None:
    ui.add_head_html(f"<style>{GLOBAL_CSS}</style>")
    L = build_demo_ledger()
    rng = np.random.default_rng(7)
    state = {"group": "(none)", "running": True, "dirty": True}
    L.subscribe(lambda _s: state.__setitem__("dirty", True))

    with ui.row().classes("w-full items-center gap-4"):
        ui.label("Portfolio").classes("text-xl font-semibold")
        ui.link("Options payoff", "/")
        ui.link("Futures", "/futures")
    ui.label("SIMULATED demo book and random-walk ticks, not real positions or quotes. "
             "Margin is a simplified model.").style(f"color: {PALETTE.warning}; font-size: 12px;")

    stats = ui.row().classes("opt-panel w-full gap-6 flex-wrap")
    with ui.row().classes("w-full items-center gap-4"):
        grp = ui.select(GROUPS, value="(none)", label="Group by").classes("w-44")
        run = ui.switch("Simulate ticks", value=True)
    cols = [
        {"name": "name", "label": "Position / group", "field": "name", "align": "left"},
        {"name": "count", "label": "Qty / count", "field": "count", "align": "right", ":format": "v => v == null ? '' : Number(v).toLocaleString('en-US', {maximumFractionDigits: 2})"},
        {"name": "mv", "label": "Market value $", "field": "mv", "align": "right", ":format": "v => v == null ? '' : Number(v).toLocaleString('en-US', {maximumFractionDigits: 2})"},
        {"name": "upnl", "label": "Unrealized $", "field": "upnl", "align": "right", ":format": "v => v == null ? '' : Number(v).toLocaleString('en-US', {maximumFractionDigits: 2})"},
        {"name": "delta_usd", "label": "Delta $", "field": "delta_usd", "align": "right", ":format": "v => v == null ? '' : Number(v).toLocaleString('en-US', {maximumFractionDigits: 2})"},
    ]
    table = ui.table(columns=cols, rows=rows_for(L, "(none)"), row_key="name").classes("w-full")
    table.props("flat dense dark").style(
        "font-variant-numeric: tabular-nums; background: transparent; box-shadow: none;")
    table.add_slot("body-cell-upnl", '''
        <q-td :props="props" class="text-right"
              :style="{color: props.row.upnl >= 0 ? '%s' : '%s'}">
            {{ Number(props.row.upnl).toLocaleString('en-US', {maximumFractionDigits: 2}) }}
        </q-td>''' % (PALETTE.profit_green, PALETTE.loss_red))

    def stat(label, value, color=None):
        with ui.column().classes("gap-0"):
            ui.label(label).style(f"color: {PALETTE.text_muted}; font-size: 11px;")
            ui.label(value).style("font-variant-numeric: tabular-nums; font-size: 16px;"
                                  + (f"color: {color};" if color else ""))

    def render() -> None:
        s = L.summary()
        stats.clear()
        with stats:
            stat("Net liquidation", money(s["nlv"]))
            stat("Unrealized P&L", money(s["unrealized"]),
                 PALETTE.profit_green if s["unrealized"] >= 0 else PALETTE.loss_red)
            stat("Realized", money(s["realized"]))
            stat("Beta-wtd exposure", money(s["beta_weighted"]))
            stat("Init / Maint margin", f"{money(s['init_margin'])} / {money(s['maint_margin'])}")
            stat("Excess liquidity", money(s["excess_liquidity"]),
                 PALETTE.loss_red if s["excess_liquidity"] < 0 else None)
            util = s["margin_utilization"]
            stat("Margin utilization", f"{util:.0%}", PALETTE.loss_red if util > 0.8 else None)
        table.rows = rows_for(L, state["group"])
        table.update()

    def tick() -> None:
        if run.value:
            step_ticks(L, rng)
        if state["dirty"]:           # one re-render per burst, not per event
            state["dirty"] = False
            render()

    def on_group(e) -> None:
        state["group"] = grp.value
        state["dirty"] = True

    grp.on_value_change(on_group)
    render()
    ui.timer(1.0, tick)
