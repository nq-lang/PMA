"""
engine/views.py
================
Alternate chart "view modes" (spec §3.6) and the Profit Index tile (§3.3).
Pure numpy; reuses engine.payoff/pricing so every view agrees with the
main P/L curve.

Definitions (documented choices):
- P/L %            = P/L / |net entry cost| * 100 (return on premium/capital
                     at risk; if net cost is ~0, falls back to raw P/L).
- Contract Value   = current mark-to-model value of the whole position in $
                     (sum of direction*qty*100*leg_price), i.e. P/L + entry cost.
- % of Max Risk    = P/L / |max loss| * 100. If max loss is unbounded the
                     chart falls back to |net entry cost| as the risk base.
- Greek curves     = position Greek (delta/gamma/theta/vega/rho) at each price
                     in the grid, `days_elapsed` days after entry.
- Profit Index     = E[P/L] / risk base, where E[P/L] is the expectation of
                     expiration P/L under the same lognormal model as POP and
                     risk base = |max loss| (or |net cost| if unbounded).
"""
from __future__ import annotations

import numpy as np
from scipy.stats import norm

from engine.payoff import (
    CONTRACT_MULTIPLIER, DAYS_PER_YEAR, PricedLeg, asof_payoff, expiration_payoff,
    leg_dte_years, net_entry_cost,
)
from engine.pricing import bsm_greeks

VIEW_MODES = [
    "Profit / Loss $", "Profit / Loss %", "Contract Value", "% of Max Risk",
    "Delta", "Gamma", "Theta", "Vega", "Rho",
]


def pnl_curve(priced_legs, S, r, q, iv_fn, spot, days_elapsed, max_dte):
    """Expiration curve when scrubbed to expiry, else the as-of curve."""
    if days_elapsed >= max_dte:
        return expiration_payoff(priced_legs, S)
    return asof_payoff(priced_legs, S, r, q, iv_fn, spot, days_elapsed)


def risk_base(net_cost: float, max_loss_value: float | None) -> float:
    base = abs(max_loss_value) if max_loss_value is not None else abs(net_cost)
    return base if base > 1e-9 else 1.0


def greek_curve(priced_legs: list[PricedLeg], S, r, q, iv_fn, spot,
                days_elapsed: float, greek: str) -> np.ndarray:
    """Position Greek across the price grid (contract/direction weighted)."""
    S = np.asarray(S, dtype=float)
    total = np.zeros_like(S)
    for pl in priced_legs:
        leg = pl.leg
        w = leg.direction * leg.quantity * CONTRACT_MULTIPLIER
        if leg.kind == "stock":
            if greek == "delta":
                total += w
            continue
        remaining = max(leg.dte_days - days_elapsed, 0.0)
        iv_now = float(iv_fn(leg.strike, spot, remaining))
        g = bsm_greeks(S, leg.strike, r, q, iv_now, leg_dte_years(remaining), leg.kind)
        total += w * np.asarray(getattr(g, greek), dtype=float)
    return total


def view_series(mode, priced_legs, S, r, q, iv_fn, spot, days_elapsed,
                max_dte, max_loss_value):
    """Return (y_array, axis_label, kind) for the requested view mode."""
    cost = net_entry_cost(priced_legs)
    pnl = pnl_curve(priced_legs, S, r, q, iv_fn, spot, days_elapsed, max_dte)
    if mode == "Profit / Loss $":
        return pnl, "Profit / Loss ($)", "money"
    if mode == "Profit / Loss %":
        base = abs(cost) if abs(cost) > 1e-9 else 1.0
        return pnl / base * 100.0, "Profit / Loss (%)", "pct"
    if mode == "Contract Value":
        return pnl + cost, "Position Value ($)", "money"
    if mode == "% of Max Risk":
        return pnl / risk_base(cost, max_loss_value) * 100.0, "% of Max Risk", "pct"
    greek = mode.lower()
    return greek_curve(priced_legs, S, r, q, iv_fn, spot, days_elapsed, greek), mode, "greek"


def expected_value(priced_legs, spot, iv, dte_days, r) -> float:
    """Model expected P/L ($) at expiration under the same lognormal terminal-price model as the Probability of Profit."""
    T = max(dte_days, 0.0) / DAYS_PER_YEAR
    if T <= 0 or iv <= 0:
        return float(expiration_payoff(priced_legs, np.array([spot]))[0])
    mu = np.log(spot) + (r - 0.5 * iv ** 2) * T
    sig = iv * np.sqrt(T)
    z = np.linspace(-6, 6, 4001)
    pnl = expiration_payoff(priced_legs, np.exp(mu + sig * z))
    return float(np.trapezoid(pnl * norm.pdf(z), z))


def profit_index(priced_legs, S_wide, expiration_pnl_wide, spot, iv, dte_days,
                 r, max_loss_value) -> float:
    """E[P/L] / risk base under the lognormal terminal-price model."""
    base = risk_base(net_entry_cost(priced_legs), max_loss_value)
    return expected_value(priced_legs, spot, iv, dte_days, r) / base
