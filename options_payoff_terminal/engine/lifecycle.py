"""
engine/lifecycle.py
====================
Strategy-lifecycle detection: turns a flat fill history into *position
threads* per underlying, so covered calls, cash-secured puts, wheels,
collars and rolls are tracked as one continuous trade with a true
cumulative cost basis and annualized return on capital.

Conventions
-----------
* Fill.qty is signed (+buy / -sell); stock in shares, options in contracts (x100).
* Assignment/exercise: record the option close with price 0 (``note="assigned"``)
  and the resulting stock fill at the strike (``note="assigned"``).
* A thread starts at the first fill on an underlying and ends when every
  position in it is flat.
* Adjusted cost basis per share = (net stock cash outlay - net option cash
  collected, incl. every roll credit/debit and fee) / shares held.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

OPT_MULT = 100.0


@dataclass(frozen=True)
class Fill:
    ts: str                     # ISO date "YYYY-MM-DD"
    underlying: str
    kind: str                   # "stock" | "call" | "put"
    qty: float
    price: float
    strike: float | None = None
    expiry: str | None = None
    fee: float = 0.0
    note: str = ""

    @property
    def mult(self) -> float:
        return 1.0 if self.kind == "stock" else OPT_MULT

    @property
    def cash(self) -> float:
        return -self.qty * self.price * self.mult - self.fee

    @property
    def key(self) -> tuple:
        return ("stock",) if self.kind == "stock" else (self.kind, self.strike, self.expiry)


@dataclass
class Roll:
    ts: str
    kind: str
    from_leg: tuple
    to_leg: tuple
    net_cash: float             # >0 credit, <0 debit (incl. fees)


@dataclass
class Thread:
    underlying: str
    start: str
    end: str | None = None
    fills: list[Fill] = field(default_factory=list)
    rolls: list[Roll] = field(default_factory=list)
    positions: dict = field(default_factory=dict)      # key -> [qty, avg]
    realized: float = 0.0
    cash: float = 0.0
    stock_cash: float = 0.0
    option_cash: float = 0.0
    peak_capital: float = 0.0
    was_wheel: bool = False

    # ---- derived -----------------------------------------------------
    @property
    def shares(self) -> float:
        return self.positions.get(("stock",), [0.0, 0.0])[0]

    @property
    def archetype(self) -> str:
        return classify(self.positions) if self.positions else ("Wheel (closed)" if self.was_wheel else "Closed")

    def adjusted_cost_basis(self) -> float | None:
        """Per-share basis net of all option premium (None if no stock held)."""
        if self.shares <= 0:
            return None
        return (-self.stock_cash - self.option_cash) / self.shares

    def net_pnl(self, marks: dict | None = None) -> float:
        marks = marks or {}
        unreal = 0.0
        for k, (q, avg) in self.positions.items():
            m = marks.get(k, avg)
            unreal += (m - avg) * q * (1.0 if k == ("stock",) else OPT_MULT)
        return self.realized + unreal

    def annualized_return(self, as_of: str | None = None, marks: dict | None = None) -> float | None:
        if self.peak_capital <= 0:
            return None
        end = self.end or as_of or self.fills[-1].ts
        days = max((date.fromisoformat(end) - date.fromisoformat(self.start)).days, 1)
        return self.net_pnl(marks) / self.peak_capital * 365.0 / days


def classify(positions: dict) -> str:
    shares = positions.get(("stock",), [0.0, 0])[0]
    def tot(kind, sign):
        return sum(q for k, (q, _) in positions.items() if k[0] == kind and q * sign > 0) * sign
    short_calls, short_puts = tot("call", -1), tot("put", -1)
    long_puts, long_calls = tot("put", 1), tot("call", 1)
    if shares >= OPT_MULT:
        if short_calls and long_puts:
            return "Protective collar"
        if short_calls:
            return "Covered call"
        if long_puts:
            return "Protective put"
        return "Long stock"
    if shares == 0:
        if short_puts and not (short_calls or long_puts or long_calls):
            return "Cash-secured put"
        if long_calls and short_calls and not (short_puts or long_puts):
            return "Call spread/calendar"
        if short_calls and not (short_puts or long_puts or long_calls):
            return "Naked call"
    return "Custom"


def _apply(thread: Thread, f: Fill) -> None:
    pos = thread.positions.setdefault(f.key, [0.0, 0.0])
    q, avg = pos
    if q == 0 or (q > 0) == (f.qty > 0):
        tot = q + f.qty
        pos[1] = (avg * q + f.price * f.qty) / tot if tot else 0.0
        pos[0] = tot
    else:
        closing = min(abs(f.qty), abs(q))
        sgn = 1 if q > 0 else -1
        thread.realized += (f.price - avg) * closing * sgn * f.mult
        newq = q + f.qty
        if abs(f.qty) > abs(q):
            pos[1] = f.price
        pos[0] = newq
    if abs(pos[0]) < 1e-12:
        del thread.positions[f.key]
    thread.realized -= f.fee
    thread.cash += f.cash
    if f.kind == "stock":
        thread.stock_cash += f.cash
    else:
        thread.option_cash += f.cash


def _capital(thread: Thread) -> float:
    cap = 0.0
    for k, (q, avg) in thread.positions.items():
        if k == ("stock",) and q > 0:
            cap += q * avg
        elif k[0] == "put" and q < 0:
            cap += abs(q) * k[1] * OPT_MULT        # cash-secured collateral
    return cap


def _detect_roll(thread: Thread, f: Fill, window_days: int) -> None:
    """If ``f`` opens an option leg right after the same kind/direction was
    closed (different strike/expiry) record a roll with the net credit/debit."""
    if f.kind == "stock":
        return
    d = date.fromisoformat(f.ts)
    for prev in reversed(thread.fills[:-1]):
        if (d - date.fromisoformat(prev.ts)).days > window_days:
            break
        closes_same_side = (prev.kind == f.kind and prev.qty * f.qty < 0 and prev.key != f.key
                            and prev.note != "assigned")
        already = any(r.from_leg == prev.key and r.ts == prev.ts for r in thread.rolls)
        # prev closed a leg that had direction == f's direction (e.g. BTC short call, STO new call)
        if closes_same_side and not already and prev.price > 0:
            thread.rolls.append(Roll(f.ts, f.kind, prev.key, f.key, prev.cash + f.cash))
            return


def build_threads(fills: list[Fill], roll_window_days: int = 1) -> list[Thread]:
    """Group fills into per-underlying position threads (chronological)."""
    threads: list[Thread] = []
    open_by_und: dict[str, Thread] = {}
    ordered = sorted(fills, key=lambda x: x.ts)           # stable: keeps same-day order
    last_idx = {(g.underlying, g.ts): i for i, g in enumerate(ordered)}
    for i, f in enumerate(ordered):
        th = open_by_und.get(f.underlying)
        if th is None:
            th = Thread(f.underlying, f.ts)
            open_by_und[f.underlying] = th
            threads.append(th)
        th.fills.append(f)
        _apply(th, f)
        _detect_roll(th, f, roll_window_days)
        th.peak_capital = max(th.peak_capital, _capital(th))
        if f.kind == "stock" and f.note == "assigned" and f.qty > 0:
            th.was_wheel = True
        # flat only counts at the day's last fill (assignment closes the option
        # before the stock arrives; that must not split the thread)
        if not th.positions and last_idx[(f.underlying, f.ts)] == i:
            th.end = f.ts
            del open_by_und[f.underlying]
    return threads
