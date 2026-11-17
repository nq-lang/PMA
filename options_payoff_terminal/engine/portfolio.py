"""
engine/portfolio.py
====================
Event-driven multi-asset ledger: equities, ETFs, options, futures.

Events (all O(1) per holding, no full recompute needed by callers):
    apply_tick, apply_fill, apply_dividend, expire_option, accrue_carry

Conventions
-----------
* qty is signed (+long / -short): shares, option contracts, futures contracts.
* ``multiplier`` converts a price quote to dollars per unit (1 shares,
  100 equity options, contract multiplier for futures).
* Cash model: equities/options settle premium/notional into cash immediately;
  futures move cash only on fees and on REALIZED P&L (daily variation is
  carried as unrealized market value).
* **Margin is a SIMPLIFIED model** (see ``margin()``). Futures use
  ``engine.futures`` registry values, which are placeholders until a live
  exchange adapter supplies them. Do not treat as broker-accurate.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Iterable

from engine import futures as fut

ASSET_CLASSES = ("equity", "etf", "option", "future")


@dataclass
class Holding:
    symbol: str                 # unique key, e.g. "AAPL", "AAPL 250C 2026-12-18", "ES"
    asset_class: str
    underlying: str
    qty: float
    avg_cost: float             # per-unit quote (share px / premium per share / futures entry)
    multiplier: float = 1.0
    mark: float | None = None
    beta: float = 1.0           # vs primary benchmark
    delta: float = 1.0          # delta of the instrument wrt its underlying (1 for linear)
    underlying_mark: float | None = None   # needed for option notional/margin
    strike: float | None = None
    right: str | None = None    # "call" | "put"
    sleeve: str = ""            # user-defined thematic group
    strategy: str = ""          # strategy archetype tag
    expiry: str | None = None   # ISO date

    def __post_init__(self):
        if self.asset_class not in ASSET_CLASSES:
            raise ValueError(f"asset_class must be one of {ASSET_CLASSES}")
        if self.mark is None:
            self.mark = self.avg_cost

    @property
    def is_future(self) -> bool:
        return self.asset_class == "future"

    @property
    def market_value(self) -> float:
        """Contribution to NLV. Futures carry only unrealized P&L."""
        if self.is_future:
            return self.unrealized
        return self.qty * self.mark * self.multiplier

    @property
    def unrealized(self) -> float:
        return (self.mark - self.avg_cost) * self.qty * self.multiplier

    @property
    def cost_basis(self) -> float:
        return self.qty * self.avg_cost * self.multiplier

    @property
    def delta_notional(self) -> float:
        """Delta-adjusted dollar exposure to the underlying."""
        ref = self.underlying_mark if self.underlying_mark is not None else self.mark
        return self.qty * self.delta * ref * (self.multiplier if self.asset_class != "equity" and self.asset_class != "etf" else 1.0)


@dataclass
class Event:
    kind: str
    symbol: str
    detail: dict = field(default_factory=dict)


class Ledger:
    def __init__(self, cash: float = 0.0, base_ccy: str = "USD"):
        self.cash = float(cash)
        self.base_ccy = base_ccy
        self.holdings: dict[str, Holding] = {}
        self.realized = 0.0
        self.fees_paid = 0.0
        self.carry_paid = 0.0
        self.events: list[Event] = []
        self.borrow_rates: dict[str, float] = {}   # annual, by symbol
        self.financing_rate = 0.0                  # annual, on negative cash
        self._listeners: list[Callable[[set[str]], None]] = []

    # ------------------------------------------------------------ events
    def subscribe(self, fn: Callable[[set[str]], None]) -> None:
        self._listeners.append(fn)

    def _emit(self, symbols: set[str]) -> None:
        for fn in self._listeners:
            fn(symbols)

    def apply_tick(self, symbol_or_underlying: str, price: float, *, underlying: bool = False) -> set[str]:
        """Update marks. With ``underlying=True`` updates ``underlying_mark``
        on every holding of that underlying; else the holding's own mark.
        Returns the set of changed holding symbols (for targeted re-render)."""
        changed: set[str] = set()
        if underlying:
            for h in self.holdings.values():
                if h.underlying == symbol_or_underlying and h.underlying_mark != price:
                    h.underlying_mark = price
                    if h.asset_class in ("equity", "etf", "future") and h.symbol == symbol_or_underlying:
                        h.mark = price
                    changed.add(h.symbol)
        else:
            h = self.holdings.get(symbol_or_underlying)
            if h is not None and h.mark != price:
                h.mark = price
                if h.asset_class in ("equity", "etf", "future"):
                    h.underlying_mark = price
                changed.add(h.symbol)
        if changed:
            self._emit(changed)
        return changed

    def apply_fill(self, holding: Holding, qty: float, price: float, fee: float = 0.0) -> float:
        """Apply a signed fill. Returns realized P&L from this fill.
        ``holding`` supplies metadata when the position is new."""
        if qty == 0:
            raise ValueError("fill qty must be non-zero")
        sym = holding.symbol
        cur = self.holdings.get(sym)
        realized = 0.0
        mult = holding.multiplier
        if cur is None or cur.qty == 0:
            new = replace(holding, qty=qty, avg_cost=price, mark=price)
            self.holdings[sym] = new
        else:
            same_dir = (qty > 0) == (cur.qty > 0)
            if same_dir:
                tot = cur.qty + qty
                cur.avg_cost = (cur.avg_cost * cur.qty + price * qty) / tot
                cur.qty = tot
            else:
                closing = min(abs(qty), abs(cur.qty))
                sgn = 1 if cur.qty > 0 else -1
                realized = (price - cur.avg_cost) * closing * sgn * mult
                new_qty = cur.qty + qty
                if abs(qty) > abs(cur.qty):          # flipped through zero
                    cur.avg_cost = price
                cur.qty = new_qty
            cur.mark = price
        h = self.holdings[sym]
        # cash effects: futures settle only realized P&L; everything else pays notional
        if h.is_future:
            self.cash += realized
        else:
            self.cash -= qty * price * mult
        self.realized += realized
        self.cash -= fee
        self.fees_paid += fee
        if h.qty == 0:
            del self.holdings[sym]
        self.events.append(Event("fill", sym, {"qty": qty, "price": price, "fee": fee, "realized": realized}))
        self._emit({sym})
        return realized

    def apply_dividend(self, symbol: str, per_share: float) -> float:
        h = self.holdings.get(symbol)
        if h is None or h.asset_class not in ("equity", "etf"):
            return 0.0
        amt = h.qty * per_share            # shorts owe the dividend (negative)
        self.cash += amt
        self.events.append(Event("dividend", symbol, {"per_share": per_share, "amount": amt}))
        self._emit({symbol})
        return amt

    def expire_option(self, symbol: str, settle_underlying: float) -> float:
        """Cash-settle an option at intrinsic value and remove it."""
        h = self.holdings.get(symbol)
        if h is None or h.asset_class != "option":
            raise KeyError(f"no option holding {symbol!r}")
        intrinsic = max(settle_underlying - h.strike, 0.0) if h.right == "call" else max(h.strike - settle_underlying, 0.0)
        realized = (intrinsic - h.avg_cost) * h.qty * h.multiplier
        self.cash += h.qty * intrinsic * h.multiplier
        self.realized += realized
        del self.holdings[symbol]
        self.events.append(Event("expiry", symbol, {"intrinsic": intrinsic, "realized": realized}))
        self._emit({symbol})
        return realized

    def accrue_carry(self, days: float = 1.0) -> float:
        """Borrow fees on shorts and financing on negative cash. Returns total cost."""
        cost = 0.0
        for h in self.holdings.values():
            if h.qty < 0 and h.asset_class in ("equity", "etf"):
                cost += abs(h.market_value) * self.borrow_rates.get(h.symbol, 0.0) * days / 365.0
        if self.cash < 0:
            cost += -self.cash * self.financing_rate * days / 365.0
        self.cash -= cost
        self.carry_paid += cost
        return cost

    # ------------------------------------------------------------ aggregates
    @property
    def unrealized(self) -> float:
        return sum(h.unrealized for h in self.holdings.values())

    @property
    def nlv(self) -> float:
        return self.cash + sum(h.market_value for h in self.holdings.values())

    @property
    def gross_exposure(self) -> float:
        return sum(abs(h.delta_notional) for h in self.holdings.values())

    @property
    def net_exposure(self) -> float:
        return sum(h.delta_notional for h in self.holdings.values())

    def beta_weighted_exposure(self) -> float:
        """Dollar exposure expressed in benchmark terms: sum(delta$ * beta)."""
        return sum(h.delta_notional * h.beta for h in self.holdings.values())

    def margin(self) -> tuple[float, float]:
        """(initial, maintenance) under a SIMPLIFIED model:
        long stock 50%/25% of value; short stock 50%/30% of value;
        long options 0 (paid in full); short options 20% of underlying
        notional + premium (floored at 10% of notional); futures per registry."""
        init = maint = 0.0
        for h in self.holdings.values():
            if h.asset_class in ("equity", "etf"):
                v = abs(h.qty * h.mark)
                if h.qty > 0:
                    init, maint = init + 0.50 * v, maint + 0.25 * v
                else:
                    init, maint = init + 0.50 * v, maint + 0.30 * v
            elif h.asset_class == "option" and h.qty < 0:
                und = (h.underlying_mark or h.strike or 0.0) * h.multiplier * abs(h.qty)
                prem = h.mark * h.multiplier * abs(h.qty)
                req = max(0.20 * und + prem, 0.10 * und + prem)
                init, maint = init + req, maint + req
            elif h.is_future:
                spec = fut.get_spec(h.symbol)
                init += abs(h.qty) * spec.init_margin
                maint += abs(h.qty) * spec.maint_margin
        return init, maint

    @property
    def buying_power(self) -> float:
        return self.nlv - self.margin()[0]

    @property
    def excess_liquidity(self) -> float:
        return self.nlv - self.margin()[1]

    def margin_utilization(self) -> float:
        _, maint = self.margin()
        return maint / self.nlv if self.nlv > 0 else float("inf")

    def summary(self) -> dict:
        init, maint = self.margin()
        return {
            "nlv": self.nlv, "cash": self.cash, "unrealized": self.unrealized,
            "realized": self.realized, "fees": self.fees_paid, "carry": self.carry_paid,
            "gross": self.gross_exposure, "net": self.net_exposure,
            "beta_weighted": self.beta_weighted_exposure(),
            "init_margin": init, "maint_margin": maint,
            "buying_power": self.nlv - init, "excess_liquidity": self.nlv - maint,
            "margin_utilization": self.margin_utilization(),
        }

    def group_by(self, key: str) -> dict[str, dict]:
        """Aggregate by 'underlying' | 'asset_class' | 'sleeve' | 'strategy' | 'expiry'."""
        if key not in ("underlying", "asset_class", "sleeve", "strategy", "expiry"):
            raise ValueError(f"cannot group by {key!r}")
        out: dict[str, dict] = {}
        for h in self.holdings.values():
            k = getattr(h, key) or "(none)"
            g = out.setdefault(k, {"count": 0, "market_value": 0.0, "unrealized": 0.0, "delta_notional": 0.0})
            g["count"] += 1
            g["market_value"] += h.market_value
            g["unrealized"] += h.unrealized
            g["delta_notional"] += h.delta_notional
        return out
