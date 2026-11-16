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

import sys

from nicegui import ui

from ui.layout import build_page


@ui.page("/")
def main_page() -> None:
    build_page()


def run() -> None:
    native_mode = "--web" not in sys.argv
    try:
        ui.run(
            title="Options Strategy Payoff Terminal",
            native=native_mode,
            window_size=(1440, 900) if native_mode else None,
            reload=False,
            port=8080,
            dark=True,
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
                port=8080,
                dark=True,
            )
        else:
            raise


if __name__ in {"__main__", "__mp_main__"}:
    run()
