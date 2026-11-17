"""
ui/futures_page.py
===================
Futures payoff & risk page (route: /futures). Thin UI over ``engine.futures``;
all math lives in the engine and in the pure ``compute_view`` below (tested).
"""
from __future__ import annotations

import numpy as np
from nicegui import ui

from engine import futures as fut
from ui.theme import GLOBAL_CSS, PALETTE


def compute_view(
    symbol: str, qty: int, entry: float, mark: float, fee_per_side: float,
    equity: float, stop: float | None, target: float | None,
    range_pct: float = 0.04, n: int = 241,
) -> dict:
    """Everything the page renders, as plain data (no UI imports needed)."""
    spec = fut.get_spec(symbol)
    pos = fut.FuturesPosition(spec, int(qty), float(entry), float(fee_per_side))
    init, maint = pos.margin()
    out: dict = {
        "spec": spec, "position": pos, "init_margin": init, "maint_margin": maint,
        "unrealized": pos.pnl(mark) if qty else 0.0,
        "breakeven": pos.breakeven(), "bracket": None, "liquidation": None,
        "excess_liquidity": equity - maint, "leverage": pos.leverage(equity) if qty else 0.0,
    }
    if qty:
        out["liquidation"] = pos.liquidation_price(equity)
        if stop and target:
            try:
                out["bracket"] = fut.bracket(pos, stop, target)
            except ValueError:
                out["bracket"] = None
    lo, hi = entry * (1 - range_pct), entry * (1 + range_pct)
    grid = fut.round_to_tick(np.linspace(lo, hi, n), spec)
    out["grid"], out["pnl"] = grid, pos.pnl(grid, include_fees=True) if qty else np.zeros(n)
    return out


def _chart_options(v: dict, mark: float, stop, target) -> dict:
    x = [float(p) for p in v["grid"]]
    y = [round(float(p), 2) for p in v["pnl"]]
    lines = [(v["position"].entry, "Entry", PALETTE.text_secondary),
             (mark, "Mark", PALETTE.accent_blue),
             (v["breakeven"], "Breakeven", PALETTE.accent_violet)]
    if v["liquidation"] is not None:
        lines.append((v["liquidation"], "Margin call", PALETTE.loss_red))
    if stop:
        lines.append((stop, "Stop", PALETTE.loss_red_dim))
    if target:
        lines.append((target, "Target", PALETTE.profit_green_dim))
    return {
        "backgroundColor": "transparent",
        "animation": False,
        "grid": {"left": 70, "right": 30, "top": 20, "bottom": 40},
        "tooltip": {"trigger": "axis", "valueFormatter": None},
        "xAxis": {"type": "value", "min": x[0], "max": x[-1], "scale": True,
                  "axisLabel": {"color": PALETTE.text_secondary}},
        "yAxis": {"type": "value", "axisLabel": {"color": PALETTE.text_secondary},
                  "splitLine": {"lineStyle": {"color": PALETTE.border_subtle}}},
        "series": [{
            "type": "line", "showSymbol": False, "data": list(zip(x, y)),
            "lineStyle": {"color": PALETTE.profit_green, "width": 2},
            "markLine": {"symbol": "none", "silent": True, "data": [
                {"xAxis": float(px), "label": {"formatter": name, "color": col},
                 "lineStyle": {"color": col, "type": "dashed"}} for px, name, col in lines
            ]},
        }],
    }


def build_futures_page() -> None:
    ui.add_head_html(f"<style>{GLOBAL_CSS}</style>")
    st = {"symbol": "ES", "qty": 1, "entry": 5000.0, "mark": 5000.0, "fee": 2.5,
          "equity": 30000.0, "stop": 4980.0, "target": 5060.0}

    with ui.row().classes("w-full items-center gap-4"):
        ui.label("Futures Payoff & Risk").classes("text-xl font-semibold")
        ui.link("← Options payoff", "/")
    badge = ui.label().style(f"color: {PALETTE.text_muted}; font-size: 12px;")
    with ui.row().classes("opt-panel w-full gap-4 items-end flex-wrap"):
        sym = ui.select(sorted(fut.CONTRACTS), value=st["symbol"], label="Contract").classes("w-28")
        inputs = {
            "qty": ui.number("Qty (+long/-short)", value=st["qty"], step=1, format="%d"),
            "entry": ui.number("Entry", value=st["entry"]),
            "mark": ui.number("Mark", value=st["mark"]),
            "fee": ui.number("Fee/side $", value=st["fee"]),
            "equity": ui.number("Account equity $", value=st["equity"]),
            "stop": ui.number("Stop", value=st["stop"]),
            "target": ui.number("Target", value=st["target"]),
        }
    metrics = ui.row().classes("opt-panel w-full gap-6 flex-wrap")
    chart = ui.echart({"series": []}).classes("w-full opt-panel").style("height: 420px;")

    def stat(label: str, value: str, color: str | None = None) -> None:
        with ui.column().classes("gap-0"):
            ui.label(label).style(f"color: {PALETTE.text_muted}; font-size: 11px;")
            ui.label(value).style(
                f"font-variant-numeric: tabular-nums; font-size: 16px;"
                + (f"color: {color};" if color else ""))

    def refresh(_=None) -> None:
        vals = {k: (w.value if w.value is not None else 0) for k, w in inputs.items()}
        try:
            v = compute_view(sym.value, int(vals["qty"]), vals["entry"], vals["mark"],
                             vals["fee"], vals["equity"], vals["stop"] or None, vals["target"] or None)
        except Exception as exc:  # noqa: BLE001 - surface bad input, keep page alive
            ui.notify(f"Invalid input: {exc}", type="warning")
            return
        spec, pos = v["spec"], v["position"]
        badge.set_text(f"{spec.name} · tick {spec.tick_size:g} = ${spec.tick_value:,.2f} · "
                       f"${spec.multiplier:,g}/pt · margins: {spec.margin_source.upper()} "
                       "(not exchange data)")
        pnl_color = PALETTE.profit_green if v["unrealized"] >= 0 else PALETTE.loss_red
        metrics.clear()
        with metrics:
            stat("Unrealized P&L", f"${v['unrealized']:,.2f}", pnl_color)
            stat("$/point · $/tick", f"${pos.dollars_per_point:,.2f} · ${pos.dollars_per_tick:,.2f}")
            stat("Notional", f"${pos.notional:,.0f}")
            stat("Init / Maint margin", f"${v['init_margin']:,.0f} / ${v['maint_margin']:,.0f}")
            stat("Excess liquidity", f"${v['excess_liquidity']:,.0f}",
                 PALETTE.loss_red if v["excess_liquidity"] < 0 else None)
            stat("Leverage", f"{v['leverage']:.1f}x")
            stat("Breakeven (after fees)", f"{v['breakeven']:,.2f}")
            if v["liquidation"] is not None:
                stat("Margin-call price", f"{v['liquidation']:,.2f}", PALETTE.loss_red)
            if v["bracket"]:
                b = v["bracket"]
                stat("Risk / Reward", f"${b.risk_dollars:,.0f} / ${b.reward_dollars:,.0f}  ({b.risk_reward:.2f}R)")
        chart.options.clear()
        chart.options.update(_chart_options(v, vals["mark"], vals["stop"] or None, vals["target"] or None))
        chart.update()

    sym.on_value_change(refresh)
    for w in inputs.values():
        w.on_value_change(refresh)
    refresh()
