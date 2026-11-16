"""
engine/payoff.py
=================

Payoff/P&L engine: turns a list of `Leg` objects (engine/strategies.py) plus
a simulated market environment (engine/market_sim.py) into everything the
UI needs to draw a payoff chart and stats bar:

- Per-leg entry premium (what the position "cost", computed via BSM)
- At-expiration payoff array over a price grid (pure intrinsic-value math)
- "As of" date payoff array (re-priced via BSM at remaining time -- NOT a
  linear interpolation between today and expiration; see `asof_payoff`)
- Aggregate position Greeks (Delta/Gamma/Theta/Vega/Rho), contract- and
  direction-weighted
- Breakeven price(s), found generically via root-finding so it works for
  *any* leg combination, not just 1-2 leg formulas
- Max Profit / Max Loss, including correct "Unlimited"/"-Infinity"
  detection from the payoff array's asymptotic slope
- Probability of Profit under a lognormal terminal-price assumption

CONTRACT MULTIPLIER & STOCK CONVENTION
---------------------------------------
Options: 1 contract = 100 shares. All dollar P&L for option legs is
per-share-price * 100 * quantity * direction.

Stock legs: `Leg.quantity` is interpreted as **100-share lots** (i.e.,
quantity=1 means 100 shares), the same "lot size" as an option contract.
This keeps position-Greek scaling uniform across leg types (a covered
call's stock delta of +100 lines up on the same footing as its short
call's delta contribution) and matches how the reference UI's "Positions"
sidebar treats a stock leg as directly comparable in size to an option
leg. This convention is stated explicitly here and in the README since it
is a deliberate, documented choice per spec §5.3 ("Stock legs contribute
Delta = +/-shares/100 ... be explicit").
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import optimize
from scipy.stats import norm

from engine.pricing import Greeks, bsm_greeks, bsm_price
from engine.strategies import Leg

CONTRACT_MULTIPLIER = 100.0
DAYS_PER_YEAR = 365.0


# ---------------------------------------------------------------------------
# Leg pricing (entry premium + mark-to-model pricing at any point in time)
# ---------------------------------------------------------------------------


def leg_dte_years(dte_days: float) -> float:
    return max(dte_days, 0.0) / DAYS_PER_YEAR


def leg_entry_price(
    leg: Leg, spot: float, iv: float, r: float, q: float
) -> float:
    """Per-share entry price for a single leg, at trade inception (T =
    leg.dte_days). Stock legs are priced at `spot` (their entry basis)."""
    if leg.kind == "stock":
        return spot
    T = leg_dte_years(leg.dte_days)
    return float(bsm_price(spot, leg.strike, r, q, iv, T, leg.kind))


def leg_price_at(
    leg: Leg,
    S: np.ndarray,
    r: float,
    q: float,
    iv: float,
    days_elapsed: float,
) -> np.ndarray:
    """Per-share mark-to-model price of a single leg, `days_elapsed` days
    after trade inception, evaluated across a price grid `S`. For an
    option leg this re-prices via BSM at the leg's *remaining* time
    (leg.dte_days - days_elapsed, floored at 0 = expired/intrinsic). For a
    stock leg, price is simply `S` (marked to the hypothetical spot)."""
    if leg.kind == "stock":
        return np.asarray(S, dtype=float)
    T_remaining_days = max(leg.dte_days - days_elapsed, 0.0)
    T = leg_dte_years(T_remaining_days)
    return bsm_price(S, leg.strike, r, q, iv, T, leg.kind)


@dataclass
class PricedLeg:
    """A `Leg` bundled with its simulated entry IV and computed entry
    premium (per-share), so downstream payoff math doesn't need to
    re-derive IV per leg on every call."""

    leg: Leg
    entry_iv: float
    entry_price: float  # per-share

    @property
    def entry_cost(self) -> float:
        """Signed dollar cost to establish this leg (positive = debit paid,
        negative = credit received), including contract multiplier and
        quantity. A long leg costs money (positive); a short leg receives
        money (negative cost)."""
        multiplier = CONTRACT_MULTIPLIER if self.leg.kind != "stock" else CONTRACT_MULTIPLIER
        return self.leg.direction * self.leg.quantity * multiplier * self.entry_price


def leg_iv_now(leg: Leg, iv_fn, spot: float, remaining_dte: float) -> float:
    """IV used to re-price a leg after entry. A per-leg custom IV is scaled by the scenario multiplier
    (`iv_fn.scale`, 1.0 if absent) so the IV slider shifts it too."""
    if leg.iv is not None:
        return float(leg.iv) * float(getattr(iv_fn, "scale", 1.0))
    return float(iv_fn(leg.strike, spot, remaining_dte))


def price_legs(
    legs: list[Leg],
    spot: float,
    r: float,
    q: float,
    iv_fn,
) -> list[PricedLeg]:
    """Compute entry IV (via `iv_fn(strike, spot, dte_days) -> float`) and
    entry premium for every leg. `iv_fn` is typically
    `MarketSimulator.implied_vol`, injected so this module has no direct
    dependency on the simulator (keeps pricing math independently
    testable with fixed IVs).
    """
    priced: list[PricedLeg] = []
    for leg in legs:
        if leg.kind == "stock":
            entry_iv = 0.0
            entry_price = spot
        else:
            entry_iv = float(leg.iv) if leg.iv is not None else float(iv_fn(leg.strike, spot, leg.dte_days))
            entry_price = (
                float(leg.premium) if leg.premium is not None
                else leg_entry_price(leg, spot, entry_iv, r, q)
            )
        priced.append(PricedLeg(leg=leg, entry_iv=entry_iv, entry_price=entry_price))
    return priced


# ---------------------------------------------------------------------------
# Net premium (position-level entry cost)
# ---------------------------------------------------------------------------


def net_entry_cost(priced_legs: list[PricedLeg]) -> float:
    """Net dollar cost to establish the whole position: positive = net
    debit paid, negative = net credit received."""
    return float(sum(pl.entry_cost for pl in priced_legs))


# ---------------------------------------------------------------------------
# Payoff arrays
# ---------------------------------------------------------------------------


def price_grid(spot: float, price_range_pct: float, n_points: int = 300) -> np.ndarray:
    """A price grid spanning +/- `price_range_pct` (e.g., 0.30 for +/-30%)
    around `spot`, per spec §3.5/§3.7's 'Price Range %' slider. `n_points`
    defaults within the spec's suggested 200-400 point range (§6)."""
    low = max(spot * (1.0 - price_range_pct), 0.01)
    high = spot * (1.0 + price_range_pct)
    return np.linspace(low, high, n_points)


def expiration_payoff(
    priced_legs: list[PricedLeg], S: np.ndarray
) -> np.ndarray:
    """At-expiration P&L across price grid `S`: pure intrinsic-value math
    per leg, minus each leg's entry cost, summed. Vectorized.
    """
    S = np.asarray(S, dtype=float)
    total = np.zeros_like(S)
    for pl in priced_legs:
        leg = pl.leg
        if leg.kind == "stock":
            leg_value = S  # at "expiration" a stock position is just marked at S
        else:
            # T=0 -> bsm_price collapses to intrinsic value (see pricing.py)
            leg_value = bsm_price(S, leg.strike, 0.0, 0.0, 0.01, 0.0, leg.kind)
        multiplier = CONTRACT_MULTIPLIER
        leg_pl = leg.direction * leg.quantity * multiplier * leg_value - pl.entry_cost
        total += leg_pl
    return total


def asof_payoff(
    priced_legs: list[PricedLeg],
    S: np.ndarray,
    r: float,
    q: float,
    iv_fn,
    spot: float,
    days_elapsed: float,
) -> np.ndarray:
    """'As of' date P&L across price grid `S`, `days_elapsed` days after
    trade inception. This is the correct, non-naive time-decay curve: each
    leg is re-priced via BSM at its own *remaining* time-to-expiration
    (which may differ per leg, e.g. calendar spreads), using the
    simulated IV for that leg's strike/DTE at that point in time -- it is
    **not** a linear interpolation between the today-curve and the
    expiration-curve.

    `iv_fn(strike, spot, dte_days)` supplies IV for re-pricing; we
    evaluate it at each leg's *remaining* DTE (not entry DTE), consistent
    with how the simulator's smooth term-structure function is meant to be
    read as "IV appropriate for an option with this much time left."
    """
    S = np.asarray(S, dtype=float)
    total = np.zeros_like(S)
    for pl in priced_legs:
        leg = pl.leg
        if leg.kind == "stock":
            leg_value = S
        else:
            remaining_dte = max(leg.dte_days - days_elapsed, 0.0)
            iv_now = leg_iv_now(leg, iv_fn, spot, remaining_dte)
            leg_value = leg_price_at(leg, S, r, q, iv_now, days_elapsed)
        multiplier = CONTRACT_MULTIPLIER
        leg_pl = leg.direction * leg.quantity * multiplier * leg_value - pl.entry_cost
        total += leg_pl
    return total


# ---------------------------------------------------------------------------
# Aggregate position Greeks
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PositionGreeks:
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


def position_greeks(
    priced_legs: list[PricedLeg],
    spot: float,
    r: float,
    q: float,
    iv_fn,
    days_elapsed: float = 0.0,
) -> PositionGreeks:
    """Aggregate position Greeks at `spot`, `days_elapsed` days after
    inception, contract- and direction-weighted and summed across legs.
    Stock legs contribute only to Delta (see module docstring for the
    100-shares-per-lot convention) and zero to the other Greeks.
    """
    delta = gamma = theta = vega = rho = 0.0
    for pl in priced_legs:
        leg = pl.leg
        weight = leg.direction * leg.quantity
        if leg.kind == "stock":
            delta += weight * CONTRACT_MULTIPLIER
            continue
        remaining_dte = max(leg.dte_days - days_elapsed, 0.0)
        iv_now = leg_iv_now(leg, iv_fn, spot, remaining_dte)
        T = leg_dte_years(remaining_dte)
        g: Greeks = bsm_greeks(spot, leg.strike, r, q, iv_now, T, leg.kind)
        delta += weight * CONTRACT_MULTIPLIER * g.delta
        gamma += weight * CONTRACT_MULTIPLIER * g.gamma
        theta += weight * CONTRACT_MULTIPLIER * g.theta
        vega += weight * CONTRACT_MULTIPLIER * g.vega
        rho += weight * CONTRACT_MULTIPLIER * g.rho
    return PositionGreeks(delta=delta, gamma=gamma, theta=theta, vega=vega, rho=rho)


# ---------------------------------------------------------------------------
# Breakeven root-finding (generalizes to any leg combination)
# ---------------------------------------------------------------------------


def find_breakevens(S: np.ndarray, pnl: np.ndarray) -> list[float]:
    """Find breakeven price(s): root(s) of the P&L function, located by
    bracketing sign changes across the price grid and refining each with
    `scipy.optimize.brentq`. This is fully generic -- it does not assume
    any particular number of legs or a closed-form breakeven formula, so
    it works for a 1-leg call, a 2-leg vertical, a 4-leg iron condor, or
    an arbitrary custom structure alike.

    Exact zeros on the grid (pnl == 0 at a grid point) are also reported.
    Returns breakevens sorted ascending; near-duplicate roots (within a
    tiny tolerance relative to the grid spacing) are de-duplicated.
    """
    S = np.asarray(S, dtype=float)
    pnl = np.asarray(pnl, dtype=float)
    breakevens: list[float] = []

    sign = np.sign(pnl)
    # Treat "close enough to zero" grid points as exact zero-crossings too.
    zero_tol = 1e-6 * max(np.max(np.abs(pnl)), 1.0)

    for i in range(len(S) - 1):
        p0, p1 = pnl[i], pnl[i + 1]
        if abs(p0) <= zero_tol:
            breakevens.append(float(S[i]))
            continue
        if sign[i] == 0:
            continue
        if sign[i] != sign[i + 1] and sign[i + 1] != 0:
            # bracketed sign change -> refine with brentq
            try:
                root = optimize.brentq(
                    lambda x: np.interp(x, S, pnl), S[i], S[i + 1], xtol=1e-6
                )
                breakevens.append(float(root))
            except (ValueError, RuntimeError):
                # brentq can fail on pathological interpolated shapes; fall
                # back to the midpoint as a reasonable approximation rather
                # than dropping the breakeven entirely.
                breakevens.append(float((S[i] + S[i + 1]) / 2))

    if abs(pnl[-1]) <= zero_tol:
        breakevens.append(float(S[-1]))

    # De-duplicate near-identical roots (can happen at grid boundaries).
    breakevens.sort()
    deduped: list[float] = []
    grid_spacing = float(S[1] - S[0]) if len(S) > 1 else 1.0
    for b in breakevens:
        if not deduped or abs(b - deduped[-1]) > grid_spacing * 0.5:
            deduped.append(b)
    return deduped


# ---------------------------------------------------------------------------
# Max Profit / Max Loss (with correct unbounded detection)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MaxPnL:
    value: float | None  # None means unbounded in this direction
    is_unbounded: bool


def _net_payoff_slope_as_S_to_infinity(priced_legs: list[PricedLeg]) -> float:
    """Net asymptotic d(P&L)/dS as S -> +infinity.

    As S -> +infinity: a call's delta -> 1, a put's delta -> 0, and a
    stock leg's "delta" (in our 100-shares-per-lot convention) is the
    constant `direction * quantity * 100` everywhere. Summing
    `direction * quantity * 100 * asymptotic_delta` across legs gives the
    net slope of the payoff line at the far right of the chart. A nonzero
    slope means the position's P&L keeps changing without bound as price
    rises -- positive slope => unbounded profit to the upside, negative
    slope => unbounded loss to the upside.
    """
    slope = 0.0
    for pl in priced_legs:
        leg = pl.leg
        weight = leg.direction * leg.quantity * CONTRACT_MULTIPLIER
        if leg.kind == "stock":
            slope += weight
        elif leg.kind == "call":
            slope += weight * 1.0  # call delta -> 1 as S -> inf
        elif leg.kind == "put":
            slope += weight * 0.0  # put delta -> 0 as S -> inf
    return slope


def _payoff_at_zero_price(priced_legs: list[PricedLeg]) -> float:
    """Exact P&L at the theoretical floor S=0 (a call is worthless, a put
    is worth its full strike, stock is worth nothing), independent of
    whatever price range the chart happens to be zoomed to. This lets Max
    Profit/Loss be correct even when the visible chart window (per the
    'Price Range %' slider) doesn't happen to extend all the way down to
    S=0.
    """
    total = 0.0
    for pl in priced_legs:
        leg = pl.leg
        if leg.kind == "stock":
            leg_value = 0.0
        elif leg.kind == "call":
            leg_value = 0.0  # max(0-K, 0) = 0
        else:  # put
            leg_value = leg.strike  # max(K-0, 0) = K
        total += leg.direction * leg.quantity * CONTRACT_MULTIPLIER * leg_value - pl.entry_cost
    return total


def max_profit_loss(
    priced_legs: list[PricedLeg], S: np.ndarray, pnl: np.ndarray
) -> tuple[MaxPnL, MaxPnL]:
    """Determine Max Profit and Max Loss for the position.

    Only the **upside** (S -> +infinity) can produce a genuinely unbounded
    result, because the underlying price is mathematically bounded below
    by zero: a put or short stock position's payoff slope may be nonzero
    as S -> 0, but that slope is realized over a *finite* price range (S
    can fall at most to 0, not to -infinity), so the payoff value it
    reaches at S=0 -- while it can be large -- is always a finite,
    computable number, not "Unlimited". This mirrors every real options
    platform: a long put's max profit is reported as strike*100 - premium
    (achieved if the stock goes to zero), never as "Infinity".

    Unboundedness is therefore derived analytically from the net
    asymptotic payoff slope as S -> infinity only (per spec §5.4's "does
    P&L trend to +inf/-inf as price -> 0 or infinity" -- for price -> 0
    the answer is always "no, it reaches a large-but-finite value at
    S=0"). We compute that S=0 value directly (`_payoff_at_zero_price`),
    independent of the currently-visible chart window, and fold it into
    the candidate extrema alongside the evaluated array's interior
    extrema -- so Max Profit/Loss stays correct even when the user has
    zoomed the chart to a narrow price range that doesn't itself reach
    S=0.
    """
    S = np.asarray(S, dtype=float)
    pnl = np.asarray(pnl, dtype=float)

    slope_at_inf = _net_payoff_slope_as_S_to_infinity(priced_legs)
    unbounded_profit_up = slope_at_inf > 1e-9
    unbounded_loss_up = slope_at_inf < -1e-9

    payoff_at_zero = _payoff_at_zero_price(priced_legs)

    interior_max = max(float(np.max(pnl)), payoff_at_zero)
    interior_min = min(float(np.min(pnl)), payoff_at_zero)

    max_profit = MaxPnL(
        value=None if unbounded_profit_up else interior_max,
        is_unbounded=unbounded_profit_up,
    )
    max_loss = MaxPnL(
        value=None if unbounded_loss_up else interior_min,
        is_unbounded=unbounded_loss_up,
    )
    return max_profit, max_loss


# ---------------------------------------------------------------------------
# Probability of Profit (lognormal terminal-price assumption)
# ---------------------------------------------------------------------------


def probability_of_profit(
    S: np.ndarray,
    pnl: np.ndarray,
    spot: float,
    iv: float,
    dte_days: float,
    r: float = 0.0,
) -> float:
    """Probability that the terminal underlying price lands in a
    profitable region, under a lognormal distribution for the terminal
    price implied by (spot, iv, dte_days) -- i.e. assuming
    ln(S_T / spot) ~ Normal((r - 0.5*iv^2)*T, iv^2*T), a standard
    risk-neutral-ish lognormal terminal-price model. This is a modeling
    **assumption**, not a guarantee (surfaced to the user via a tooltip
    per spec §7) -- real-world terminal price distributions can differ
    from lognormal (fat tails, skew, jumps).

    Method: identify the profitable price sub-intervals from the sign of
    `pnl` across the grid `S` (bounded by the grid's min/max, plus the
    open-ended tails beyond the grid if the position is profitable at the
    grid's edges and unbounded in that direction), then integrate the
    lognormal density (equivalently, use the lognormal CDF) over each
    profitable sub-interval.
    """
    S = np.asarray(S, dtype=float)
    pnl = np.asarray(pnl, dtype=float)
    T = max(dte_days, 0.0) / DAYS_PER_YEAR
    if T <= 0 or iv <= 0:
        # No time or no vol left -- probability collapses to a certainty
        # given today's price is already fixed: 1.0 if currently profitable.
        return 1.0 if float(np.interp(spot, S, pnl)) >= 0 else 0.0

    mu = np.log(spot) + (r - 0.5 * iv**2) * T
    sigma_T = iv * np.sqrt(T)

    def lognormal_cdf(x: float) -> float:
        if x <= 0:
            return 0.0
        return float(norm.cdf((np.log(x) - mu) / sigma_T))

    # Find contiguous profitable sub-intervals over the grid.
    profitable = pnl >= 0
    intervals: list[tuple[float, float]] = []
    start_idx = None
    for i, is_profit in enumerate(profitable):
        if is_profit and start_idx is None:
            start_idx = i
        elif not is_profit and start_idx is not None:
            intervals.append((float(S[start_idx]), float(S[i - 1])))
            start_idx = None
    if start_idx is not None:
        intervals.append((float(S[start_idx]), float(S[-1])))

    if not intervals:
        return 0.0

    prob = 0.0
    grid_min, grid_max = float(S[0]), float(S[-1])
    for lo, hi in intervals:
        lo_bound = 0.0 if lo <= grid_min else lo
        hi_bound = float("inf") if hi >= grid_max else hi
        cdf_hi = 1.0 if hi_bound == float("inf") else lognormal_cdf(hi_bound)
        cdf_lo = lognormal_cdf(lo_bound) if lo_bound > 0 else 0.0
        prob += max(cdf_hi - cdf_lo, 0.0)

    return float(np.clip(prob, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Convenience: full stats bundle for the UI's key-stats bar
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PayoffStats:
    net_entry_cost: float  # positive = net debit, negative = net credit
    max_profit: MaxPnL
    max_loss: MaxPnL
    breakevens: list[float]
    probability_of_profit: float
    greeks: PositionGreeks


def compute_stats(
    priced_legs: list[PricedLeg],
    S: np.ndarray,
    expiration_pnl: np.ndarray,
    spot: float,
    r: float,
    q: float,
    iv_fn,
    position_iv_estimate: float,
    max_dte_days: float,
) -> PayoffStats:
    """Bundle every stat the key-stats bar / Greeks strip needs, computed
    off the same expiration payoff array used to draw the chart (so the
    profit table and chart can never silently disagree with the stats bar).
    """
    cost = net_entry_cost(priced_legs)
    max_profit, max_loss = max_profit_loss(priced_legs, S, expiration_pnl)
    breakevens = find_breakevens(S, expiration_pnl)
    pop = probability_of_profit(S, expiration_pnl, spot, position_iv_estimate, max_dte_days, r)
    greeks = position_greeks(priced_legs, spot, r, q, iv_fn, days_elapsed=0.0)
    return PayoffStats(
        net_entry_cost=cost,
        max_profit=max_profit,
        max_loss=max_loss,
        breakevens=breakevens,
        probability_of_profit=pop,
        greeks=greeks,
    )
