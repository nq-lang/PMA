"""
engine/strategies.py
=====================

Strategy -> leg-set factory. Given a strategy name, a simulated spot price,
a strike increment, and a default DTE, produces a list of `Leg` objects
(the same primitive the custom leg-builder uses) with sensible default
relative strikes (spec §4: "ATM +/- one strike increment"-style defaults).

Every value produced here is **user-editable afterward** — this module
only picks reasonable starting points. The custom leg-builder in the UI
(spec §3.9) operates on the exact same `Leg` primitive, so any preset can
be reproduced or modified manually, and arbitrary combinations beyond the
presets are just lists of `Leg`.

A `Leg` is intentionally minimal and instrument-agnostic:
    kind:       "call" | "put" | "stock"
    direction:  +1 (long) or -1 (short)
    quantity:   number of contracts (or, for stock, number of 100-share
                lots, to keep position-Greek scaling uniform — see
                engine/payoff.py's docstring for the stock convention)
    strike:     option strike price (ignored for stock legs; kept as the
                reference/entry price for stock legs so premium/basis math
                has a consistent field to read)
    dte_days:   days to expiration for this leg (ignored for stock legs)
    label:      short display label, e.g. "280C", "525C x2" (UI convenience)
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

Kind = str  # "call" | "put" | "stock"


@dataclass
class Leg:
    kind: Kind  # "call", "put", or "stock"
    direction: int  # +1 long, -1 short
    quantity: float  # contracts (or 100-share lots for stock)
    strike: float  # strike price; for stock, the reference/entry price
    dte_days: float  # days to expiration; ignored for stock legs
    iv: float | None = None       # per-leg implied vol override (decimal); None = simulated
    premium: float | None = None  # custom per-share premium/entry price; None = model estimate

    def label(self) -> str:
        qty_suffix = f" x{int(self.quantity)}" if self.quantity != 1 else ""
        if self.kind == "stock":
            side = "Long Stock" if self.direction > 0 else "Short Stock"
            return f"{side}{qty_suffix}"
        strike_str = _fmt_strike(self.strike)
        type_letter = "C" if self.kind == "call" else "P"
        sign = "" if self.direction > 0 else "-"
        return f"{sign}{strike_str}{type_letter}{qty_suffix}"


def _fmt_strike(strike: float) -> str:
    if float(strike).is_integer():
        return str(int(strike))
    return f"{strike:g}"


def _round_to_increment(price: float, increment: float) -> float:
    if increment <= 0:
        return round(price, 2)
    return round(round(price / increment) * increment, 2)


# ---------------------------------------------------------------------------
# Strategy factory functions
#
# Each factory has signature (spot, increment, dte_days) -> list[Leg] and is
# registered in STRATEGY_REGISTRY below under its canonical display name.
# `dte_days` is the *default* single DTE used for same-expiration strategies;
# time-spread strategies (calendar/diagonal) use it as the near-leg DTE and
# derive a longer far-leg DTE from it.
# ---------------------------------------------------------------------------


def _atm(spot: float, increment: float) -> float:
    return _round_to_increment(spot, increment)


def _strike_at(spot: float, increment: float, steps: int) -> float:
    """`steps` strike-increments away from ATM (positive = above spot)."""
    return _round_to_increment(spot, increment) + steps * increment


# -- Single-leg --------------------------------------------------------------


def long_call(spot, inc, dte):
    return [Leg("call", +1, 1, _atm(spot, inc), dte)]


def short_call(spot, inc, dte):
    return [Leg("call", -1, 1, _atm(spot, inc), dte)]


def long_put(spot, inc, dte):
    return [Leg("put", +1, 1, _atm(spot, inc), dte)]


def short_put(spot, inc, dte):
    return [Leg("put", -1, 1, _atm(spot, inc), dte)]


def long_stock(spot, inc, dte):
    return [Leg("stock", +1, 1, spot, dte)]


def short_stock(spot, inc, dte):
    return [Leg("stock", -1, 1, spot, dte)]


# -- Vertical spreads ----------------------------------------------------


def bull_call_spread(spot, inc, dte):
    return [
        Leg("call", +1, 1, _strike_at(spot, inc, 0), dte),
        Leg("call", -1, 1, _strike_at(spot, inc, 2), dte),
    ]


def bear_call_spread(spot, inc, dte):
    return [
        Leg("call", -1, 1, _strike_at(spot, inc, 0), dte),
        Leg("call", +1, 1, _strike_at(spot, inc, 2), dte),
    ]


def bull_put_spread(spot, inc, dte):
    return [
        Leg("put", +1, 1, _strike_at(spot, inc, -2), dte),
        Leg("put", -1, 1, _strike_at(spot, inc, 0), dte),
    ]


def bear_put_spread(spot, inc, dte):
    return [
        Leg("put", -1, 1, _strike_at(spot, inc, -2), dte),
        Leg("put", +1, 1, _strike_at(spot, inc, 0), dte),
    ]


# -- Volatility / straddle family ----------------------------------------


def long_straddle(spot, inc, dte):
    k = _atm(spot, inc)
    return [Leg("call", +1, 1, k, dte), Leg("put", +1, 1, k, dte)]


def short_straddle(spot, inc, dte):
    k = _atm(spot, inc)
    return [Leg("call", -1, 1, k, dte), Leg("put", -1, 1, k, dte)]


def long_strangle(spot, inc, dte):
    return [
        Leg("call", +1, 1, _strike_at(spot, inc, 1), dte),
        Leg("put", +1, 1, _strike_at(spot, inc, -1), dte),
    ]


def short_strangle(spot, inc, dte):
    return [
        Leg("call", -1, 1, _strike_at(spot, inc, 1), dte),
        Leg("put", -1, 1, _strike_at(spot, inc, -1), dte),
    ]


def strap(spot, inc, dte):
    """2 long calls + 1 long put at ATM — bullish-biased volatility play
    (as referenced in the project's reference screenshot)."""
    k = _atm(spot, inc)
    return [Leg("call", +1, 2, k, dte), Leg("put", +1, 1, k, dte)]


def strip(spot, inc, dte):
    """1 long call + 2 long puts at ATM — bearish-biased volatility play."""
    k = _atm(spot, inc)
    return [Leg("call", +1, 1, k, dte), Leg("put", +1, 2, k, dte)]


# -- Time spreads ----------------------------------------------------------

_CALENDAR_FAR_DTE_MULTIPLIER = 3.0  # far leg default = 3x the near leg's DTE


def calendar_call_spread(spot, inc, dte):
    k = _atm(spot, inc)
    far_dte = dte * _CALENDAR_FAR_DTE_MULTIPLIER
    return [
        Leg("call", -1, 1, k, dte),
        Leg("call", +1, 1, k, far_dte),
    ]


def calendar_put_spread(spot, inc, dte):
    k = _atm(spot, inc)
    far_dte = dte * _CALENDAR_FAR_DTE_MULTIPLIER
    return [
        Leg("put", -1, 1, k, dte),
        Leg("put", +1, 1, k, far_dte),
    ]


def diagonal_spread(spot, inc, dte):
    """Long a further-dated, further-OTM call; short a nearer-dated,
    nearer-the-money call — a bullish calendar/diagonal hybrid."""
    far_dte = dte * _CALENDAR_FAR_DTE_MULTIPLIER
    return [
        Leg("call", -1, 1, _strike_at(spot, inc, 1), dte),
        Leg("call", +1, 1, _strike_at(spot, inc, 2), far_dte),
    ]


# -- Wing / butterfly / condor family --------------------------------------


def long_call_butterfly(spot, inc, dte):
    return [
        Leg("call", +1, 1, _strike_at(spot, inc, -2), dte),
        Leg("call", -1, 2, _strike_at(spot, inc, 0), dte),
        Leg("call", +1, 1, _strike_at(spot, inc, 2), dte),
    ]


def long_put_butterfly(spot, inc, dte):
    return [
        Leg("put", +1, 1, _strike_at(spot, inc, -2), dte),
        Leg("put", -1, 2, _strike_at(spot, inc, 0), dte),
        Leg("put", +1, 1, _strike_at(spot, inc, 2), dte),
    ]


def iron_butterfly(spot, inc, dte):
    k = _atm(spot, inc)
    return [
        Leg("put", +1, 1, _strike_at(spot, inc, -2), dte),
        Leg("put", -1, 1, k, dte),
        Leg("call", -1, 1, k, dte),
        Leg("call", +1, 1, _strike_at(spot, inc, 2), dte),
    ]


def long_call_condor(spot, inc, dte):
    return [
        Leg("call", +1, 1, _strike_at(spot, inc, -3), dte),
        Leg("call", -1, 1, _strike_at(spot, inc, -1), dte),
        Leg("call", -1, 1, _strike_at(spot, inc, 1), dte),
        Leg("call", +1, 1, _strike_at(spot, inc, 3), dte),
    ]


def long_put_condor(spot, inc, dte):
    return [
        Leg("put", +1, 1, _strike_at(spot, inc, -3), dte),
        Leg("put", -1, 1, _strike_at(spot, inc, -1), dte),
        Leg("put", -1, 1, _strike_at(spot, inc, 1), dte),
        Leg("put", +1, 1, _strike_at(spot, inc, 3), dte),
    ]


def iron_condor(spot, inc, dte):
    return [
        Leg("put", +1, 1, _strike_at(spot, inc, -3), dte),
        Leg("put", -1, 1, _strike_at(spot, inc, -1), dte),
        Leg("call", -1, 1, _strike_at(spot, inc, 1), dte),
        Leg("call", +1, 1, _strike_at(spot, inc, 3), dte),
    ]


# -- Combo / synthetic / collar family --------------------------------------


def collar(spot, inc, dte):
    return [
        Leg("stock", +1, 1, spot, dte),
        Leg("put", +1, 1, _strike_at(spot, inc, -1), dte),
        Leg("call", -1, 1, _strike_at(spot, inc, 1), dte),
    ]


def covered_call(spot, inc, dte):
    return [
        Leg("stock", +1, 1, spot, dte),
        Leg("call", -1, 1, _strike_at(spot, inc, 1), dte),
    ]


def protective_put(spot, inc, dte):
    return [
        Leg("stock", +1, 1, spot, dte),
        Leg("put", +1, 1, _strike_at(spot, inc, -1), dte),
    ]


def married_put(spot, inc, dte):
    """Protective put opened simultaneously with the stock purchase, at
    the ATM strike (distinct default from protective_put's slightly-OTM
    put, matching common usage where 'married put' implies same-day, ATM
    protection)."""
    return [
        Leg("stock", +1, 1, spot, dte),
        Leg("put", +1, 1, _atm(spot, inc), dte),
    ]


def synthetic_long_stock(spot, inc, dte):
    k = _atm(spot, inc)
    return [Leg("call", +1, 1, k, dte), Leg("put", -1, 1, k, dte)]


def synthetic_short_stock(spot, inc, dte):
    k = _atm(spot, inc)
    return [Leg("call", -1, 1, k, dte), Leg("put", +1, 1, k, dte)]


def ratio_call_spread(spot, inc, dte):
    """Call backspread: short 1 near-the-money call, long 2 further OTM
    calls -- net long vega/gamma to the upside."""
    return [
        Leg("call", -1, 1, _strike_at(spot, inc, 0), dte),
        Leg("call", +1, 2, _strike_at(spot, inc, 2), dte),
    ]


def ratio_put_spread(spot, inc, dte):
    """Put backspread: short 1 near-the-money put, long 2 further OTM puts
    -- net long vega/gamma to the downside."""
    return [
        Leg("put", -1, 1, _strike_at(spot, inc, 0), dte),
        Leg("put", +1, 2, _strike_at(spot, inc, -2), dte),
    ]


def custom(spot, inc, dte):
    """Custom mode starts blank; the UI's Add Leg control populates it."""
    return []


# ---------------------------------------------------------------------------
# Registry: canonical display name -> factory function
# ---------------------------------------------------------------------------

STRATEGY_REGISTRY: dict[str, Callable[[float, float, float], list[Leg]]] = {
    # Single-leg
    "Long Call": long_call,
    "Short Call": short_call,
    "Long Put": long_put,
    "Short Put": short_put,
    "Long Stock": long_stock,
    "Short Stock": short_stock,
    # Vertical spreads
    "Bull Call Spread": bull_call_spread,
    "Bear Call Spread": bear_call_spread,
    "Bull Put Spread": bull_put_spread,
    "Bear Put Spread": bear_put_spread,
    # Volatility / straddle family
    "Long Straddle": long_straddle,
    "Short Straddle": short_straddle,
    "Long Strangle": long_strangle,
    "Short Strangle": short_strangle,
    "Strap": strap,
    "Strip": strip,
    # Time spreads
    "Calendar Call Spread": calendar_call_spread,
    "Calendar Put Spread": calendar_put_spread,
    "Diagonal Spread": diagonal_spread,
    # Wing / butterfly / condor family
    "Long Call Butterfly": long_call_butterfly,
    "Long Put Butterfly": long_put_butterfly,
    "Iron Butterfly": iron_butterfly,
    "Long Call Condor": long_call_condor,
    "Long Put Condor": long_put_condor,
    "Iron Condor": iron_condor,
    # Combo / synthetic / collar family
    "Collar": collar,
    "Covered Call": covered_call,
    "Protective Put": protective_put,
    "Married Put": married_put,
    "Synthetic Long Stock": synthetic_long_stock,
    "Synthetic Short Stock": synthetic_short_stock,
    "Ratio Call Spread": ratio_call_spread,
    "Ratio Put Spread": ratio_put_spread,
    # Custom
    "Custom": custom,
}

# Grouping metadata for the UI's searchable/typeahead dropdown (spec §3.1),
# so the strategy list can be rendered with section headers matching §4.
STRATEGY_GROUPS: dict[str, list[str]] = {
    "Single-leg": [
        "Long Call",
        "Short Call",
        "Long Put",
        "Short Put",
        "Long Stock",
        "Short Stock",
    ],
    "Vertical spreads": [
        "Bull Call Spread",
        "Bear Call Spread",
        "Bull Put Spread",
        "Bear Put Spread",
    ],
    "Volatility / straddle family": [
        "Long Straddle",
        "Short Straddle",
        "Long Strangle",
        "Short Strangle",
        "Strap",
        "Strip",
    ],
    "Time spreads": [
        "Calendar Call Spread",
        "Calendar Put Spread",
        "Diagonal Spread",
    ],
    "Wing / butterfly / condor family": [
        "Long Call Butterfly",
        "Long Put Butterfly",
        "Iron Butterfly",
        "Long Call Condor",
        "Long Put Condor",
        "Iron Condor",
    ],
    "Combo / synthetic / collar family": [
        "Collar",
        "Covered Call",
        "Protective Put",
        "Married Put",
        "Synthetic Long Stock",
        "Synthetic Short Stock",
        "Ratio Call Spread",
        "Ratio Put Spread",
    ],
    "Custom": ["Custom"],
}

DEFAULT_DTE_DAYS = 30.0


def build_strategy_legs(
    strategy_name: str,
    spot: float,
    strike_increment: float = 5.0,
    dte_days: float = DEFAULT_DTE_DAYS,
) -> list[Leg]:
    """Look up and invoke the factory for `strategy_name`, returning a
    fresh list of `Leg` objects with default relative strikes around
    `spot`. Raises KeyError with a helpful message for unknown strategy
    names (callers should validate against STRATEGY_REGISTRY keys, e.g.
    for a dropdown's options list)."""
    try:
        factory = STRATEGY_REGISTRY[strategy_name]
    except KeyError as exc:
        raise KeyError(
            f"Unknown strategy {strategy_name!r}. "
            f"Valid options: {sorted(STRATEGY_REGISTRY.keys())}"
        ) from exc
    return factory(spot, strike_increment, dte_days)


def clone_legs(legs: list[Leg]) -> list[Leg]:
    """Deep-enough copy of a leg list (each Leg is a small immutable-ish
    dataclass of scalars, so a shallow per-item copy suffices) — used by
    the UI when duplicating a strategy config before editing, and by tests
    that mutate a returned leg list without affecting the factory."""
    return [replace(leg) for leg in legs]
