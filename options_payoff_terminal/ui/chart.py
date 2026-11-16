"""
ui/chart.py
===========
ECharts option builder for the payoff chart (original config).

Key points
- Profit/loss shading is two clipped fill series (>=0 green, <=0 red), so the
  color split is exactly at y=0 (an earlier single-gradient version split at
  the bounding-box midpoint instead).
- Crosshair tooltip text is precomputed in Python (`hover_texts`) and stored as
  the 3rd element of each data point; the client formatter just prints it.
- Breakevens get hoverable markers with a plain-language explanation (§7).
- IMPORTANT: JS callbacks must use the ":key" prefix (Vue v-bind) or NiceGUI
  will treat them as literal strings (see PROGRESS.md regression entry).
"""
from __future__ import annotations

import json

import numpy as np
from nicegui import ui

from ui import insights
from ui.theme import PALETTE

MAIN_NAME = "At Expiration"
ASOF_NAME = "As Of Date"


def _split_by_sign(S: np.ndarray, pnl: np.ndarray) -> list[list[float]]:
    """[[x, y], ...] with an exact interpolated zero-crossing inserted at each
    sign change, so clipped fills meet the zero line precisely."""
    points: list[list[float]] = []
    for i in range(len(S)):
        points.append([round(float(S[i]), 4), round(float(pnl[i]), 4)])
        if i < len(S) - 1:
            p0, p1 = pnl[i], pnl[i + 1]
            if (p0 < 0 < p1) or (p0 > 0 > p1):
                frac = -p0 / (p1 - p0)
                x_cross = float(S[i]) + frac * (float(S[i + 1]) - float(S[i]))
                points.append([round(x_cross, 4), 0.0])
    return points


def dominant_greek(delta: float, gamma: float, theta: float, vega: float, spot: float) -> str:
    """Which Greek moves value most for a 'typical' shock: a 1% spot move
    (delta, and gamma as 0.5*gamma*dS^2), one day (theta), one vol point (vega)."""
    dS = spot * 0.01
    impact = {
        "Delta": abs(delta * dS),
        "Gamma": abs(0.5 * gamma * dS * dS),
        "Theta": abs(theta),
        "Vega": abs(vega),
    }
    return max(impact, key=impact.get)


def hover_texts(S, y, spot, cost, greeks: dict | None, kind: str) -> list[str]:
    """Precomputed crosshair tooltip HTML for every grid point (§7)."""
    out = []
    base = abs(cost) if abs(cost) > 1e-9 else None
    for i, price in enumerate(S):
        val = float(y[i])
        if kind == "money":
            head = f"P/L ${val:,.2f}"
            if base:
                head += f" ({val / base * 100:+.1f}% of entry cost)"
        elif kind == "pct":
            head = f"{val:,.1f}%"
        else:
            head = f"{val:,.4f}"
        text = f"<b>Price ${price:,.2f}</b> ({(price / spot - 1) * 100:+.1f}% vs spot)<br/>{head}"
        if greeks is not None:
            d, g = float(greeks["delta"][i]), float(greeks["gamma"][i])
            t, v = float(greeks["theta"][i]), float(greeks["vega"][i])
            dom = dominant_greek(d, g, t, v, spot)
            text += (
                f"<br/>Δ {d:,.1f} · Γ {g:,.2f} · Θ {t:,.2f}/day · ν {v:,.2f}"
                f"<br/><i>Dominant Greek here: {dom}</i>"
            )
        out.append(text)
    return out


def _fill(color_top: str, color_bottom: str) -> dict:
    return {
        "color": {
            "type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
            "colorStops": [{"offset": 0, "color": color_top}, {"offset": 1, "color": color_bottom}],
        }
    }


def build_payoff_chart_options(
    S: np.ndarray,
    main_y: np.ndarray,
    spot: float,
    breakevens: list[float],
    asof_pnl: np.ndarray | None = None,
    y_axis_label: str = "Profit / Loss ($)",
    y_kind: str = "money",          # "money" | "pct" | "greek"
    hover: list[str] | None = None,  # precomputed tooltip html for the main curve
    fill: bool = True,
    main_name: str = MAIN_NAME,
) -> dict:
    main_points = [
        [round(float(S[i]), 4), round(float(main_y[i]), 4)] + ([hover[i]] if hover else [])
        for i in range(len(S))
    ]
    series: list[dict] = [{
        "name": main_name, "type": "line", "data": main_points, "showSymbol": False,
        "lineStyle": {"width": 2, "color": PALETTE.text_primary}, "z": 3,
    }]
    if asof_pnl is not None:
        series.append({
            "name": ASOF_NAME, "type": "line", "showSymbol": False, "z": 4,
            "data": [[round(float(S[i]), 4), round(float(asof_pnl[i]), 4)] for i in range(len(S))],
            "lineStyle": {"width": 2, "type": "dashed", "color": PALETTE.accent_amber},
        })

    if fill:
        pts = _split_by_sign(S, main_y)
        series.append({
            "name": "_profit_fill", "type": "line", "showSymbol": False, "silent": True, "z": 1,
            "data": [[x, max(y, 0.0)] for x, y in pts], "lineStyle": {"width": 0},
            "areaStyle": _fill(PALETTE.profit_fill_top, PALETTE.profit_fill_bottom),
            "tooltip": {"show": False},
        })
        series.append({
            "name": "_loss_fill", "type": "line", "showSymbol": False, "silent": True, "z": 1,
            "data": [[x, min(y, 0.0)] for x, y in pts], "lineStyle": {"width": 0},
            "areaStyle": _fill(PALETTE.loss_fill_top, PALETTE.loss_fill_bottom),
            "tooltip": {"show": False},
        })

    mark_lines = [
        {"yAxis": 0, "lineStyle": {"color": PALETTE.border_strong, "type": "solid", "width": 1},
         "label": {"show": False}},
        {"xAxis": spot, "lineStyle": {"color": PALETTE.accent_blue, "type": "dotted"},
         "label": {"formatter": f"Spot ${spot:,.2f}", "color": PALETTE.accent_blue,
                   "position": "end", "distance": 4}},
    ]
    for be in breakevens:
        mark_lines.append({
            "xAxis": be, "lineStyle": {"color": PALETTE.accent_violet, "type": "dashed"},
            "label": {"formatter": f"${be:,.2f}", "color": PALETTE.accent_violet,
                      "position": "start", "distance": 4},
        })
    series[0]["markLine"] = {"silent": True, "symbol": "none", "data": mark_lines,
                             "label": {"fontSize": 11}}

    if breakevens:
        series[0]["markPoint"] = {
            "symbol": "circle", "symbolSize": 13,
            "itemStyle": {"color": PALETTE.accent_violet, "borderColor": "#fff", "borderWidth": 1},
            "label": {"show": False},
            "data": [{"coord": [be, 0], "name": "Breakeven",
                      "explain": insights.breakeven_tooltip(be)} for be in breakevens],
        }

    axis_fmt = {"money": "${value}", "pct": "{value}%", "greek": "{value}"}[y_kind]
    tooltip = {
        "trigger": "axis", "confine": True,
        "backgroundColor": PALETTE.bg_panel_raised, "borderColor": PALETTE.border_strong,
        "textStyle": {"color": PALETTE.text_primary, "fontSize": 12},
        "axisPointer": {"type": "cross", "lineStyle": {"color": PALETTE.text_muted, "type": "dashed"},
                        "label": {"backgroundColor": PALETTE.bg_input}},
    }
    if hover:
        be_info = [{"x": be, "text": insights.breakeven_tooltip(be)} for be in breakevens]
        tol = float(S[-1] - S[0]) / max(len(S), 1) * 3
        tooltip[":formatter"] = (
            "(ps) => { const bes = " + json.dumps(be_info) + "; const tol = " + repr(tol) + ";"
            " const ax = ps.length ? Number(ps[0].axisValue) : NaN;"
            " let out = ps.filter(s => s.data && s.data.length > 2)"
            ".map(s => '<div style=\"max-width:300px;white-space:normal\">' + s.data[2] + '</div>').join('');"
            " for (const b of bes) { if (Math.abs(ax - b.x) <= tol) {"
            " out += '<hr/><div style=\"max-width:300px;white-space:normal\"><b>Breakeven</b><br/>' + b.text + '</div>'; } }"
            " return out; }"
        )

    legend_names = [main_name] + ([ASOF_NAME] if asof_pnl is not None else [])
    return {
        "animation": False,  # instant redraw: live slider/ruler drags must not lag or screenshot mid-animation
        "backgroundColor": "transparent",
        "textStyle": {"color": PALETTE.text_secondary},
        "grid": {"left": 70, "right": 30, "top": 30, "bottom": 40},
        "legend": {"show": asof_pnl is not None, "top": 0, "data": legend_names,
                   "textStyle": {"color": PALETTE.text_secondary}},
        "tooltip": tooltip,
        "xAxis": {
            "type": "value", "name": "Underlying Price ($)", "nameLocation": "middle", "nameGap": 28,
            "min": round(float(S[0])), "max": round(float(S[-1])),
            "axisLine": {"lineStyle": {"color": PALETTE.border_strong}},
            "splitLine": {"lineStyle": {"color": PALETTE.border_subtle}},
            "axisLabel": {"formatter": "${value}"},
        },
        "yAxis": {
            "type": "value", "name": y_axis_label, "nameLocation": "middle", "nameGap": 55,
            "axisLine": {"lineStyle": {"color": PALETTE.border_strong}},
            "splitLine": {"lineStyle": {"color": PALETTE.border_subtle}},
            "axisLabel": {"formatter": axis_fmt},
        },
        "series": series,
    }


def payoff_chart(*args, **kwargs) -> ui.echart:
    chart = ui.echart(build_payoff_chart_options(*args, **kwargs)).classes("w-full")
    chart.style("height: 420px;")
    return chart
