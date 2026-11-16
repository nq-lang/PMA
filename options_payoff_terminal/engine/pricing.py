"""
engine/pricing.py
==================

Black-Scholes-Merton (BSM) European option pricing and analytic Greeks.

This module contains **no simulated data** and **no UI code** — it is a pure
quantitative finance library. Every function is vectorized with numpy so it
can be called with scalars or arrays of hypothetical underlying prices
(e.g., the 200-400 point price grid used to draw the payoff chart).

--------------------------------------------------------------------------
UNIT CONVENTIONS (read this before using any Greek elsewhere in the app)
--------------------------------------------------------------------------
All functions below return **per-share** values (i.e., the textbook BSM
formulas, unscaled). The `engine/payoff.py` module is responsible for
scaling per-share Greeks up to a "per contract lot" (100 shares/contract)
and then by the number of contracts and direction (+1 long / -1 short) to
produce the position-level Greeks shown in the UI's Greeks strip. This
mirrors how most retail platforms display Greeks (e.g., a single long ATM
call showing "Delta 55" instead of "Delta 0.55").

Specifically, per-share conventions used here:

- **Delta**: dimensionless, in [-1, 1] for calls/puts (a $1 move in the
  underlying moves the option price by ~Delta dollars, per share).
- **Gamma**: units of (Delta per $1 move in underlying), i.e. d(Delta)/dS.
  Per-share gamma is a small number (e.g., 0.02); the UI scales it by
  contract multiplier (100) and quantity for a more legible "position
  gamma" readout.
- **Vega**: reported **per 1 percentage point (1 vol point) change in
  IV**, i.e. the textbook per-unit vega multiplied by 0.01. This matches
  how retail platforms quote vega (e.g., "Vega 91.77" meaning the position
  gains/loses ~$91.77 if IV moves from, say, 63.5% to 64.5%).
- **Theta**: reported **per calendar day**, i.e. the textbook per-year
  theta divided by 365. This is the standard "daily time decay" figure
  shown on most platforms. It is negative for net-long premium and
  positive for net-short premium.
- **Rho**: reported **per 1 percentage point (100bps) change in the
  risk-free rate**, i.e. the textbook per-unit rho multiplied by 0.01.

All four of Vega/Theta/Rho above are still **per-share**; `payoff.py`
multiplies by 100 (contract multiplier) and by (quantity * direction) per
leg, then sums across legs, to get the position-level number shown in the
UI. This two-step scaling is intentional and kept explicit so unit bugs
are easy to audit.

References for formulas: Hull, "Options, Futures, and Other Derivatives";
Black & Scholes (1973); Merton (1973) continuous-dividend extension.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

import numpy as np
from scipy.special import ndtr

ArrayLike = Union[float, np.ndarray]
OptionType = Literal["call", "put"]

# Below this remaining-time threshold (in years), we treat the option as
# "at expiration" and use the intrinsic-value limit instead of evaluating
# the BSM formula (which would divide by sqrt(T) ~ 0).
_MIN_T_YEARS = 1.0 / 365.0 / 24.0  # ~1 hour, effectively "expired" for our purposes
_MIN_SIGMA = 1e-6  # floor to avoid divide-by-zero on degenerate zero-vol inputs
_INV_SQRT_2PI = 0.3989422804014327  # 1/sqrt(2*pi)


def _npdf(x: np.ndarray) -> np.ndarray:
    """Standard normal PDF (closed form; avoids scipy.stats.norm overhead)."""
    return _INV_SQRT_2PI * np.exp(-0.5 * x * x)


def _safe_T_sigma(T: ArrayLike, sigma: ArrayLike) -> tuple[np.ndarray, np.ndarray]:
    """Clip T and sigma away from zero so downstream math never divides by zero.

    Callers that need the *true* intrinsic-value limit at T->0 should check
    `T <= _MIN_T_YEARS` themselves (see `bsm_price`) rather than relying on
    this clip alone, since clipping T to a tiny positive number would still
    produce a (nearly) correct extrinsic-free price, but we prefer the exact
    intrinsic formula for numerical cleanliness at true expiration.
    """
    T_arr = np.asarray(T, dtype=float)
    sigma_arr = np.asarray(sigma, dtype=float)
    T_safe = np.clip(T_arr, _MIN_T_YEARS, None)
    sigma_safe = np.clip(sigma_arr, _MIN_SIGMA, None)
    return T_safe, sigma_safe


def d1_d2(
    S: ArrayLike, K: ArrayLike, r: float, q: float, sigma: ArrayLike, T: ArrayLike
) -> tuple[np.ndarray, np.ndarray]:
    """Compute the BSM d1 and d2 terms (vectorized).

    d1 = (ln(S/K) + (r - q + 0.5*sigma^2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    """
    S_arr = np.asarray(S, dtype=float)
    K_arr = np.asarray(K, dtype=float)
    T_safe, sigma_safe = _safe_T_sigma(T, sigma)

    sqrtT = np.sqrt(T_safe)
    d1 = (np.log(S_arr / K_arr) + (r - q + 0.5 * sigma_safe**2) * T_safe) / (
        sigma_safe * sqrtT
    )
    d2 = d1 - sigma_safe * sqrtT
    return d1, d2


def intrinsic_value(S: ArrayLike, K: ArrayLike, option_type: OptionType) -> np.ndarray:
    """Intrinsic value of a European option at expiration (T=0 limit)."""
    S_arr = np.asarray(S, dtype=float)
    K_arr = np.asarray(K, dtype=float)
    if option_type == "call":
        return np.maximum(S_arr - K_arr, 0.0)
    elif option_type == "put":
        return np.maximum(K_arr - S_arr, 0.0)
    else:
        raise ValueError(f"option_type must be 'call' or 'put', got {option_type!r}")


def bsm_price(
    S: ArrayLike,
    K: ArrayLike,
    r: float,
    q: float,
    sigma: ArrayLike,
    T: ArrayLike,
    option_type: OptionType,
) -> np.ndarray:
    """European option price under Black-Scholes-Merton with continuous dividend yield q.

    Handles T -> 0 (or negative, defensively) as the intrinsic-value limit
    rather than dividing by zero. Fully vectorized: S, sigma, and T may all
    be arrays (e.g., S is a price grid, sigma/T are scalars, or vice versa),
    as long as they broadcast together per numpy rules.
    """
    S_arr = np.asarray(S, dtype=float)
    K_arr = np.asarray(K, dtype=float)
    T_arr = np.asarray(T, dtype=float)
    sigma_arr = np.asarray(sigma, dtype=float)

    # Broadcast everything to a common shape so we can mask expired points.
    S_b, K_b, T_b, sigma_b = np.broadcast_arrays(S_arr, K_arr, T_arr, sigma_arr)
    S_b = S_b.astype(float)
    T_b = T_b.astype(float)

    expired_mask = T_b <= _MIN_T_YEARS

    d1, d2 = d1_d2(S_b, K_b, r, q, sigma_b, T_b)

    T_pos = np.clip(T_b, 0, None)
    disc_q = np.exp(-q * T_pos)
    disc_r = np.exp(-r * T_pos)
    if option_type == "call":
        price = S_b * disc_q * ndtr(d1) - K_b * disc_r * ndtr(d2)
    elif option_type == "put":
        price = K_b * disc_r * ndtr(-d2) - S_b * disc_q * ndtr(-d1)
    else:
        raise ValueError(f"option_type must be 'call' or 'put', got {option_type!r}")

    intrinsic = intrinsic_value(S_b, K_b, option_type)
    price = np.where(expired_mask, intrinsic, price)

    # price should never be negative (numerical noise guard)
    price = np.maximum(price, 0.0)

    if np.isscalar(S) and np.isscalar(K) and np.isscalar(sigma) and np.isscalar(T):
        return float(price)
    return price


@dataclass(frozen=True)
class Greeks:
    """Per-share Greeks bundle. See module docstring for unit conventions.

    delta: dimensionless, in [-1, 1]
    gamma: d(delta)/dS, per $1 move in underlying
    vega:  $ change in option price per 1 percentage point (1 vol point) IV move
    theta: $ change in option price per calendar day (already divided by 365)
    rho:   $ change in option price per 1 percentage point (100bps) rate move
    """

    delta: np.ndarray
    gamma: np.ndarray
    vega: np.ndarray
    theta: np.ndarray
    rho: np.ndarray


def bsm_greeks(
    S: ArrayLike,
    K: ArrayLike,
    r: float,
    q: float,
    sigma: ArrayLike,
    T: ArrayLike,
    option_type: OptionType,
) -> Greeks:
    """Analytic BSM Greeks (not finite-difference), per-share, in the unit
    conventions documented in the module docstring.

    At/after expiration (T <= _MIN_T_YEARS), an option's Greeks collapse to
    their intrinsic limits: Delta is 0 or +/-1 (0.5 exactly at-the-money is
    a measure-zero edge case we resolve by an explicit tie-break), and
    Gamma/Vega/Theta/Rho are all 0 (an expired option has no more
    optionality left to decay, and its price no longer responds to vol or
    rates).
    """
    S_arr = np.asarray(S, dtype=float)
    K_arr = np.asarray(K, dtype=float)
    T_arr = np.asarray(T, dtype=float)
    sigma_arr = np.asarray(sigma, dtype=float)

    S_b, K_b, T_b, sigma_b = np.broadcast_arrays(S_arr, K_arr, T_arr, sigma_arr)
    S_b = S_b.astype(float)
    T_b = T_b.astype(float)
    sigma_b = sigma_b.astype(float)

    expired_mask = T_b <= _MIN_T_YEARS

    d1, d2 = d1_d2(S_b, K_b, r, q, sigma_b, T_b)
    T_safe, sigma_safe = _safe_T_sigma(T_b, sigma_b)
    sqrtT = np.sqrt(T_safe)

    pdf_d1 = _npdf(d1)
    N_d1 = ndtr(d1)
    N_d2 = ndtr(d2)
    disc_q = np.exp(-q * np.clip(T_b, 0, None))
    disc_r = np.exp(-r * np.clip(T_b, 0, None))

    # Gamma is identical in form for calls and puts.
    gamma_raw = disc_q * pdf_d1 / (S_b * sigma_safe * sqrtT)

    # Vega is identical in form for calls and puts (per unit vol -> scale by 0.01).
    vega_raw = S_b * disc_q * pdf_d1 * sqrtT
    vega = vega_raw * 0.01

    if option_type == "call":
        delta_raw = disc_q * N_d1
        theta_raw = (
            -(S_b * disc_q * pdf_d1 * sigma_safe) / (2 * sqrtT)
            - r * K_b * disc_r * N_d2
            + q * S_b * disc_q * N_d1
        )
        rho_raw = K_b * T_safe * disc_r * N_d2
        expired_delta = np.where(S_b > K_b, 1.0, np.where(S_b < K_b, 0.0, 0.5))
    elif option_type == "put":
        delta_raw = disc_q * (N_d1 - 1.0)
        theta_raw = (
            -(S_b * disc_q * pdf_d1 * sigma_safe) / (2 * sqrtT)
            + r * K_b * disc_r * (1.0 - N_d2)
            - q * S_b * disc_q * (1.0 - N_d1)
        )
        rho_raw = -K_b * T_safe * disc_r * (1.0 - N_d2)
        expired_delta = np.where(S_b < K_b, -1.0, np.where(S_b > K_b, 0.0, -0.5))
    else:
        raise ValueError(f"option_type must be 'call' or 'put', got {option_type!r}")

    theta = theta_raw / 365.0  # per calendar day
    rho = rho_raw * 0.01  # per 1 percentage point rate move

    delta = np.where(expired_mask, expired_delta, delta_raw)
    gamma = np.where(expired_mask, 0.0, gamma_raw)
    vega = np.where(expired_mask, 0.0, vega)
    theta = np.where(expired_mask, 0.0, theta)
    rho = np.where(expired_mask, 0.0, rho)

    scalar_inputs = all(np.isscalar(x) for x in (S, K, sigma, T))
    if scalar_inputs:
        return Greeks(
            delta=float(delta),
            gamma=float(gamma),
            vega=float(vega),
            theta=float(theta),
            rho=float(rho),
        )
    return Greeks(delta=delta, gamma=gamma, vega=vega, theta=theta, rho=rho)
