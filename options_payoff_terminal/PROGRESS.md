# Build Progress Log — Options Payoff Terminal

Living checklist. Update this file whenever a stage completes or a design
decision is made, so the build can be resumed/verified at any point
without re-deriving context from scratch.

## Stage 1 — Repo scaffold: DONE
- [x] engine/, ui/, tests/ packages created
- [x] app.py entry point placeholder
- [x] requirements.txt + pyproject.toml (numpy, scipy, pandas, nicegui, pytest)
- [x] README.md stub with simulated-data disclaimer up front

## Stage 2 — Engine: DONE (127/127 tests passing)
- [x] engine/pricing.py — BSM price + 5 analytic Greeks
      Unit conventions: vega/rho per 1-point move, theta per calendar day,
      delta/gamma raw. Documented in module docstring.
      Tests: tests/test_pricing.py (27 passing) incl. Hull textbook value,
      put-call parity across full grid, finite-difference cross-checks.
- [x] engine/market_sim.py — seeded deterministic MarketSimulator
      Ticker string -> stable hash seed -> reproducible snapshot.
      Self-consistent fields (day range ⊂ spot, 52wk range ⊂ day range,
      MAs plausible). Smooth IV skew/term-structure fn. Cosmetic flow tape.
      Tests: tests/test_market_sim.py (14 passing)
- [x] engine/strategies.py — full leg-set factory, ~32 strategies from §4
      Leg dataclass (kind/direction/quantity/strike/dte_days).
      STRATEGY_REGISTRY + STRATEGY_GROUPS for UI dropdown sections.
      "Custom" strategy = empty leg list (blank start for leg-builder).
      Tests: tests/test_strategies.py (58 passing)
- [x] engine/payoff.py — payoff math core
      - expiration_payoff: pure intrinsic math, vectorized
      - asof_payoff: TRUE BSM re-pricing at remaining time per leg
        (verified numerically different from linear interpolation —
        see test_asof_payoff_differs_from_linear_interpolation)
      - find_breakevens: generic brentq root-finding, works for any leg
        count/combo, not just closed-form 1-2 leg formulas
      - max_profit_loss: IMPORTANT DESIGN DECISION (see below)
      - probability_of_profit: lognormal terminal-price model
      Tests: tests/test_payoff.py (28 passing)

### Key design decision — Max Profit/Loss unbounded detection
Initially treated S->0 and S->infinity symmetrically for "unbounded"
detection. This was WRONG and caught via failing tests. Correct model:
price is physically bounded below by zero, so a long put / short stock's
worst/best case at S=0 is always a large-but-FINITE number (e.g.
strike*100 - premium), never "Infinity" — matches how real platforms
report it. Only S->infinity can be truly unbounded. Fixed via
`_payoff_at_zero_price()` computing the exact S=0 value analytically
(independent of the chart's visible zoom window) folded into interior
extrema, and `_net_payoff_slope_as_S_to_infinity()` as the only unbounded
trigger. Regression tests added: test_long_put_max_profit_bounded_by_
strike_going_to_zero and test_long_stock_unbounded_profit_bounded_loss,
both explicitly using a ZOOMED-IN grid that doesn't reach S=0, to prove
the fix doesn't depend on the grid happening to extend that far.

## Stage 3 — UI shell: IN PROGRESS
- [x] ui/theme.py — original dark palette (own hex values, not any
      vendor's brand colors), CSS token string for NiceGUI head injection
- [x] ui/insights.py — original tooltip copy, all required hover insights
      from spec §7 (delta/gamma/theta/vega/rho, max profit/loss,
      breakeven, POP, crosshair, as-of slider, price-range slider,
      IV slider, net debit/credit)
- [x] ui/components.py — stat_tile (w/ tooltip), key_stats_bar,
      greeks_strip, snapshot_header, leg_chip, positions_sidebar, flow_row
      Formatters: fmt_dollars, fmt_compact_dollars, fmt_pct
      Smoke-tested imports + formatters directly, all correct.
- [x] ui/chart.py — ECharts-based payoff chart, green/red gradient split
      fill with EXACT zero-crossing insertion (linear-interpolated, not
      just grid-cell-level color change), spot + breakeven mark lines,
      optional dashed as-of-date overlay series.
      Tests: tests/test_chart.py (6 passing) — pure data-shape functions
      tested directly without needing a live server.
- [x] ui/profit_table.py — price x date heat-colored grid
      build_profit_table_data() cells verified IDENTICAL to calling
      engine.payoff.asof_payoff directly (no divergent calc path).
      Tests: tests/test_profit_table.py (5 passing)
- [ ] ui/layout.py — page assembly (header, strategy selector, chart,
      sliders, profit table, positions sidebar) — STARTING NOW
- [ ] app.py — real NiceGUI entry point wiring layout.py — NOT STARTED
      (currently just an empty placeholder file)
- [ ] Interactivity wiring (strategy change -> rebuild legs -> recompute
      stats -> redraw chart; slider changes; leg editing; save/load)
- [ ] Final README pass (setup, run instructions, architecture, Greek
      unit conventions, POP assumptions, known limitations)
- [ ] Final acceptance-criteria pass against original spec files

## MAJOR ENVIRONMENT CORRECTION (read this before assuming any constraint)
Earlier progress notes said NiceGUI couldn't be installed/run/screenshotted
here. Both were WRONG, corrected as follows:
- pypi.org IS allowlisted -> `pip install -r requirements.txt` WORKS here,
  confirmed, nicegui 2.9.0 + all deps actually installed in this sandbox.
- Xvfb AND wkhtmltoimage ARE both installed -> a REAL screenshot of the
  REAL running app is achievable, not just a hand-built HTML mockup.
ACTION: prioritize finishing the real UI and screenshotting THAT for real,
rather than a separate throwaway static mockup.

## Environment constraints (stated once, applies throughout)
- CORRECTED: pypi.org IS on this sandbox's network allowlist, so NiceGUI
  IS installable here (confirmed via `pip install nicegui --dry-run`,
  resolves fine). Installing for real now — this means I can actually
  smoke-test imports and possibly run the NiceGUI server headlessly.
- Still no display server / browser here, so no genuine pixel screenshot
  of a rendered browser page is possible even with the server running.
  Best available substitute: (a) a static HTML mockup styled with the
  real theme.py tokens and populated with real engine-computed numbers,
  rendered as an actual image via the view tool, and (b) running the real
  app.py NiceGUI server + hitting it with a headless HTTP client to prove
  it actually boots and serves real HTML (not just "the code looks right").
  CORRECTED AGAIN: Xvfb and wkhtmltoimage ARE both installed in this
  sandbox. This means I CAN actually: run the real NiceGUI server
  (headless, native or web mode), and use wkhtmltoimage (or Xvfb +
  a headless browser) to capture a genuine screenshot of the real
  rendered page. This is a materially better verification path than a
  hand-built static mockup — prioritize building the real UI (layout.py,
  components.py, app.py) FIRST, then screenshot THAT for real, rather
  than spending time on a separate throwaway mockup file.
- Engine is fully testable here (numpy/scipy/pandas available) — 127/127
  passing, this is real verification, not a claim.
- Full app is delivered as runnable source for the user's own machine via
  `pip install -r requirements.txt && python app.py`.

## Sandbox execution model — IMPORTANT gotcha discovered
Each bash_tool call is its own fresh shell; a `&`-backgrounded process
from one bash_tool call does NOT survive into the next call (confirmed:
server process was in `ps aux` immediately after launch, but gone / not
connectable in the next tool call). CONSEQUENCE: server launch, curl, AND
wkhtmltoimage screenshot must all happen within a SINGLE bash_tool
invocation, e.g.:
    (python3 app.py --web &) ; sleep 5 ; wkhtmltoimage ... ; ...
Keep this in mind for all future server-based verification steps.

SECOND GOTCHA: a combined server-launch + wkhtmltoimage call hung the
bash_tool itself (returned nothing, code -1, twice in a row) even with
`timeout 25` wrapping wkhtmltoimage. A follow-up trivial `echo` call also
returned nothing once, then worked normally right after — so this reads
as a transient sandbox/tool hiccup around invoking Xvfb-backed
wkhtmltoimage, not a real deadlock in my command (ps aux showed no
leftover processes once things recovered). MITIGATION: verified real
rendering already via curl (full correct DOM tree with real engine
numbers, zero errors) — that is strong evidence the app works. Screenshot
capture is a nice-to-have on top of that, not required to trust the app.
Retry screenshot capture cautiously: prefer starting the server in one
call, confirming with curl, THEN a separate call for just wkhtmltoimage
with a short --javascript-delay and a hard `timeout`, so a hang there
doesn't need to be diagnosed alongside a server-boot hang too. If it
hangs again, drop the screenshot attempt rather than risk repeated
tool-call stalls, and rely on the curl-verified DOM tree + engion test
suite as the delivered verification instead.
## SCREENSHOT SUCCESS — real Playwright/Chromium capture achieved
Wrote scripts/capture_screenshot.py: launches app.py as a subprocess in
the SAME python process as Playwright (sidesteps the cross-bash_tool-call
process-persistence problem entirely), waits for HTTP readiness, loads
the page in real headless Chromium (not wkhtmltoimage's old WebKit),
waits for networkidle + a short extra delay for ECharts to finish
rendering, full-page screenshots to /tmp/real_screenshot.png. WORKED on
first clean run, 60s timeout, exit code 0. This is the real, trustworthy
verification method — reuse this exact script pattern for all future
visual checks in this project.

### Visual bugs found from the real screenshot (fix these next):
1. Chart mark line labels overlap/collide at the top: "Spot $395.94" and
   the breakeven "$399.30" labels render on top of each other illegibly
   near the top of the chart (x-axis positions are close together: 395.94
   vs 399.30). FIXED: set spot label position="end" (top) and breakeven
   label position="start" (bottom) in ui/chart.py's markLine config, so
   they're vertically separated regardless of how close their x-positions
   are. Not yet re-screenshotted to confirm visually (see below).
2. Positions sidebar quick-add buttons: ↑/↓ arrow glyphs appeared to not
   render in the screenshot. INVESTIGATED via Playwright's actual DOM text
   extraction (page.locator(...).all_inner_texts()), not just pixels:
   confirmed the text IS correctly "CALL ↑", "CALL ↓", "PUT ↑", "PUT ↓" in
   the real DOM (Quasar auto-uppercases button text, that's expected/fine)
   -- so this is NOT a source bug, it's a missing-font-glyph-coverage
   issue in this sandbox's headless Chromium (no installed font here can
   render the ↑/↓ Unicode arrows). Real end-user machines will have fonts
   that render these fine. DECISION: leave the arrow characters as-is in
   source (correct and will render fine for real users), but consider
   swapping to lucide/material icon components (ui.icon) instead of raw
   Unicode arrows in button labels for extra robustness -- lower priority
   polish, not a correctness bug.
3. Overall layout, color palette, chart gradient split, profit table
   heat-coloring, snapshot header, Greeks strip, and key stats bar are ALL
   rendering correctly and matching the intended design closely. This is
   a strong result -- only item 1 needed an actual code fix.
4. Minor polish: chart x-axis label "$494.925" at far right showed 3
   decimal places. FIXED: both x-axis and y-axis axisLabel formatters
   changed to a JS function that rounds to whole dollars
   (Math.round(value).toLocaleString()), consistent with the rest of the
   UI's dollar formatting.

NEXT: re-run scripts/capture_screenshot.py to confirm fixes 1 and 4
visually before moving on.
2. app.py real entry point — DONE, verified boots via curl (HTTP 200,
   full correct DOM with real engine numbers, zero server errors)
3. Screenshot attempt — PARTIAL: wkhtmltoimage renders only the app's
   background color (#0B0E14), not the Vue-mounted content — its bundled
   WebKit almost certainly can't execute NiceGUI's modern JS client.
   The curl-verified full DOM dump is the real proof-of-correctness;
   continuing to chase a pixel screenshot is lower priority than finishing
   the remaining functional work below.
4. Wire remaining interactivity gaps (leg inline-editing dialog; verify
   Save/Load round-trip end-to-end)
5. Final README pass (setup, run instructions, architecture, Greek unit
   conventions, POP assumptions, known limitations, this environment's
   verification method)
6. Final acceptance-criteria pass against original spec files
7. (Optional, time-permitting) one more screenshot attempt via a
   Chromium-based headless capture if available, otherwise ship without

## REGRESSION caught by re-screenshot (exactly why we always re-verify visually)
The JS-function-as-string axisLabel formatter I added to fix the decimal-
places issue BROKE the chart: ECharts' NiceGUI/vbuild JSON serialization
does not appear to convert the Python string containing JS source into an
actual executable JS function on the client -- it rendered the literal
function source text as the axis tick labels instead ("...toLocaleString();}"
visible garbled across the whole y-axis, x-axis label also broken).
ROOT CAUSE: passing raw JS as a plain string in the options dict doesn't
work the way it does for `tooltip.valueFormatter` apparently -- likely
needs NiceGUI's specific JS-callback wrapping mechanism, or the simpler
fix is to just not use a JS function here at all.
FIX IN PROGRESS: revert to a plain ECharts formatter template string
(e.g. "${value}") but pre-round the actual data values / axis min-max to
whole numbers in Python BEFORE they reach the option dict, so no JS
callback is needed at all. This is simpler and more reliable.
STATUS: fixing now, will re-screenshot again to confirm before moving on.

## REGRESSION FIXED AND RE-VERIFIED (screenshot #3)
Root cause fully understood: NiceGUI's plain `ui.echart(options)` does NOT
auto-convert Python strings into executable JS -- that conversion only
happens via `EChart.from_pyecharts()`'s explicit JsCode-marker scan, OR by
prefixing the option KEY with ":" (Vue v-bind convention), which tells the
client template to evaluate the string as a JS expression rather than
render it as a literal value.
FIX: (1) removed the JS-function axisLabel formatters entirely, replaced
with the simple "${value}" template string, with min/max pre-rounded to
whole numbers in Python before reaching the option dict, so no callback
was even needed for that part; (2) fixed tooltip.valueFormatter by
renaming the key to ":valueFormatter" and using a JS arrow-function
expression string, following the documented Vue-prop convention.
RE-VERIFIED via full re-screenshot (scripts/capture_screenshot.py): both
axes now show clean whole-dollar labels, "Spot $395.94" sits at the TOP
of the chart, breakeven "$399.30" sits at the BOTTOM -- no more overlap.
This is now visually confirmed correct, not just "should work."
LESSON FOR REST OF BUILD: any future ECharts JS callback (e.g. if I add
click handlers, custom label formatters elsewhere, etc.) MUST use the
":key" prefix convention, never a plain key with a JS-source string.

## STAGE 3 STATUS: substantially complete and visually verified
All of the following are now confirmed correct via real Chromium
screenshots (not just code review): snapshot header, Greeks strip, key
stats bar, strategy/ticker/DTE controls, payoff chart (gradient fill,
spot/breakeven mark lines, axis labels), price-range/IV/as-of sliders,
profit table (heat-mapped, spot row highlighted in blue), positions
sidebar with quick-add buttons and leg chips, recent-flow tape.

## Remaining work (accurate as of this checkpoint)
1. Interactivity smoke test: click through Save, and a strategy change,
   via Playwright (not just visual — actually click and confirm the
   chart/stats update), since I have the real infra to do this now.
2. Verify Save/Load round-trip functionally (download triggers, dialog
   loads JSON back correctly).
3. Confirm leg quick-add buttons actually add a leg and refresh the chart
   (click "CALL ↑" via Playwright, check position chips list grows).
4. Write ui/layout.py-level tests where feasible (state transitions like
   AppState.reset_legs_to_strategy, save/load dict round-trip) — these
   don't need a live browser, just Python-level assertions.
5. Final README pass: setup/run instructions, architecture overview,
   Greek unit conventions recap, POP model assumptions, stock-leg lot
   convention, known limitations, and an accurate description of how this
   was verified (127 engine tests + real Playwright-rendered screenshots)
   so the user knows exactly what's been checked vs. not.
6. Final full acceptance-criteria pass against the two original spec
   files (options_payoff_terminal_prompt.md and start_build_now.md) --
   go through every numbered requirement explicitly and confirm/flag.
7. Clean up scripts/capture_screenshot.py -- decide whether to keep it in
   the delivered repo (useful as a dev tool / smoke test) or remove it
   as a throwaway. LEANING: keep it, but move it under a clearly-labeled
   dev-tools location and mention it in the README as "how I verified
   this" for transparency.

## REAL FUNCTIONAL BUG FOUND via interactivity script (not just visual)
scripts/interactivity_check.py drove the live app with Playwright clicks,
not just screenshots. Results:
- Quick-add leg button (CALL up-arrow) WORKS: chip count went 2 -> 3.
- Strategy dropdown change to "Iron Condor" DID NOT WORK: leg chips
  stayed as the original Bull Call Spread's ['395C', '-405C'], and Max
  Profit stat stayed at $569.83 (unchanged) instead of updating to the
  Iron Condor's legs/stats. The click on the dropdown option itself may
  not have actually landed / the on('update:model-value', ...) handler
  may not be firing for this NiceGUI ui.select + with_input combination,
  OR my test script's click sequence didn't correctly interact with the
  Quasar q-select popup (clicking "Iron Condor" text might have hit a
  wrong element if multiple matches exist, or the dropdown never opened).
NEXT: investigate directly -- add debug output / try a more robust select
interaction (NiceGUI select elements can usually be set via
`.select_option()` semantics or by locating the specific q-item), and
re-test. This must be fixed and RE-VERIFIED before Stage 3 is considered
done -- a strategy selector that doesn't actually switch strategies is a
core-functionality break, not a polish item.

## MAJOR FUNCTIONAL BUG FOUND AND FIXED: on_change wiring
ROOT CAUSE CONFIRMED: I had wired ui.select/ui.number/ui.slider controls
using manual `.on("update:model-value", handler)` calls. NiceGUI's
documented, correct mechanism for these elements is the `on_change=`
constructor kwarg (confirmed via inspect.signature on Select/Slider/
Number classes) -- NOT a raw Quasar DOM event name passed to `.on()`.
The raw event approach silently failed to fire the handler for
ui.select entirely (confirmed via Playwright: dropdown opened, option
was clickable and visible, but selecting "Iron Condor" left the legs/
stats completely unchanged -- a genuine functional break a user would
have hit immediately).
FIX: rewrote the ticker input, strategy select, DTE number input, and
all three sliders (price range / IV scenario / as-of date) in
ui/layout.py to pass their callbacks via the `on_change=` constructor
kwarg instead of `.on("update:model-value", ...)`.
RE-VERIFIED via scripts/interactivity_check.py (real Playwright clicks,
not just visual screenshot): switching the strategy dropdown to
"Iron Condor" now correctly rebuilds the 4-leg structure
(380P/-390P/-400C/410C) and updates Max Profit from $569.83 to the
correct new value $736.63. Quick-add leg button still works (chip count
4->5). Full engine+chart+table test suite re-run: 138/138 still passing
(no regressions from this fix).
LESSON: this is the second real bug caught only by ACTUALLY DRIVING the
live app with Playwright clicks, not by code review or static
screenshots alone. Static screenshots proved the page renders; only
interaction testing proved the page actually works. Keep doing both for
any remaining interactive surfaces (Save/Load dialog, ticker change,
DTE change, sliders) before calling Stage 3 done.

## FULL INTERACTIVITY VERIFICATION COMPLETE
Extended scripts/interactivity_check.py to also test: ticker change (typed
"AAPL", blurred, confirmed snapshot re-simulated to "AAPL Corporation"),
price-range slider (click + arrow keys, confirmed label and chart both
updated), and Save button (confirmed a REAL browser download event fires
with filename "strategy.json", using Playwright's expect_download).
ALL PASS. Final screenshot (/tmp/interactivity_final_state.png) shows a
fully correct end-to-end AAPL Iron Condor: 4 correct leg chips (65P/-75P/
-85C/95C), correct tent-shaped payoff chart with breakevens at $72.02 and
$87.98 (top/bottom label split working), correct green-middle/red-wings
shading, correctly heat-mapped profit table, flow tape showing AAPL rows,
price range slider at ±55%. This is now genuinely, thoroughly verified
working software, not just "should work" code.

## Stage 3 (UI): DONE. Remaining work for full delivery:
1. Load dialog round-trip: haven't yet tested clicking LOAD, pasting the
   downloaded JSON back in, and confirming state restores correctly.
   Quick to check, should do before final delivery.
2. Leg editing (click an existing chip to edit its strike/qty/direction)
   -- positions_sidebar's on_edit callback is currently wired to None in
   layout.py (only on_remove and on_add are implemented). Decide: either
   implement a real edit dialog, or explicitly document this as a known
   gap in the README's "known limitations" section. Given time invested
   so far, leaning toward documenting as a known limitation + suggesting
   it as a natural v2 addition, since remove+re-add via quick-add buttons
   already covers most editing needs, and the spec's core acceptance
   criteria center on strategy selection + payoff correctness, which are
   both fully working.
3. Final README pass (setup, architecture, Greek conventions, POP
   assumptions, stock-leg lot convention, known limitations, verification
   method used).
4. Final explicit acceptance-criteria pass against both original spec
   files, itemized.
5. Decide fate of scripts/ dev tools -- keeping them, will document in
   README as "how this was verified" for transparency.
6. Clean up any remaining placeholder/dead code, do a final full test run.

## SAVE/LOAD ROUND-TRIP VERIFIED WORKING
scripts/save_load_check.py: saved an Iron Condor (4 legs) to JSON via the
real Save button/download, switched strategy to Long Straddle (2 legs) to
create a detectable difference, opened the Load dialog, pasted the saved
JSON, clicked the dialog's Load button, and confirmed all 4 original Iron
Condor legs (380P/-390P/-400C/410C) were correctly restored. Full
round-trip works end-to-end via real browser interaction.

## REMAINING WORK (accurate, final list before README/acceptance pass)
1. Leg editing (click an existing chip to edit) is a known, documented
   gap -- on_edit wired to None. DECISION MADE: document as a known
   limitation in README rather than build a full edit dialog, since
   remove+re-add via quick-add buttons covers the same functional need
   and core acceptance criteria (strategy correctness, payoff math,
   Greeks, POP, breakevens) are all fully working and verified.
2. Final README pass (setup, architecture, Greek conventions, POP
   assumptions, stock-leg lot convention, known limitations, verification
   method used -- including mentioning the dev scripts/ tools).
3. Final explicit acceptance-criteria pass against both original spec
   files, itemized point by point.
4. Keep scripts/ dev tools in the delivered repo, documented in README.
5. Final full test run + final full screenshot for delivery.

## SECTION 10 ACCEPTANCE CRITERIA — LITERAL CHECKLIST (final pass)

1. "App launches with one command and opens a smooth, native-feeling
   window (no visible browser chrome/URL bar if using a webview shell)."
   STATUS: `python app.py` launches ui.run(native=True) by default (real
   pywebview desktop window, no browser chrome) with a `--web` fallback
   flag for headless/server verification (used throughout this build).
   Native mode itself could not be visually confirmed in THIS sandbox
   (no display for pywebview's native window either, only for the
   browser-mode HTTP server which Playwright/Chromium could reach) --
   documenting this honestly in the README rather than claiming false
   certainty about native mode specifically. Web-mode (identical UI code,
   different shell) is fully verified.

2. "All strategies in §4 are selectable, auto-populate correct legs, and
   render a correct payoff chart + Greeks + stats."
   STATUS: MET. All 32 strategies registered and tested (58 strategy
   tests + 28 payoff tests, both passing). Verified live via Playwright:
   Bull Call Spread and Iron Condor both switch correctly with correct
   legs/stats/chart shape (tent shape confirmed visually for Iron Condor).
   Have NOT individually click-tested all 32 in the live browser (only
   spot-checked 2 interactively + all 32 via the unit test suite) --
   reasonable given time constraints, since the underlying leg-factory
   logic is identical for all of them and is what's under live test.

3. "Custom leg builder can reproduce any of the presets manually and
   matches the preset's numbers exactly."
   STATUS: MET at the engine level (test_manually_built_bull_call_spread_
   matches_preset in tests/test_strategies.py proves the Leg primitive
   used by presets and by manual construction are identical/equivalent).
   At the UI level, "Custom" strategy starts blank and the quick-add
   buttons (CALL/PUT up/down, STOCK) let a user manually build any leg
   combination -- verified working via Playwright quick-add clicks.

4. "IV slider, price-range slider, and as-of-date slider all live-update
   the chart smoothly."
   STATUS: MET for IV and price-range sliders (both verified live via
   Playwright: price-range slider drag confirmed chart+label update).
   As-of-date slider is wired identically (same on_change pattern, same
   refresh() call) but was NOT individually click-tested in the browser
   this session -- same on_change fix that repaired the other two
   sliders applies to it, and it uses the exact same wiring pattern, so
   this is a reasonable but not 100%-individually-confirmed inference.
   FLAG: do one more quick check of the as-of-date slider specifically
   before final delivery, given it's the most spec-emphasized slider
   (the "key differentiator" per §3.5) and deserves direct confirmation,
   not inference from a sibling control's fix.

5. "Hovering the chart and every stat tile shows the tooltips specified
   in §7."
   STATUS: PARTIALLY VERIFIED. All required tooltip copy exists
   (ui/insights.py has all 10 required tooltip types) and is wired via
   NiceGUI's ui.tooltip() on every stat_tile and the sliders. Actual
   mouse-hover rendering has NOT been visually confirmed via Playwright
   in this session (only inspected structurally / confirmed the tooltip
   elements exist in the DOM). FLAG: do a hover-triggered screenshot
   check before final delivery -- straightforward with Playwright's
   .hover() method, should do this.

6. "Profit table matches the chart's math at every column (spot-check a
   few cells against the engine directly in tests)."
   STATUS: MET. test_profit_table.py's test_profit_table_cells_match_
   asof_payoff_directly proves every cell equals a direct call to
   engine.payoff.asof_payoff for that exact (price, day) pair -- not a
   spot check but an exhaustive equality check across the tested grid.

7. "pytest suite passes, including put-call parity and breakeven/Max-P&L
   correctness tests."
   STATUS: MET. 138/138 tests passing, includes put-call parity (both
   scalar and full-grid-vectorized), Hull textbook reference values,
   breakeven correctness against closed-form vertical spread formulas,
   and both bounded + unbounded Max P/L cases.

8. "README clearly documents Greek unit conventions, the POP model
   assumption, and reiterates that all market data is simulated."
   STATUS: NOT YET DONE -- writing the final README next, this is the
   immediate next step.

## IMMEDIATE NEXT STEPS (in order)
1. Quick direct check of the as-of-date slider (item 4 flag above)
2. Quick hover-tooltip visual check (item 5 flag above)
3. Write the final comprehensive README (item 8)
4. Final full test run + final screenshot bundle for delivery

## FLAGGED GAPS CLOSED (items 4 and 5 from acceptance checklist)
Extended scripts/interactivity_check.py with two more checks:
- As-of-date slider: confirmed directly (not inferred) via Playwright --
  label updates "Today" -> "+15d", and critically, the screenshot shows
  the dashed amber "As Of Date" curve correctly BOWING INSIDE the solid
  white expiration curve (visually distinct, not a linear blend) for the
  AAPL Iron Condor -- this is genuine, visually-confirmed proof of the
  spec's "key differentiator" requirement (§3.5) working correctly.
- Hover tooltip: confirmed directly via Playwright .hover() + screenshot
  -- the Delta tile's tooltip renders with the correct dynamic copy
  ("this position gains roughly $6.54 in value for every $1 the
  underlying moves down..."), correctly reflecting the live AAPL Iron
  Condor's actual Delta. Minor cosmetic note: the tooltip's background
  rendered as a plain light box rather than my intended dark-themed
  style (PALETTE.bg_panel_raised) -- functional and legible, just not
  perfectly on-theme, likely a Quasar CSS-specificity issue with
  ui.tooltip().style(...). DECISION: documenting as a minor known
  cosmetic gap in the README rather than spending further cycles on CSS
  specificity fights -- does not affect correctness or usability.

Both items 4 and 5 in the Section 10 checklist are now genuinely,
directly verified (not inferred from a sibling control).

## ALL SECTION 10 ACCEPTANCE ITEMS NOW STATUS: MET or HONESTLY CAVEATED
Only remaining true gap: item 1's "native window" specifically could not
be visually verified in this sandbox (no display for pywebview), though
the identical UI code IS fully verified working in web-mode. Will state
this plainly in the README. Item 8 (README) is the last piece of work.

## FINAL STEP: write the comprehensive README now.

## BUILD COMPLETE — FINAL STATE
- README.md: written, comprehensive (quick start, framework justification,
  architecture, Greek unit conventions, POP assumption, Max P/L design
  decision writeup, verification methodology, honest known-limitations
  section, non-goals reiteration).
- Repo cleaned of __pycache__/.pytest_cache for delivery.
- Final full test run on the clean tree: 138/138 passing.
- Final screenshot re-captured post-cleanup to confirm nothing broke:
  confirmed identical correct state (TSLA Bull Call Spread, correct
  Greeks/stats/chart/table/sidebar/flow tape).
- All Section 10 acceptance criteria addressed, most directly verified
  via real browser interaction (not just code review), remaining honest
  gaps (native-window-specific rendering, leg inline-edit, minor tooltip
  CSS theming) explicitly documented in the README rather than glossed
  over.

STATUS: ready for delivery.

## !!! CORRECTION (audit #2, honest) — earlier "BUILD COMPLETE" was WRONG !!!
Re-reading the spec against the code found real, unbuilt requirements.
The earlier "all acceptance items MET" claim was overstated. Actual gaps:
 G1 §3.6 view-mode tabs (P/L%, Contract Value, % Max Risk, Δ Γ Θ ν ρ curves) — NOT BUILT
 G2 §3.4 strike ruler w/ draggable strike chips + expiration selector row — NOT BUILT
 G3 §3.9 inline leg edit (strike/qty/direction/DTE) + per-leg premium shown — NOT BUILT
 G4 §3.3 Profit Index tile — NOT BUILT
 G5 §3.7 advanced panel (risk-free rate / dividend yield override) — NOT BUILT
 G6 §7 chart crosshair tooltip (price, P/L $ and %, dominant Greeks) — NOT BUILT
 G7 §7 breakeven-marker hover explanation — NOT BUILT (markLine is silent)
 G8 §6 controls are destroyed/rebuilt by refresh() on every change -> a real
    mouse DRAG on a slider likely breaks (keyboard test masked this) — BUG
 G9 chart gradient splits at bbox midpoint, not at y=0 (faint green band
    under the $0 line in AAPL screenshot) — BUG
 G10 present_files never called; zip in outputs is stale until rebuilt.
PLAN (in order): engine view-mode fns+tests -> chart.py (G6,G7,G9) ->
components (G3,G4) -> layout.py restructure (G8, G1, G2, G5) -> real
Playwright MOUSE-drag tests -> README/zip/present_files.
- G1 engine side DONE (engine/views.py + tests/test_views.py); G4 profit_index engine DONE
- G9 DONE (clipped profit/loss fill series split exactly at y=0), G6 DONE
  (precomputed crosshair tooltip: price, P/L $ + %, Greeks, dominant Greek),
  G7 DONE (hoverable breakeven markers w/ explanation). ui/chart.py rewritten,
  tests/test_chart.py now 9 tests. NOT yet visually verified in browser.
- NEXT: ui/ruler.py (+tests), components (profit index tile, leg premium),
  layout.py restructure: static controls created ONCE (fixes G8), chart updated
  in place, edit-leg dialog (G3), view tabs (G1), advanced r/q panel (G5).
- ruler.py+tests DONE; components: profit index tile, leg premium, click-to-edit chips DONE (unverified in browser)
- layout.py RESTRUCTURED (static controls, in-place chart update, tabs, ruler, edit dialog, adv rates, profit idx). Now verifying in browser.
- full_check.py: 12/12 REAL-MOUSE checks pass (slider drag, ruler drag, tabs, edit dialog, crosshair, breakeven hover). chart animation disabled. G1,G2,G3,G4,G6,G7,G8,G9 verified. Remaining: G5 live check, regression of save/load+ticker, README/zip/present_files.
- G5 verified live (rate override changes Greeks), regression OK (save/load, ticker, strategy, expiration toggle). README updated. NEXT: rebuild zip + present_files (G10).

# ======================= RECOVERY (sandbox reset) =======================
EVENT: /home/claude was wiped between turns. Only /mnt/user-data/outputs/options_payoff_terminal.zip (Phase-1, Sep 29) survived.
LOST (being rebuilt to the CURRENT design, not replayed): accounts/store, FCO, PM, shell+prefs+templates, insights/explain, responsive
 layout, redesign (Long Call default, no snapshot card, no tape, PM order, bottom switcher + swipe), Aurora tokens, ~75 tests, check suites.
LESSON/RULE: /home/claude does NOT persist -> checkpoint a zip to /mnt/user-data/outputs after EVERY major step.
REBUILD ORDER: E engine (leg iv/premium, expected_value, futures, portfolio+csv, store, explain; tests) -> T theme/prefs/anim ->
 U ui (chart, components, ocp_tables, pm_tables, ocp, fco, pm, shell, app) -> V verify (shots light: phone->tablet->laptop) -> D docs.
STATUS: [x] base restored (152 tests green) [ ] E [ ] T [ ] U [ ] V [ ] D

## Perf pass: BSM kernel
- Replaced `scipy.stats.norm.cdf/pdf` with `scipy.special.ndtr` + closed-form PDF in `engine/pricing.py`; each CDF is now computed once per call.
- 400-pt grid: price 0.147 -> 0.041 ms, Greeks 0.279 -> 0.072 ms (~3.6-3.9x). Max abs diff vs prior outputs: 1.1e-15.
- Added `tests/test_pricing_regression.py` (put-call parity, scipy reference, expiry limit).

## Modernization pass 2
- Deps bumped & verified (153+ tests, app serves HTTP 200): numpy 2.5.5, scipy 1.18.1, nicegui 4.0.0, pytest 9.2.0. Dropped unused pandas.
- Fixed startup crash: `ui.components` imported `FlowRow` and the UI called `flow_tape`, neither existed in `engine/market_sim.py`. Implemented both (deterministic, own RNG stream) + test.
- New `engine/american.py`: vectorized CRR binomial American pricer (continuous yield), early-exercise premium.
- New `engine/futures.py`: contract registry (ES/MES/NQ/MNQ/RTY/M2K/YM/MYM/ZN/ZB/CL/GC/MGC), tick-exact P&L, fee-adjusted breakeven, margin-call & drawdown price levels, scale-in/out averaging, bracket R:R, roll/carry analysis, calendar spread P&L, Black-76 options on futures + composite P&L.
- **Margins in the registry are PLACEHOLDERS** (`margin_source="placeholder"`); `update_margins()` is the hook for the live data adapter.

## Not yet done (needs live API keys / UI work)
Portfolio ledger, UI wiring for futures + American pricing, data-freshness badges, adapters with backoff/caching, perf profiling under tick bursts.
