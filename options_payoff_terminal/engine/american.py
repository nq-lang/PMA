"""
engine/american.py
===================
American option pricing via a Cox-Ross-Rubinstein binomial tree with a
continuous dividend yield ``q`` (early exercise checked at every node).

Vectorized across the underlying-price axis, so a whole payoff grid is
priced in one call. Pure numerics: no UI, no simulated data.
Per-share units, same conventions as ``engine/pricing.py``.
"""
from __future__ import annotations

import numpy as np

from engine.pricing import OptionType, intrinsic_value


def american_price(
    S, K: float, r: float, q: float, sigma: float, T: float,
    option_type: OptionType, steps: int = 200,
):
    """American option value (scalar or array ``S``)."""
    if option_type not in ("call", "put"):
        raise ValueError(f"option_type must be 'call' or 'put', got {option_type!r}")
    S_arr = np.atleast_1d(np.asarray(S, dtype=float))
    scalar = np.isscalar(S)
    if T <= 0 or sigma <= 0:
        out = intrinsic_value(S_arr, K, option_type)
        return float(out[0]) if scalar else out

    n = int(steps)
    dt = T / n
    u = np.exp(sigma * np.sqrt(dt))
    d = 1.0 / u
    disc = np.exp(-r * dt)
    p = (np.exp((r - q) * dt) - d) / (u - d)
    if not 0.0 < p < 1.0:
        raise ValueError("binomial probability outside (0,1); increase steps or check inputs")

    j = np.arange(n + 1)
    # terminal node prices: shape (len(S), n+1)
    ST = S_arr[:, None] * (u ** (n - j)) * (d ** j)
    V = intrinsic_value(ST, K, option_type)
    for i in range(n - 1, -1, -1):
        cont = disc * (p * V[:, : i + 1] + (1 - p) * V[:, 1 : i + 2])
        Si = S_arr[:, None] * (u ** (i - j[: i + 1])) * (d ** j[: i + 1])
        V = np.maximum(cont, intrinsic_value(Si, K, option_type))
    out = V[:, 0]
    return float(out[0]) if scalar else out


def early_exercise_premium(S, K, r, q, sigma, T, option_type, steps: int = 200):
    """American value minus the same-tree European value (>= 0)."""
    from engine.pricing import bsm_price
    return american_price(S, K, r, q, sigma, T, option_type, steps) - bsm_price(
        S, K, r, q, sigma, T, option_type
    )
