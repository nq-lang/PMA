"""
ui/theme.py
===========

Original color palette and design tokens for the terminal's dark theme.

This palette is *inspired by the category* of dark-themed trading/flow
terminal (near-black background, high-contrast text, green-for-profit /
red-for-loss accents) but uses its own original hex values -- it does not
reuse any specific vendor's exact brand colors, logos, or trademarks, per
the project's explicit non-goals (spec §9).

All NiceGUI screens should import color tokens from here rather than
hardcoding hex strings, so the whole app's look stays consistent and is
easy to re-skin later from a single file.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    # Backgrounds (near-black, layered for depth)
    bg_app: str = "#0B0E14"  # outermost window background
    bg_panel: str = "#12151C"  # cards / panels / header bar
    bg_panel_raised: str = "#181C26"  # hovered/raised panel state
    bg_input: str = "#1E2330"  # text inputs, dropdowns

    # Borders / dividers
    border_subtle: str = "#242938"
    border_strong: str = "#33394A"

    # Text
    text_primary: str = "#F2F4F8"
    text_secondary: str = "#9AA3B8"
    text_muted: str = "#6B7386"

    # Profit / loss accents (original hues -- not matched to any specific
    # vendor's brand green/red)
    profit_green: str = "#20D67B"
    profit_green_dim: str = "#128850"
    loss_red: str = "#FF5C5C"
    loss_red_dim: str = "#9C3A3A"

    # Neutral accent (used for spot-price markers, dotted "today" lines)
    accent_blue: str = "#4C8DFF"
    accent_violet: str = "#9B7BFF"
    accent_amber: str = "#F5B942"

    # Long / short leg color-coding on the strike ruler (spec §3.4)
    leg_long: str = "#20D67B"
    leg_short: str = "#FF5C5C"

    # Semantic status
    warning: str = "#F5B942"
    info: str = "#4C8DFF"

    # Chart gradient stops (profit zone fades from strong green near the
    # curve to transparent; loss zone fades from strong red near the curve
    # to transparent) -- expressed as rgba strings for direct use in
    # ECharts/ Plotly gradient fill definitions.
    profit_fill_top: str = "rgba(32, 214, 123, 0.35)"
    profit_fill_bottom: str = "rgba(32, 214, 123, 0.02)"
    loss_fill_top: str = "rgba(255, 92, 92, 0.02)"
    loss_fill_bottom: str = "rgba(255, 92, 92, 0.35)"


PALETTE = Palette()

# Typography
FONT_FAMILY = "'Inter', 'Segoe UI', -apple-system, sans-serif"
FONT_FAMILY_MONO = "'JetBrains Mono', 'SF Mono', 'Consolas', monospace"

# Spacing scale (px), used consistently across layout.py/components.py
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 20
SPACE_XL = 32

# Border radius scale
RADIUS_SM = 6
RADIUS_MD = 10
RADIUS_LG = 16

# The permanent "SIMULATED DATA" badge copy, defined once here so header
# and any other surface that repeats the disclosure stays word-for-word
# consistent (spec §3.1: "never mistaken for a live feed").
SIMULATED_DATA_BADGE_TEXT = "SIMULATED DATA"

# A single stylesheet string layout.py injects once via ui.add_css /
# ui.add_head_html, defining a few reusable classes (stat tiles, chip
# pills, tooltip popovers) on top of the raw NiceGUI/Quasar defaults.
GLOBAL_CSS = f"""
:root {{
  --bg-app: {PALETTE.bg_app};
  --bg-panel: {PALETTE.bg_panel};
  --bg-panel-raised: {PALETTE.bg_panel_raised};
  --bg-input: {PALETTE.bg_input};
  --border-subtle: {PALETTE.border_subtle};
  --border-strong: {PALETTE.border_strong};
  --text-primary: {PALETTE.text_primary};
  --text-secondary: {PALETTE.text_secondary};
  --text-muted: {PALETTE.text_muted};
  --profit-green: {PALETTE.profit_green};
  --loss-red: {PALETTE.loss_red};
  --accent-blue: {PALETTE.accent_blue};
  --accent-violet: {PALETTE.accent_violet};
  --accent-amber: {PALETTE.accent_amber};
}}

body {{
  background-color: var(--bg-app) !important;
  color: var(--text-primary);
  font-family: {FONT_FAMILY};
}}

.opt-panel {{
  background-color: var(--bg-panel);
  border: 1px solid var(--border-subtle);
  border-radius: {RADIUS_MD}px;
  padding: {SPACE_MD}px {SPACE_LG}px;
}}

.opt-stat-tile {{
  background-color: var(--bg-panel);
  border: 1px solid var(--border-subtle);
  border-radius: {RADIUS_SM}px;
  padding: {SPACE_SM}px {SPACE_MD}px;
  cursor: help;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}}
.opt-stat-tile:hover {{
  border-color: var(--border-strong);
  background-color: var(--bg-panel-raised);
}}

.opt-stat-label {{
  color: var(--text-secondary);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}}

.opt-stat-value {{
  font-family: {FONT_FAMILY_MONO};
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}}

.opt-value-positive {{ color: var(--profit-green); }}
.opt-value-negative {{ color: var(--loss-red); }}

.opt-chip {{
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border-radius: 999px;
  padding: 2px 10px;
  font-family: {FONT_FAMILY_MONO};
  font-size: 12px;
  font-weight: 600;
  cursor: grab;
  user-select: none;
}}
.opt-chip-long {{
  background-color: rgba(32, 214, 123, 0.15);
  color: var(--profit-green);
  border: 1px solid rgba(32, 214, 123, 0.4);
}}
.opt-chip-short {{
  background-color: rgba(255, 92, 92, 0.15);
  color: var(--loss-red);
  border: 1px solid rgba(255, 92, 92, 0.4);
}}

.opt-badge-simulated {{
  background-color: rgba(245, 185, 66, 0.15);
  color: var(--accent-amber);
  border: 1px solid rgba(245, 185, 66, 0.4);
  border-radius: 999px;
  padding: 2px 10px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
}}

.opt-info-icon {{
  color: var(--text-muted);
  cursor: help;
  font-size: 13px;
  margin-left: 4px;
}}
.opt-info-icon:hover {{
  color: var(--text-secondary);
}}
"""
