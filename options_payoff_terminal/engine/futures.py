"""
engine/futures.py
==================
High-precision futures payoff & risk module.

* ``CONTRACTS``: registry of contract specifications (tick size, tick value,
  point multiplier, quarterly cycle).  **Margin figures are PLACEHOLDER
  indicative values** — exchanges change them often. They are structured so
  a live data adapter can overwrite them via ``update_margins``; until
  then every margin-derived output is only as good as these placeholders.
* Tick-exact P&L, commission-adjusted breakevens, scale-in/out averaging,
  bracket risk/reward, liquidation (margin-call) price levels, calendar
  spread / roll analysis, and Black-76 options on futures.

All money in USD. Quantities are signed (+long / -short).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

import numpy as np
from scipy.special import ndtr


@dataclass(frozen=True)
class ContractSpec:
    symbol: str
    name: str
    exchange: str
    multiplier: float          # $ per 1.0 point
    tick_size: float           # points
    cycle: str                 # "HMUZ" quarterly, "monthly", ...
    init_margin: float         # per contract, $ (PLACEHOLDER; see module doc)
    maint_margin: float        # per contract, $ (PLACEHOLDER)
    margin_source: str = "placeholder"

    @property
    def tick_value(self) -> float:
        return self.tick_size * self.multiplier


def _c(sym, name, ex, mult, tick, cyc, im, mm):
    return ContractSpec(sym, name, ex, mult, tick, cyc, im, mm)


CONTRACTS: dict[str, ContractSpec] = {c.symbol: c for c in [
    _c("ES",  "E-mini S&P 500",         "CME",   50,    0.25,      "HMUZ", 22000, 20000),
    _c("MES", "Micro E-mini S&P 500",   "CME",   5,     0.25,      "HMUZ", 2200,  2000),
    _c("NQ",  "E-mini Nasdaq-100",      "CME",   20,    0.25,      "HMUZ", 33000, 30000),
    _c("MNQ", "Micro E-mini Nasdaq-100","CME",   2,     0.25,      "HMUZ", 3300,  3000),
    _c("RTY", "E-mini Russell 2000",    "CME",   50,    0.10,      "HMUZ", 8000,  7300),
    _c("M2K", "Micro E-mini Russell 2000","CME", 5,     0.10,      "HMUZ", 800,   730),
    _c("YM",  "E-mini Dow",             "CBOT",  5,     1.0,       "HMUZ", 15000, 13600),
    _c("MYM", "Micro E-mini Dow",       "CBOT",  0.5,   1.0,       "HMUZ", 1500,  1360),
    _c("ZN",  "10-Year T-Note",         "CBOT",  1000,  1 / 64,    "HMUZ", 2100,  1900),
    _c("ZB",  "30-Year T-Bond",         "CBOT",  1000,  1 / 32,    "HMUZ", 4200,  3800),
    _c("CL",  "WTI Crude Oil",          "NYMEX", 1000,  0.01,      "monthly", 6500, 5900),
    _c("GC",  "Gold",                   "COMEX", 100,   0.10,      "GJMQVZ", 11000, 10000),
    _c("MGC", "Micro Gold",             "COMEX", 10,    0.10,      "GJMQVZ", 1100,  1000),
]}


def get_spec(symbol: str) -> ContractSpec:
    try:
        return CONTRACTS[symbol.upper()]
    except KeyError:
        raise KeyError(f"unknown futures symbol {symbol!r}; known: {sorted(CONTRACTS)}") from None


def update_margins(symbol: str, init: float, maint: float, source: str) -> ContractSpec:
    """Overwrite a contract's margins (hook for the live exchange-data adapter)."""
    if maint > init:
        raise ValueError("maintenance margin cannot exceed initial margin")
    CONTRACTS[symbol.upper()] = replace(
        get_spec(symbol), init_margin=init, maint_margin=maint, margin_source=source
    )
    return CONTRACTS[symbol.upper()]


def round_to_tick(price, spec: ContractSpec):
    return np.round(np.asarray(price, dtype=float) / spec.tick_size) * spec.tick_size


@dataclass(frozen=True)
class FuturesPosition:
    spec: ContractSpec
    qty: int                   # signed contracts
    entry: float
    fee_per_side: float = 0.0  # commissions + exchange fees, $ per contract per side

    def pnl(self, price, include_fees: bool = False):
        """Gross (or net of round-trip fees) P&L in $ at ``price``."""
        p = np.asarray(price, dtype=float)
        out = (p - self.entry) * self.qty * self.spec.multiplier
        if include_fees:
            out = out - 2 * self.fee_per_side * abs(self.qty)
        return float(out) if np.isscalar(price) else out

    @property
    def dollars_per_point(self) -> float:
        return self.qty * self.spec.multiplier

    @property
    def dollars_per_tick(self) -> float:
        return self.qty * self.spec.tick_value

    @property
    def notional(self) -> float:
        return abs(self.qty) * self.entry * self.spec.multiplier

    def breakeven(self) -> float:
        """Price at which P&L net of round-trip fees is zero."""
        if self.qty == 0:
            return self.entry
        pts = 2 * self.fee_per_side / self.spec.multiplier
        return self.entry + (pts if self.qty > 0 else -pts)

    def margin(self) -> tuple[float, float]:
        n = abs(self.qty)
        return n * self.spec.init_margin, n * self.spec.maint_margin

    def liquidation_price(self, account_equity: float, mark: float | None = None) -> float:
        """Mark price at which equity falls to maintenance margin (margin call).

        ``account_equity`` is equity when the position is marked at ``mark``
        (default: entry).
        """
        mark = self.entry if mark is None else mark
        _, maint = self.margin()
        cushion = account_equity - maint
        move = cushion / abs(self.dollars_per_point)
        return mark - move if self.qty > 0 else mark + move

    def drawdown_price(self, max_loss: float) -> float:
        """Price at which unrealized loss equals ``max_loss`` (daily-limit line)."""
        move = max_loss / abs(self.dollars_per_point)
        return self.entry - move if self.qty > 0 else self.entry + move

    def leverage(self, account_equity: float) -> float:
        return self.notional / account_equity if account_equity > 0 else float("inf")


def scale(position: FuturesPosition, fills: Sequence[tuple[int, float]]) -> FuturesPosition:
    """Apply (signed qty, price) fills; returns the new position.

    Adding in the same direction re-averages the entry; reducing keeps the
    entry; flipping through zero re-enters at the flip fill price.
    """
    qty, entry = position.qty, position.entry
    for dq, px in fills:
        new = qty + dq
        if qty == 0 or np.sign(dq) == np.sign(qty):
            entry = (entry * abs(qty) + px * abs(dq)) / max(abs(new), 1) if new else px
        elif new != 0 and np.sign(new) != np.sign(qty):
            entry = px
        qty = new
    return replace(position, qty=qty, entry=entry if qty else position.entry)


@dataclass(frozen=True)
class Bracket:
    risk_points: float
    reward_points: float
    risk_dollars: float
    reward_dollars: float
    risk_reward: float


def bracket(position: FuturesPosition, stop: float, target: float) -> Bracket:
    if position.qty == 0:
        raise ValueError("flat position")
    sgn = 1 if position.qty > 0 else -1
    risk = (position.entry - stop) * sgn
    reward = (target - position.entry) * sgn
    if risk <= 0 or reward <= 0:
        raise ValueError("stop must be on the losing side and target on the winning side of entry")
    dpp = abs(position.dollars_per_point)
    return Bracket(risk, reward, risk * dpp, reward * dpp, reward / risk)


@dataclass(frozen=True)
class RollAnalysis:
    spread: float              # back - front, points
    spread_dollars: float      # per contract
    annualized_carry: float    # (back/front - 1) * 365/days
    fair_spread: float | None  # cost-of-carry fair value spread, points
    mispricing: float | None   # market spread - fair spread, points


def roll_analysis(
    spec: ContractSpec, front: float, back: float, days_between: float,
    spot: float | None = None, r: float = 0.0, q: float = 0.0,
    days_front: float | None = None,
) -> RollAnalysis:
    """Calendar-spread differential and implied carry. If ``spot`` and the
    front's days-to-expiry are given, compares to cost-of-carry fair value
    F = S*exp((r-q)T)."""
    spread = back - front
    carry = (back / front - 1.0) * 365.0 / days_between if days_between > 0 else float("nan")
    fair = mis = None
    if spot is not None and days_front is not None:
        f_fair = spot * np.exp((r - q) * days_front / 365.0)
        b_fair = spot * np.exp((r - q) * (days_front + days_between) / 365.0)
        fair = float(b_fair - f_fair)
        mis = float(spread - fair)
    return RollAnalysis(spread, spread * spec.multiplier, float(carry), fair, mis)


def calendar_spread_pnl(spec: ContractSpec, qty: int, entry_spread: float, spread_now) -> np.ndarray | float:
    """P&L of long ``qty`` spreads (long back / short front)."""
    out = (np.asarray(spread_now, dtype=float) - entry_spread) * qty * spec.multiplier
    return float(out) if np.isscalar(spread_now) else out


# --- Black-76 options on futures -------------------------------------------

def black76_price(F, K, r: float, sigma, T, option_type: str):
    F = np.asarray(F, dtype=float)
    T = np.asarray(T, dtype=float)
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'")
    intr = np.maximum(F - K, 0.0) if option_type == "call" else np.maximum(K - F, 0.0)
    Ts = np.maximum(T, 1e-12)
    ss = np.maximum(np.asarray(sigma, dtype=float), 1e-9)
    v = ss * np.sqrt(Ts)
    d1 = (np.log(F / K) + 0.5 * v * v) / v
    d2 = d1 - v
    df = np.exp(-r * Ts)
    px = df * (F * ndtr(d1) - K * ndtr(d2)) if option_type == "call" else df * (K * ndtr(-d2) - F * ndtr(-d1))
    out = np.where(T <= 1e-9, intr, px)
    return float(out) if np.ndim(out) == 0 else out


def futures_option_composite_pnl(
    position: FuturesPosition, options: Sequence[dict], grid, r: float = 0.04,
):
    """Composite P&L (futures + options on futures) across a price grid.

    Each option dict: ``kind`` ('call'/'put'), ``strike``, ``qty`` (signed),
    ``iv``, ``T`` (years remaining), ``entry`` (premium, points).
    Options use the same multiplier as the underlying contract.
    """
    g = np.asarray(grid, dtype=float)
    total = position.pnl(g)
    for o in options:
        val = black76_price(g, o["strike"], r, o["iv"], o["T"], o["kind"])
        total = total + (val - o["entry"]) * o["qty"] * position.spec.multiplier
    return total
