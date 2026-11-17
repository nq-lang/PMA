"""
app.py
======

Entry point for the Options Strategy Payoff Terminal.

Run locally with:

    pip install -r requirements.txt
    python app.py

This launches a NiceGUI desktop window (native pywebview mode) by default.
If native mode isn't available on your platform (e.g., some Linux setups
missing GTK/webview dependencies), it automatically falls back to serving
the same UI at http://localhost:8080 in your regular browser -- functionally
identical, just not a standalone window.

IMPORTANT: This tool is a simulation/education app. It has no brokerage
connectivity and uses no real market data -- every price, quote, and
"flow" row is generated locally by engine/market_sim.py. See README.md.
"""

from __future__ import annotations

import os
import sys

from nicegui import ui

from ui.futures_page import build_futures_page
from ui.layout import build_page
from ui.portfolio_page import build_portfolio_page


@ui.page("/")
def main_page() -> None:
    build_page()


@ui.page("/futures")
def futures_page() -> None:
    build_futures_page()


@ui.page("/portfolio")
def portfolio_page() -> None:
    build_portfolio_page()


def _headless() -> bool:
    """True in Codespaces/containers/CI where a native window cannot open."""
    return bool(os.environ.get("CODESPACES") or os.environ.get("REMOTE_CONTAINERS")
                or (sys.platform.startswith("linux") and not os.environ.get("DISPLAY")
                    and not os.environ.get("WAYLAND_DISPLAY")))


def run() -> None:
    native_mode = "--web" not in sys.argv and not _headless()
    port = int(os.environ.get("PORT", "8080"))
    try:
        ui.run(
            title="Options Strategy Payoff Terminal",
            native=native_mode,
            window_size=(1440, 900) if native_mode else None,
            reload=False,
            host="0.0.0.0",
            port=port,
            dark=True,
            show=not _headless(),
        )
    except Exception as exc:  # noqa: BLE001
        if native_mode:
            print(
                f"Native desktop window failed to start ({exc}); "
                "falling back to browser mode at http://localhost:8080",
                file=sys.stderr,
            )
            ui.run(
                title="Options Strategy Payoff Terminal",
                native=False,
                reload=False,
                host="0.0.0.0",
                port=port,
                dark=True,
                show=not _headless(),
            )
        else:
            raise


if __name__ in {"__main__", "__mp_main__"}:
    run()
