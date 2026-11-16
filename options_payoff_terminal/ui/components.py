"""
ui/components.py
=================

Reusable NiceGUI widgets shared across the app's layout:
- stat_tile: a labeled value with a hover tooltip (spec §7)
- leg_chip / leg_row: a single position leg, editable inline
- snapshot_header: the ticker/company/price/range/MA card
- greeks_strip: the Delta/Gamma/Theta/Vega/Rho/IV row
- flow_row: a single cosmetic "recent trades" tape row

Every widget here is presentational; the calling layout code is
responsible for wiring callbacks (on_click, on_change) and for passing in
already-computed values from engine/payoff.py and engine/market_sim.py.
No pricing or simulation logic lives in this module.
"""

from __future__ import annotations

from nicegui import ui

from engine.market_sim import FlowRow, UnderlyingSnapshot
from engine.payoff import MaxPnL, PositionGreeks
from engine.strategies import Leg
from ui.theme import PALETTE


def fmt_dollars(value: float, signed: bool = False, decimals: int = 2) -> str:
    sign = "+" if signed and value > 0 else ("-" if value < 0 else "")
    return f"{sign}${abs(value):,.{decimals}f}"


def fmt_compact_dollars(value: float) -> str:
    """Compact form for large numbers, e.g. market cap: $905.9B, $2.6M."""
    abs_v = abs(value)
    sign = "-" if value < 0 else ""
    if abs_v >= 1e12:
        return f"{sign}${abs_v / 1e12:,.2f}T"
    if abs_v >= 1e9:
        return f"{sign}${abs_v / 1e9:,.2f}B"
    if abs_v >= 1e6:
        return f"{sign}${abs_v / 1e6:,.2f}M"
    if abs_v >= 1e3:
        return f"{sign}${abs_v / 1e3:,.1f}K"
    return f"{sign}${abs_v:,.2f}"


def fmt_pct(value: float, decimals: int = 1) -> str:
    return f"{value * 100:,.{decimals}f}%"


def stat_tile(label: str, value_text: str, tooltip_text: str, value_class: str = "") -> ui.element:
    """A single labeled stat with a hover tooltip explaining the number.
    `value_class` can be 'opt-value-positive' / 'opt-value-negative' to
    color-code the figure (e.g., green Max Profit, red Max Loss)."""
    with ui.column().classes("opt-stat-tile gap-0").style("min-width: 130px;") as tile:
        ui.label(label).classes("opt-stat-label")
        ui.label(value_text).classes(f"opt-stat-value {value_class}".strip())
    with tile:
        ui.tooltip(tooltip_text).style(
            f"max-width: 320px; background-color: {PALETTE.bg_panel_raised}; "
            f"color: {PALETTE.text_primary}; border: 1px solid {PALETTE.border_strong}; "
            "font-size: 13px; line-height: 1.4;"
        )
    return tile


def key_stats_bar(
    net_cost: float,
    max_profit: MaxPnL,
    max_loss: MaxPnL,
    breakevens: list[float],
    pop: float,
    tooltips: dict,
    profit_idx: float | None = None,
) -> None:
    """The row of key stats under the strategy selector (Premium Paid /
    Net Credit, Max Profit, Max Loss, Break Even(s), Probability of
    Profit) -- matches the reference terminal's key-stats bar."""
    with ui.row().classes("gap-3 flex-wrap w-full"):
        cost_label = "Net Debit" if net_cost >= 0 else "Net Credit"
        stat_tile(cost_label, fmt_dollars(abs(net_cost)), tooltips["net_cost"])

        mp_text = "Unlimited" if max_profit.is_unbounded else fmt_dollars(max_profit.value)
        stat_tile("Max Profit", mp_text, tooltips["max_profit"], "opt-value-positive")

        ml_text = "Unlimited" if max_loss.is_unbounded else fmt_dollars(abs(max_loss.value))
        stat_tile("Max Loss", ml_text, tooltips["max_loss"], "opt-value-negative")

        be_text = ", ".join(f"${b:,.2f}" for b in breakevens) if breakevens else "—"
        stat_tile("Break Even", be_text, tooltips["breakeven"])

        stat_tile("Probability of Profit", fmt_pct(pop), tooltips["pop"])
        if profit_idx is not None:
            stat_tile("Profit Index", f"{profit_idx:,.2f}", tooltips["profit_index"])


def greeks_strip(greeks: PositionGreeks, iv_pct: float, tooltips: dict) -> None:
    """The Delta/Gamma/Theta/Vega/Rho/IV strip shown near the header."""
    with ui.row().classes("gap-3 flex-wrap w-full"):
        stat_tile("Delta", f"{greeks.delta:,.2f}", tooltips["delta"])
        stat_tile("Gamma", f"{greeks.gamma:,.3f}", tooltips["gamma"])
        stat_tile(
            "Theta",
            f"{greeks.theta:,.2f}",
            tooltips["theta"],
            "opt-value-negative" if greeks.theta < 0 else "opt-value-positive",
        )
        stat_tile("Vega", f"{greeks.vega:,.2f}", tooltips["vega"])
        stat_tile("Rho", f"{greeks.rho:,.2f}", tooltips["rho"])
        stat_tile("Implied Volatility", fmt_pct(iv_pct), "The simulated implied volatility currently being used to price every leg in this position.")


def snapshot_header(snap: UnderlyingSnapshot) -> None:
    """The ticker/company-name/price/day-range/52wk-range/MA card."""
    with ui.row().classes("opt-panel w-full justify-between items-start flex-wrap gap-6"):
        with ui.column().classes("gap-0"):
            ui.label(snap.company_name).classes("text-lg font-semibold")
            ui.label(f"{snap.ticker}").style(f"color: {PALETTE.text_secondary}; font-size: 13px;")
            ui.label(f"${snap.price:,.2f}").classes("text-2xl font-bold mt-1").style(
                f"font-family: monospace; color: {PALETTE.text_primary};"
            )
        with ui.column().classes("gap-1 text-sm"):
            ui.label(f"Day Range: ${snap.day_low:,.2f} – ${snap.day_high:,.2f}")
            ui.label(f"52-Week Range: ${snap.year_low:,.2f} – ${snap.year_high:,.2f}")
        with ui.column().classes("gap-1 text-sm"):
            ui.label(f"Mkt Cap: {fmt_compact_dollars(snap.market_cap)}")
            ui.label(f"50-Day MA: ${snap.ma_50:,.2f}")
            ui.label(f"200-Day MA: ${snap.ma_200:,.2f}")
        ui.label("SIMULATED DATA").classes("opt-badge-simulated self-start")


def leg_chip(leg: Leg, on_edit=None, on_remove=None, premium: float | None = None) -> ui.element:
    """One leg as a chip (e.g. '280C', '-280P x2'): green=long, red=short.
    Click opens the edit dialog; the x removes it. `premium` is the per-share
    entry price shown next to the chip (spec §3.9)."""
    css_class = "opt-chip opt-chip-long" if leg.direction > 0 else "opt-chip opt-chip-short"
    with ui.row().classes("items-center gap-2 w-full no-wrap"):
        with ui.row().classes(f"{css_class} items-center").on(
            "click", lambda _=None, l=leg: on_edit(l) if on_edit else None
        ) as chip:
            ui.icon("arrow_upward" if leg.direction > 0 else "arrow_downward").classes("text-xs")
            ui.label(leg.label())
            if on_remove is not None:
                ui.icon("close").classes("text-xs opacity-60 hover:opacity-100").on(
                    "click.stop", lambda _=None, l=leg: on_remove(l)
                )
        detail = "shares" if leg.kind == "stock" else f"{leg.dte_days:g}d"
        prem = f" @ ${premium:,.2f}" if premium is not None else ""
        ui.label(f"{detail}{prem}").style(f"color: {PALETTE.text_secondary}; font-size: 11px;")
    return chip


def positions_sidebar(priced_legs, on_edit=None, on_remove=None, on_add=None) -> None:
    """Right-hand 'Positions' panel: quick-add buttons plus one editable chip
    per leg with its entry premium. `priced_legs` is a list of PricedLeg."""
    with ui.column().classes("opt-panel gap-3 w-full"):
        ui.label("Positions").classes("text-base font-semibold")
        if on_add is not None:
            with ui.row().classes("gap-2 flex-wrap"):
                ui.button("Call ↑", on_click=lambda: on_add("call", 1)).props("dense outline")
                ui.button("Call ↓", on_click=lambda: on_add("call", -1)).props("dense outline")
                ui.button("Put ↑", on_click=lambda: on_add("put", 1)).props("dense outline")
                ui.button("Put ↓", on_click=lambda: on_add("put", -1)).props("dense outline")
                ui.button("Stock", on_click=lambda: on_add("stock", 1)).props("dense outline")
        with ui.column().classes("gap-2 w-full"):
            if not priced_legs:
                ui.label("No legs yet — add one above or pick a strategy.").style(
                    f"color: {PALETTE.text_muted}; font-size: 13px;"
                )
            for pl in priced_legs:
                leg_chip(pl.leg, on_edit=on_edit, on_remove=on_remove, premium=pl.entry_price)


def flow_row(row: FlowRow) -> None:
    """A single cosmetic 'recent trades' tape row. Purely decorative —
    not wired to any pricing or interactive behavior."""
    color = PALETTE.profit_green if row.option_type == "CALL" else PALETTE.loss_red
    with ui.column().classes("gap-0 w-full py-1").style(
        f"border-bottom: 1px solid {PALETTE.border_subtle};"
    ):
        with ui.row().classes("justify-between items-center w-full"):
            ui.label(row.timestamp).style(f"color: {PALETTE.text_muted}; font-size: 11px;")
            ui.label(f"{row.tag}").style(f"color: {PALETTE.text_muted}; font-size: 11px;")
        with ui.row().classes("justify-between items-center w-full"):
            ui.label(f"{row.ticker} {row.option_type}").style(
                f"color: {color}; font-weight: 600; font-size: 13px;"
            )
            ui.label(fmt_compact_dollars(row.notional)).style("font-size: 13px;")
        ui.label(
            f"{row.size} @ ${row.price:,.2f}  ·  Strike ${row.strike:,.0f}  ·  "
            f"OTM {row.otm_pct:,.0f}%  ·  OI {row.open_interest:,}  ·  IV {row.implied_vol_pct:,.0f}%"
        ).style(f"color: {PALETTE.text_secondary}; font-size: 11px;")
