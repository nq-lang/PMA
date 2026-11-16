"""
ui/insights.py
===============

Original hover-tooltip copy (spec §7). Every stat tile and chart region
gets a short, plain-language explanation of what the number means and how
to read it. All copy below is original writing for this project.

Functions take the live computed values so the tooltip text can include a
plain-English read of the *current* number (e.g., "gains ~$66 for a $1
move up"), not just a generic definition.
"""

from __future__ import annotations


def delta_tooltip(delta: float) -> str:
    direction = "up" if delta >= 0 else "down"
    magnitude = abs(delta)
    return (
        "Delta measures how much this position's value changes for a $1 "
        f"move in the underlying price. Right now, this position gains "
        f"roughly ${magnitude:,.2f} in value for every $1 the underlying "
        f"moves {direction}, holding everything else constant. Delta also "
        "roughly approximates the position's exposure in 'share equivalent' "
        "terms."
    )


def gamma_tooltip(gamma: float) -> str:
    return (
        "Gamma is the rate at which Delta itself changes as the underlying "
        f"price moves -- think of it as Delta's speedometer. This position's "
        f"Delta is currently changing by about {gamma:,.2f} for every $1 "
        "move in the underlying. Gamma tends to grow sharply near the "
        "strike price as expiration approaches, which is why short-dated, "
        "at-the-money positions can see their Delta shift quickly."
    )


def theta_tooltip(theta: float) -> str:
    direction = "loses" if theta < 0 else "gains"
    return (
        "Theta estimates how much value this position is expected to "
        f"{direction} purely from one calendar day passing, assuming the "
        f"underlying price and volatility don't change. At current "
        f"settings, that's about ${abs(theta):,.2f} per day. Theta decay "
        "typically accelerates as expiration gets closer."
    )


def vega_tooltip(vega: float) -> str:
    return (
        "Vega measures sensitivity to implied volatility. This position's "
        f"value would change by roughly ${vega:,.2f} for a 1 percentage "
        "point move in implied volatility (e.g., IV moving from 30% to "
        "31%), holding price and time constant. Longer-dated and "
        "at-the-money positions tend to carry more Vega."
    )


def rho_tooltip(rho: float) -> str:
    return (
        "Rho measures sensitivity to interest rates. This position's value "
        f"would change by roughly ${rho:,.2f} for a 1 percentage point move "
        "in the risk-free rate. Rho is usually the least impactful Greek "
        "for shorter-dated trades, and matters more for longer-dated "
        "options and stock-equivalent structures."
    )


def max_profit_tooltip(is_unbounded: bool, value: float | None) -> str:
    if is_unbounded:
        return (
            "Max Profit is theoretically unlimited for this structure: as "
            "the underlying price keeps rising (or falling, for a "
            "downside-unbounded structure), this position's profit keeps "
            "growing without a hard ceiling, at least in this simplified "
            "model. In practice, extreme moves are rare and this figure "
            "describes the mathematical payoff shape, not a promise."
        )
    return (
        f"Max Profit of ${value:,.2f} is the best-case result for this "
        "structure at expiration, reached once the underlying price moves "
        "far enough in the favorable direction that every leg is fully "
        "in- or out-of-the-money in the way that benefits this position."
    )


def max_loss_tooltip(is_unbounded: bool, value: float | None) -> str:
    if is_unbounded:
        return (
            "Max Loss is theoretically unlimited for this structure: an "
            "adverse move in the underlying can keep increasing this "
            "position's loss without a hard floor, at least in this "
            "simplified model. Structures with uncapped downside risk "
            "deserve extra caution and position sizing discipline."
        )
    return (
        f"Max Loss of ${abs(value):,.2f} is the worst-case result for this "
        "structure at expiration -- the most this position can lose if the "
        "underlying price moves as unfavorably as this model allows for."
    )


def breakeven_tooltip(price: float) -> str:
    return (
        f"At a price of ${price:,.2f} at expiration, this position "
        "neither makes nor loses money versus its entry cost. Above this "
        "price the position may be profitable (or unprofitable, depending "
        "on which side of the curve you're looking at) -- check the "
        "green/red shading around this line on the chart to see which "
        "direction is favorable here."
    )


def probability_of_profit_tooltip(pop: float) -> str:
    return (
        f"Probability of Profit is estimated at {pop * 100:,.1f}%. This "
        "figure comes from a simplified model that assumes the underlying "
        "price's future path follows a lognormal random walk, calibrated "
        "to the current simulated price, implied volatility, and days to "
        "expiration. Real markets can behave quite differently from this "
        "assumption (e.g., sudden jumps, changing volatility, fat tails), "
        "so treat this as an educational estimate, not a guarantee."
    )


def crosshair_tooltip(price: float, pnl_dollars: float, pnl_pct: float | None) -> str:
    pct_str = f" ({pnl_pct:+.1f}%)" if pnl_pct is not None else ""
    dominant = (
        "Near a kink in the curve, Gamma and the nearest strike dominate "
        "the local shape; further from any strike, Delta dominates and "
        "the curve is closer to a straight line."
    )
    return (
        f"At ${price:,.2f}: P/L is ${pnl_dollars:,.2f}{pct_str} at "
        f"expiration. {dominant}"
    )


def as_of_date_slider_tooltip() -> str:
    return (
        "This slider scrubs the 'as of' date between today and "
        "expiration. The dashed curve it produces is re-priced leg by leg "
        "using the option pricing model at the remaining time left on "
        "that date -- it reflects the extrinsic value still left in the "
        "position, not a straight-line guess between today's P/L and the "
        "expiration P/L. That's why the dashed curve often bows away from "
        "a simple average of the two."
    )


def price_range_slider_tooltip() -> str:
    return (
        "Controls how far above and below the current simulated price the "
        "chart's x-axis extends. This only changes what's visible -- it "
        "does not change the underlying math, Max Profit/Loss, or "
        "breakeven calculations, which already account for the full "
        "theoretical price range."
    )


def iv_slider_tooltip() -> str:
    return (
        "Overrides the simulated implied volatility used to price every "
        "leg, as a 'what-if' scenario tool. Raising IV increases the "
        "extrinsic value priced into the as-of-date curve and every "
        "Greek; it does not change the at-expiration payoff curve, since "
        "intrinsic value at expiration doesn't depend on volatility."
    )


def net_debit_credit_tooltip(cost: float) -> str:
    if cost >= 0:
        return (
            f"This position was opened for a net debit of ${cost:,.2f} -- "
            "that's the total amount paid to establish it, and (for most "
            "defined-risk structures) it's also the most this position can "
            "lose."
        )
    return (
        f"This position was opened for a net credit of ${abs(cost):,.2f} "
        "-- that's the amount received to establish it. For defined-risk "
        "credit structures, this credit is often close to the maximum "
        "possible profit."
    )


def profit_index_tooltip(pi: float) -> str:
    return (
        f"Profit Index is {pi:,.2f}. It divides the model's expected profit or "
        "loss at expiration (averaged over the same lognormal price model used "
        "for Probability of Profit) by the amount at risk (max loss, or the net "
        "entry cost when loss is unbounded). Above 0 means the model expects a "
        "gain per dollar risked; below 0 means it expects a loss. Because the "
        "prices here are simulated and fairly valued, values near 0 are normal "
        "-- treat it as an educational comparison between structures."
    )


def leg_edit_tooltip() -> str:
    return "Click a leg to edit its strike, quantity, direction and days to expiration."
