"""
ui/ruler.py
===========
Strike ruler (spec §3.4): a horizontal ruler with one draggable chip per option
leg (green=long, red=short) plus a spot marker. Rendered as plain HTML; drag
behaviour is a small global JS handler (RULER_JS) that snaps to the strike
increment and emits a 'ruler_drag' event {idx, strike} to Python on release.
"""
from __future__ import annotations

import math

from engine.strategies import Leg

RULER_JS = """
<script>
(function () {
  if (window.__rulerInstalled) return; window.__rulerInstalled = true;
  let drag = null;
  document.addEventListener('pointerdown', (e) => {
    const chip = e.target.closest('.ruler-chip'); if (!chip) return;
    const ruler = chip.closest('.ruler'); if (!ruler) return;
    drag = {chip, ruler, idx: parseInt(chip.dataset.idx), strike: null};
    chip.setPointerCapture(e.pointerId); e.preventDefault();
  });
  document.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const r = drag.ruler, rect = r.getBoundingClientRect();
    const lo = parseFloat(r.dataset.lo), hi = parseFloat(r.dataset.hi), inc = parseFloat(r.dataset.inc);
    let pct = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    let strike = Math.round((lo + pct * (hi - lo)) / inc) * inc;
    strike = Math.min(hi, Math.max(lo, strike));
    drag.strike = strike;
    drag.chip.style.left = ((strike - lo) / (hi - lo) * 100) + '%';
    drag.chip.querySelector('.ruler-strike').textContent = strike;
  });
  document.addEventListener('pointerup', () => {
    if (!drag) return;
    if (drag.strike !== null) emitEvent('ruler_drag', {idx: drag.idx, strike: drag.strike});
    drag = null;
  });
})();
</script>
"""

RULER_CSS = """
.ruler { position: relative; height: 92px; margin: 8px 24px 4px 24px; user-select: none; touch-action: none; }
.ruler-line { position: absolute; left: 0; right: 0; top: 46px; height: 2px; background: var(--border-strong); }
.ruler-tick { position: absolute; top: 40px; width: 1px; height: 14px; background: var(--border-strong); }
.ruler-tick-label { position: absolute; top: 58px; transform: translateX(-50%); font-size: 10px; color: var(--text-muted); }
.ruler-spot { position: absolute; top: 14px; bottom: 14px; width: 0; border-left: 2px dotted var(--accent-blue); }
.ruler-spot-label { position: absolute; top: -2px; transform: translateX(-50%); font-size: 10px; color: var(--accent-blue); white-space: nowrap; }
.ruler-chip { position: absolute; transform: translateX(-50%); cursor: grab; padding: 2px 8px; border-radius: 999px;
  font-family: monospace; font-size: 12px; font-weight: 600; white-space: nowrap; z-index: 5; }
.ruler-chip.long { background: rgba(32,214,123,.18); color: var(--profit-green); border: 1px solid rgba(32,214,123,.5); }
.ruler-chip.short { background: rgba(255,92,92,.18); color: var(--loss-red); border: 1px solid rgba(255,92,92,.5); }
.ruler-chip:active { cursor: grabbing; }
"""


def ruler_bounds(legs: list[Leg], spot: float, inc: float) -> tuple[float, float]:
    strikes = [l.strike for l in legs if l.kind != "stock"] + [spot]
    lo = min(min(strikes), spot * 0.85) - 2 * inc
    hi = max(max(strikes), spot * 1.15) + 2 * inc
    lo = math.floor(lo / inc) * inc
    hi = math.ceil(hi / inc) * inc
    return max(lo, inc), hi


def snap_strike(lo: float, hi: float, pct: float, inc: float) -> float:
    pct = min(1.0, max(0.0, pct))
    return min(hi, max(lo, round((lo + pct * (hi - lo)) / inc) * inc))


def build_ruler_html(legs: list[Leg], spot: float, inc: float) -> str:
    lo, hi = ruler_bounds(legs, spot, inc)
    span = hi - lo
    pos = lambda v: (v - lo) / span * 100.0
    n_ticks = 8
    tick_step = max(inc, round(span / n_ticks / inc) * inc)
    parts = [f'<div class="ruler" data-lo="{lo}" data-hi="{hi}" data-inc="{inc}">',
             '<div class="ruler-line"></div>']
    t = math.ceil(lo / tick_step) * tick_step
    while t <= hi:
        parts.append(f'<div class="ruler-tick" style="left:{pos(t):.3f}%"></div>'
                     f'<div class="ruler-tick-label" style="left:{pos(t):.3f}%">{t:g}</div>')
        t += tick_step
    parts.append(f'<div class="ruler-spot" style="left:{pos(spot):.3f}%"></div>'
                 f'<div class="ruler-spot-label" style="left:{pos(spot):.3f}%">Spot {spot:,.2f}</div>')
    levels: list[list[float]] = []   # x-positions (%) already used on each row
    min_gap = 9.0                    # chips closer than this (% of ruler width) go to the next row
    for idx, leg in enumerate(legs):
        if leg.kind == "stock":
            continue
        x = pos(leg.strike)
        level = next((i for i, xs in enumerate(levels) if all(abs(x - o) >= min_gap for o in xs)), len(levels))
        if level == len(levels):
            levels.append([])
        levels[level].append(x)
        side = "long" if leg.direction > 0 else "short"
        top = 20 + level * 26
        parts.append(
            f'<div class="ruler-chip {side}" data-idx="{idx}" style="left:{pos(leg.strike):.3f}%;top:{top}px">'
            f'{"+" if leg.direction > 0 else "-"}<span class="ruler-strike">{leg.strike:g}</span>'
            f'{"C" if leg.kind == "call" else "P"}{f" x{int(leg.quantity)}" if leg.quantity != 1 else ""}</div>'
        )
    parts.append("</div>")
    return "".join(parts)
