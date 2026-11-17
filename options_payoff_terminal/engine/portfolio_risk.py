"""
engine/portfolio_risk.py
=========================
Portfolio analytics on return series / exposure vectors (pure numpy).
"""
from __future__ import annotations

import numpy as np


def sharpe(returns, rf_per_period: float = 0.0, periods_per_year: int = 252) -> float:
    r = np.asarray(returns, dtype=float) - rf_per_period
    sd = r.std(ddof=1)
    return float(r.mean() / sd * np.sqrt(periods_per_year)) if sd > 0 else float("nan")


def sortino(returns, mar_per_period: float = 0.0, periods_per_year: int = 252) -> float:
    r = np.asarray(returns, dtype=float) - mar_per_period
    downside = np.sqrt(np.mean(np.minimum(r, 0.0) ** 2))
    return float(r.mean() / downside * np.sqrt(periods_per_year)) if downside > 0 else float("nan")


def max_drawdown(equity) -> float:
    """Most negative peak-to-trough fraction (<= 0)."""
    e = np.asarray(equity, dtype=float)
    peak = np.maximum.accumulate(e)
    return float(np.min(e / peak - 1.0))


def cvar(returns, alpha: float = 0.95) -> float:
    """Expected shortfall: mean of the worst (1-alpha) tail (negative number = loss)."""
    r = np.sort(np.asarray(returns, dtype=float))
    k = max(int(np.ceil((1 - alpha) * len(r))), 1)
    return float(r[:k].mean())


def correlation_matrix(returns_by_symbol: dict[str, np.ndarray]) -> tuple[list[str], np.ndarray]:
    names = sorted(returns_by_symbol)
    return names, np.corrcoef(np.vstack([np.asarray(returns_by_symbol[n], float) for n in names]))


def covariance_matrix(returns_by_symbol: dict[str, np.ndarray]) -> tuple[list[str], np.ndarray]:
    names = sorted(returns_by_symbol)
    return names, np.cov(np.vstack([np.asarray(returns_by_symbol[n], float) for n in names]))


def portfolio_variance(exposures_usd: np.ndarray, cov: np.ndarray) -> float:
    """Variance (in $^2 per period) of dollar exposures w under covariance of returns."""
    w = np.asarray(exposures_usd, dtype=float)
    return float(w @ cov @ w)


def trade_impact(names: list[str], cov: np.ndarray, current: dict[str, float],
                 trade: dict[str, float], nlv: float, margin_before: float,
                 margin_added: float) -> dict:
    """Pre-trade what-if: change in daily $ volatility and margin cushion."""
    w0 = np.array([current.get(n, 0.0) for n in names])
    w1 = w0 + np.array([trade.get(n, 0.0) for n in names])
    v0, v1 = np.sqrt(portfolio_variance(w0, cov)), np.sqrt(portfolio_variance(w1, cov))
    return {
        "vol_before": float(v0), "vol_after": float(v1), "vol_change": float(v1 - v0),
        "cushion_before": nlv - margin_before, "cushion_after": nlv - margin_before - margin_added,
    }


def concentration(exposures_usd: dict[str, float]) -> dict:
    """Herfindahl index and top weight on absolute exposures."""
    a = np.abs(np.array(list(exposures_usd.values()), dtype=float))
    tot = a.sum()
    if tot == 0:
        return {"hhi": 0.0, "top": None, "top_weight": 0.0}
    w = a / tot
    names = list(exposures_usd)
    i = int(np.argmax(w))
    return {"hhi": float((w ** 2).sum()), "top": names[i], "top_weight": float(w[i])}
