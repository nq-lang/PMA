"""
ui/layout.py
============
Assembles the terminal page around one `AppState`.

Architecture rule (fixes an earlier bug where a mouse-drag on a slider broke,
because refresh() destroyed and rebuilt the slider mid-drag): **interactive
controls are created ONCE and never rebuilt**. `refresh()` only (a) updates the
chart in place, (b) rebuilds display-only regions (header stats, ruler html,
positions list, profit table) and (c) updates label text.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
from nicegui import ui

from engine.market_sim import MarketSimulator, UnderlyingSnapshot
from engine.payoff import (
    asof_payoff, compute_stats, expiration_payoff, find_breakevens, price_grid, price_legs,
)
from engine.strategies import STRATEGY_GROUPS, Leg, build_strategy_legs
from engine.views import VIEW_MODES, greek_curve, profit_index, view_series
from ui import insights
from ui.chart import build_payoff_chart_options, hover_texts
from ui.components import flow_row, greeks_strip, key_stats_bar, positions_sidebar, snapshot_header
from ui.profit_table import build_profit_table_data, profit_table
from ui.ruler import RULER_CSS, RULER_JS, build_ruler_html
from ui.theme import GLOBAL_CSS, PALETTE

DEFAULT_TICKER = "TSLA"
DEFAULT_STRATEGY = "Bull Call Spread"
DEFAULT_STRIKE_INCREMENT = 5.0
DEFAULT_DTE_DAYS = 30.0
DEFAULT_PRICE_RANGE_PCT = 0.25
N_CHART_POINTS = 300
N_TABLE_PRICE_ROWS = 15
N_TABLE_DATE_COLS = 8
EXPIRATION_PRESETS = [7, 14, 30, 45, 60, 90, 180, 365]


@dataclass
class AppState:
    ticker: str = DEFAULT_TICKER
    strategy_name: str = DEFAULT_STRATEGY
    strike_increment: float = DEFAULT_STRIKE_INCREMENT
    dte_days: float = DEFAULT_DTE_DAYS
    price_range_pct: float = DEFAULT_PRICE_RANGE_PCT
    iv_multiplier: float = 1.0
    as_of_days_elapsed: float = 0.0
    view_mode: str = VIEW_MODES[0]
    r_override: float | None = None   # decimal, None = simulated
    q_override: float | None = None
    legs: list[Leg] = field(default_factory=list)
    simulator: MarketSimulator | None = None
    snapshot: UnderlyingSnapshot | None = None

    def ensure_simulator(self) -> None:
        if self.simulator is None or self.simulator.ticker != self.ticker.strip().upper():
            self.simulator = MarketSimulator(self.ticker)
            self.snapshot = self.simulator.snapshot()

    @property
    def rate(self) -> float:
        return self.snapshot.risk_free_rate if self.r_override is None else self.r_override

    @property
    def div_yield(self) -> float:
        return self.snapshot.dividend_yield if self.q_override is None else self.q_override

    def scaled_iv_fn(self):
        base_fn, m = self.simulator.implied_vol, self.iv_multiplier
        return lambda strike, spot, dte: base_fn(strike, spot, dte) * m

    def reset_legs_to_strategy(self) -> None:
        self.legs = build_strategy_legs(
            self.strategy_name, self.snapshot.price, self.strike_increment, self.dte_days)

    def set_dte(self, new_dte: float) -> None:
        """Change expiration while keeping strikes/structure: scale every option
        leg's DTE by new/nearest so calendar structures keep their shape."""
        opt = [l for l in self.legs if l.kind != "stock"]
        if opt:
            base = min(l.dte_days for l in opt)
            ratio = new_dte / base if base > 0 else 1.0
            for l in opt:
                l.dte_days = round(max(l.dte_days * ratio, 1.0), 2)
        self.dte_days = float(new_dte)

    def max_leg_dte(self) -> float:
        return max((l.dte_days for l in self.legs if l.kind != "stock"), default=self.dte_days)


def _save_state_to_dict(state: AppState) -> dict:
    return {
        "ticker": state.ticker, "strategy_name": state.strategy_name,
        "strike_increment": state.strike_increment, "dte_days": state.dte_days,
        "price_range_pct": state.price_range_pct, "iv_multiplier": state.iv_multiplier,
        "as_of_days_elapsed": state.as_of_days_elapsed, "view_mode": state.view_mode,
        "r_override": state.r_override, "q_override": state.q_override,
        "legs": [{"kind": l.kind, "direction": l.direction, "quantity": l.quantity,
                  "strike": l.strike, "dte_days": l.dte_days} for l in state.legs],
    }


def _load_state_from_dict(state: AppState, data: dict) -> None:
    state.ticker = data.get("ticker", DEFAULT_TICKER)
    state.strategy_name = data.get("strategy_name", DEFAULT_STRATEGY)
    state.strike_increment = data.get("strike_increment", DEFAULT_STRIKE_INCREMENT)
    state.dte_days = data.get("dte_days", DEFAULT_DTE_DAYS)
    state.price_range_pct = data.get("price_range_pct", DEFAULT_PRICE_RANGE_PCT)
    state.iv_multiplier = data.get("iv_multiplier", 1.0)
    state.as_of_days_elapsed = data.get("as_of_days_elapsed", 0.0)
    state.view_mode = data.get("view_mode", VIEW_MODES[0])
    state.r_override = data.get("r_override")
    state.q_override = data.get("q_override")
    state.legs = [Leg(l["kind"], l["direction"], l["quantity"], l["strike"], l["dte_days"])
                  for l in data.get("legs", [])]
    state.simulator = None
    state.ensure_simulator()


def build_page(state: AppState | None = None) -> None:
    ui.add_head_html(f"<style>{GLOBAL_CSS}{RULER_CSS}</style>")
    ui.add_body_html(RULER_JS)

    state = state or AppState()
    state.ensure_simulator()
    if not state.legs:
        state.reset_legs_to_strategy()

    syncing = {"on": False}   # True while code (not the user) sets control values

    def guarded(fn):
        def wrapper(e):
            if not syncing["on"]:
                fn(e)
        return wrapper

    # ------------------------------------------------------------------ layout
    with ui.row().classes("gap-4"):
        ui.link("Futures payoff & risk →", "/futures")
        ui.link("Portfolio →", "/portfolio")
    header_container = ui.column().classes("w-full gap-3")
    dialog_host = ui.element("div")
    with ui.row().classes("w-full gap-4 items-start flex-wrap lg:flex-nowrap"):
        with ui.column().classes("gap-4 flex-grow").style("min-width: 0;"):
            # ---- static controls (never rebuilt) ----
            with ui.column().classes("opt-panel w-full gap-2"):
                with ui.row().classes("w-full items-end gap-4 flex-wrap"):
                    ticker_in = ui.input("Ticker", value=state.ticker).props(
                        "dense outlined debounce=600").style("width: 120px;")
                    strategy_options = [n for g in STRATEGY_GROUPS.values() for n in g]
                    strategy_sel = ui.select(strategy_options, value=state.strategy_name,
                                             label="Strategy", with_input=True
                                             ).props("dense outlined").style("min-width: 220px;")
                    dte_in = ui.number("DTE (days)", value=state.dte_days, min=1, max=730,
                                       step=1).props("dense outlined").style("width: 110px;")
                    ui.button("Save", on_click=lambda: _handle_save()).props("dense outline")
                    ui.button("Load", on_click=lambda: _handle_load()).props("dense outline")
                with ui.row().classes("items-center gap-2"):
                    ui.label("Expiration").classes("text-xs").style(f"color:{PALETTE.text_secondary}")
                    exp_toggle = ui.toggle(
                        {d: f"{d}d" for d in EXPIRATION_PRESETS},
                        value=int(state.dte_days) if int(state.dte_days) in EXPIRATION_PRESETS else None,
                    ).props("dense no-caps size=sm")
                with ui.expansion("Advanced (rates)", icon="tune").classes("w-full").props("dense"):
                    with ui.row().classes("gap-4 items-end"):
                        r_in = ui.number("Risk-free rate (%)", value=round(state.rate * 100, 3),
                                         step=0.1, format="%.3f").props("dense outlined").style("width: 170px;")
                        q_in = ui.number("Dividend yield (%)", value=round(state.div_yield * 100, 3),
                                         step=0.1, format="%.3f").props("dense outlined").style("width: 170px;")
                        ui.label("Overrides the simulated rates used for pricing and Greeks."
                                 ).style(f"color:{PALETTE.text_muted}; font-size:11px;")

            ruler_html = ui.html("").classes("opt-panel w-full")
            with ui.tabs(value=state.view_mode).props("dense no-caps align=left").classes(
                    "w-full opt-panel") as view_tabs:
                for m in VIEW_MODES:
                    ui.tab(m)
            chart = ui.echart({"series": []}).classes("w-full opt-panel").style("height: 420px;")

            with ui.row().classes("opt-panel w-full gap-8 flex-wrap items-start"):
                with ui.column().classes("gap-1").style("min-width: 260px; flex: 1;"):
                    price_lbl = ui.label("").classes("text-sm")
                    price_sl = ui.slider(min=0.05, max=1.0, step=0.05, value=state.price_range_pct)
                    with price_sl:
                        ui.tooltip(insights.price_range_slider_tooltip())
                with ui.column().classes("gap-1").style("min-width: 260px; flex: 1;"):
                    iv_lbl = ui.label("").classes("text-sm")
                    iv_sl = ui.slider(min=0.25, max=3.0, step=0.05, value=state.iv_multiplier)
                    with iv_sl:
                        ui.tooltip(insights.iv_slider_tooltip())
                with ui.column().classes("gap-1").style("min-width: 260px; flex: 1;"):
                    asof_lbl = ui.label("").classes("text-sm")
                    asof_sl = ui.slider(min=0, max=max(state.max_leg_dte(), 1.0), step=1,
                                        value=state.as_of_days_elapsed)
                    with asof_sl:
                        ui.tooltip(insights.as_of_date_slider_tooltip())

            table_container = ui.column().classes("w-full")

        with ui.column().style("width: 340px; flex-shrink: 0;").classes("gap-4"):
            positions_container = ui.column().classes("w-full")
            flow_container = ui.column().classes("opt-panel gap-2 w-full")

    # ------------------------------------------------------------- refreshers
    def refresh_flow() -> None:
        flow_container.clear()
        with flow_container:
            ui.label("Recent Simulated Flow").classes("text-sm font-semibold")
            ui.label("Illustrative only — generated locally, not real trade data."
                     ).style(f"color: {PALETTE.text_muted}; font-size: 11px;")
            for row in state.simulator.flow_tape(state.snapshot, n=8):
                flow_row(row)

    def refresh() -> None:
        state.ensure_simulator()
        spot, r, q = state.snapshot.price, state.rate, state.div_yield
        iv_fn = state.scaled_iv_fn()
        priced = price_legs(state.legs, spot, r, q, iv_fn)
        S = price_grid(spot, state.price_range_pct, N_CHART_POINTS)
        exp_pnl = expiration_payoff(priced, S)
        max_dte = state.max_leg_dte()
        pos_iv = float(iv_fn(spot, spot, max_dte)) if state.legs else state.snapshot.base_iv
        stats = compute_stats(priced, S, exp_pnl, spot, r, q, iv_fn, pos_iv, max_dte)
        pidx = profit_index(priced, S, exp_pnl, spot, pos_iv, max_dte, r, stats.max_loss.value)
        elapsed = state.as_of_days_elapsed

        # ---- chart (updated in place) ----
        mode = state.view_mode
        greeks_at_date = None
        if mode == VIEW_MODES[0]:
            y, label, kind, name, fill = exp_pnl, "Profit / Loss ($)", "money", "At Expiration", True
            asof = asof_payoff(priced, S, r, q, iv_fn, spot, elapsed) if 0 < elapsed < max_dte else None
            bes = stats.breakevens
        else:
            y, label, kind = view_series(mode, priced, S, r, q, iv_fn, spot, elapsed, max_dte,
                                         stats.max_loss.value)
            name, asof = f"{mode} (day +{int(elapsed)})", None
            fill = mode in ("Profit / Loss %", "% of Max Risk")
            bes = find_breakevens(S, y) if fill else []
        hover = None
        if state.legs and kind in ("money", "pct"):
            greeks_at_date = {g: greek_curve(priced, S, r, q, iv_fn, spot, elapsed, g)
                              for g in ("delta", "gamma", "theta", "vega")}
        if state.legs:
            hover = hover_texts(S, y, spot, stats.net_entry_cost, greeks_at_date, kind)
        chart.options.clear()
        chart.options.update(build_payoff_chart_options(
            S, y, spot, bes, asof_pnl=asof, y_axis_label=label, y_kind=kind,
            hover=hover, fill=fill, main_name=name))
        chart.update()

        # ---- display-only regions ----
        header_container.clear()
        with header_container:
            snapshot_header(state.snapshot)
            g = stats.greeks
            greeks_strip(g, pos_iv, {
                "delta": insights.delta_tooltip(g.delta), "gamma": insights.gamma_tooltip(g.gamma),
                "theta": insights.theta_tooltip(g.theta), "vega": insights.vega_tooltip(g.vega),
                "rho": insights.rho_tooltip(g.rho)})
            key_stats_bar(
                stats.net_entry_cost, stats.max_profit, stats.max_loss, stats.breakevens,
                stats.probability_of_profit,
                {"net_cost": insights.net_debit_credit_tooltip(stats.net_entry_cost),
                 "max_profit": insights.max_profit_tooltip(stats.max_profit.is_unbounded, stats.max_profit.value),
                 "max_loss": insights.max_loss_tooltip(stats.max_loss.is_unbounded, stats.max_loss.value),
                 "breakeven": "\n".join(insights.breakeven_tooltip(b) for b in stats.breakevens)
                              or "No breakeven within the modeled range.",
                 "pop": insights.probability_of_profit_tooltip(stats.probability_of_profit),
                 "profit_index": insights.profit_index_tooltip(pidx)},
                profit_idx=pidx)

        ruler_html.content = build_ruler_html(state.legs, spot, state.strike_increment)

        positions_container.clear()
        with positions_container:
            positions_sidebar(priced, on_edit=open_edit, on_remove=remove_leg, on_add=add_leg)

        table_container.clear()
        with table_container:
            price_rows = np.linspace(S[0], S[-1], N_TABLE_PRICE_ROWS)
            date_cols = np.linspace(0, max_dte, N_TABLE_DATE_COLS)
            headers, rows = build_profit_table_data(priced, price_rows, date_cols, spot, r, q, iv_fn)
            profit_table(price_rows, headers, rows, spot)

        # ---- labels / slider bounds (values only touched if they differ) ----
        price_lbl.text = f"Price Range: ±{state.price_range_pct * 100:.0f}%"
        iv_lbl.text = f"Implied Volatility Scenario: {state.iv_multiplier * 100:.0f}%"
        asof_lbl.text = "As Of Date: " + ("Today" if elapsed == 0 else f"+{int(elapsed)}d")
        new_max = max(max_dte, 1.0)
        if asof_sl.props.get("max") != new_max:
            syncing["on"] = True
            asof_sl.props(f"max={new_max}")
            if state.as_of_days_elapsed > new_max:
                state.as_of_days_elapsed = new_max
                asof_sl.value = new_max
            syncing["on"] = False

    def sync_controls() -> None:
        """Push AppState values into the static controls without triggering handlers."""
        syncing["on"] = True
        ticker_in.value = state.ticker
        strategy_sel.value = state.strategy_name
        dte_in.value = state.dte_days
        exp_toggle.value = int(state.dte_days) if int(state.dte_days) in EXPIRATION_PRESETS else None
        price_sl.value, iv_sl.value = state.price_range_pct, state.iv_multiplier
        asof_sl.value = state.as_of_days_elapsed
        view_tabs.value = state.view_mode
        r_in.value, q_in.value = round(state.rate * 100, 3), round(state.div_yield * 100, 3)
        syncing["on"] = False

    # --------------------------------------------------------------- handlers
    def on_ticker(e):
        state.ticker = (e.value or DEFAULT_TICKER).strip().upper() or DEFAULT_TICKER
        state.ensure_simulator()
        state.r_override = state.q_override = None
        state.reset_legs_to_strategy()
        sync_controls()
        refresh_flow()
        refresh()

    def on_strategy(e):
        state.strategy_name = e.value
        state.reset_legs_to_strategy()
        refresh()

    def on_dte(e):
        if e.value:
            state.set_dte(float(e.value))
            syncing["on"] = True
            exp_toggle.value = int(state.dte_days) if int(state.dte_days) in EXPIRATION_PRESETS else None
            syncing["on"] = False
            refresh()

    def on_exp_toggle(e):
        if e.value:
            state.set_dte(float(e.value))
            syncing["on"] = True
            dte_in.value = float(e.value)
            syncing["on"] = False
            refresh()

    def _set(attr):
        def h(e):
            setattr(state, attr, float(e.value))
            refresh()
        return h

    def on_tab(e):
        state.view_mode = e.value
        refresh()

    def on_rate(e):
        state.r_override = None if e.value is None else float(e.value) / 100.0
        refresh()

    def on_div(e):
        state.q_override = None if e.value is None else float(e.value) / 100.0
        refresh()

    def on_ruler_drag(e):
        idx, strike = int(e.args["idx"]), float(e.args["strike"])
        if 0 <= idx < len(state.legs):
            state.legs[idx].strike = strike
            refresh()

    def add_leg(kind: str, direction: int):
        spot = state.snapshot.price
        strike = round(spot / state.strike_increment) * state.strike_increment
        state.legs.append(Leg(kind, direction, 1, strike if kind != "stock" else spot, state.dte_days))
        refresh()

    def remove_leg(leg: Leg):
        if leg in state.legs:
            state.legs.remove(leg)
            refresh()

    def open_edit(leg: Leg):
        is_stock = leg.kind == "stock"
        with dialog_host:
            with ui.dialog() as dlg, ui.card().classes("opt-panel gap-2").style("min-width: 300px;"):
                ui.label(f"Edit leg: {leg.label()}").classes("text-base font-semibold")
                dir_sel = ui.select({1: "Long", -1: "Short"}, value=leg.direction, label="Direction")
                qty = ui.number("Quantity" + (" (100-share lots)" if is_stock else " (contracts)"),
                                value=leg.quantity, min=1, step=1, precision=0)
                strike = ui.number("Entry price" if is_stock else "Strike", value=leg.strike, min=0.01, step=state.strike_increment)
                dte = None if is_stock else ui.number("DTE (days)", value=leg.dte_days, min=1, max=730, step=1)

                def apply():
                    leg.direction = int(dir_sel.value)
                    leg.quantity = max(1, int(qty.value or 1))
                    leg.strike = float(strike.value or leg.strike)
                    if dte is not None:
                        leg.dte_days = float(dte.value or leg.dte_days)
                    dlg.close()
                    refresh()

                with ui.row():
                    ui.button("Apply", on_click=apply)
                    ui.button("Cancel", on_click=dlg.close).props("flat")
        dlg.open()

    def _handle_save():
        ui.download(json.dumps(_save_state_to_dict(state), indent=2).encode(), filename="strategy.json")

    def _handle_load():
        with dialog_host:
            with ui.dialog() as dlg, ui.card().classes("opt-panel"):
                ui.label("Paste saved strategy JSON:")
                text_area = ui.textarea().props("outlined").style("width: 400px; height: 200px;")

                def confirm():
                    try:
                        _load_state_from_dict(state, json.loads(text_area.value))
                    except Exception as exc:  # noqa: BLE001 - surfaced to the user
                        ui.notify(f"Could not load strategy: {exc}", type="negative")
                        return
                    dlg.close()
                    sync_controls()
                    refresh_flow()
                    refresh()

                with ui.row():
                    ui.button("Load", on_click=confirm)
                    ui.button("Cancel", on_click=dlg.close).props("flat")
        dlg.open()

    # wire handlers once
    ticker_in.on_value_change(guarded(on_ticker))
    strategy_sel.on_value_change(guarded(on_strategy))
    dte_in.on_value_change(guarded(on_dte))
    exp_toggle.on_value_change(guarded(on_exp_toggle))
    price_sl.on_value_change(guarded(_set("price_range_pct")))
    iv_sl.on_value_change(guarded(_set("iv_multiplier")))
    asof_sl.on_value_change(guarded(_set("as_of_days_elapsed")))
    view_tabs.on_value_change(guarded(on_tab))
    r_in.on_value_change(guarded(on_rate))
    q_in.on_value_change(guarded(on_div))
    ui.on("ruler_drag", on_ruler_drag)

    refresh_flow()
    refresh()
