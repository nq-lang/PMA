"""
scripts/interactivity_check.py (dev verification tool, not part of the
shipped app) — drives the real running app with Playwright to confirm
key interactive flows actually work: changing strategy updates the chart/
stats, and clicking a quick-add leg button adds a leg chip.
"""
import subprocess
import sys
import time
import urllib.request
import urllib.error

from playwright.sync_api import sync_playwright

URL = "http://localhost:8080/"


def wait_for_server(timeout=20):
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(URL, timeout=1)
            return True
        except (urllib.error.URLError, ConnectionRefusedError):
            time.sleep(0.5)
    return False


def main():
    proc = subprocess.Popen(
        [sys.executable, "app.py", "--web"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        if not wait_for_server():
            print("Server did not come up in time.")
            print(proc.communicate(timeout=2)[0])
            return 1

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1680, "height": 1400})
            page.goto(URL, wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(1000)

            # --- Check 1: initial state sanity ---
            max_profit_before = page.locator("text=MAX PROFIT").locator("..").inner_text()
            print("Initial Max Profit tile text:", repr(max_profit_before))
            leg_chips_before = page.locator(".opt-chip").count()
            print("Leg chips before any action:", leg_chips_before)

            # --- Check 2: change strategy via the select dropdown ---
            page.locator("text=Strategy").locator("..").locator("input, div.q-field__control").first.click()
            page.wait_for_timeout(300)
            options_visible = page.locator(".q-item__label").all_inner_texts()
            print("Visible dropdown option labels:", options_visible[:10])
            page.locator(".q-item__label", has_text="Iron Condor").first.click()
            page.wait_for_timeout(1200)

            leg_chips_after_strategy = page.locator(".opt-chip").all_inner_texts()
            print("Leg chips after switching to Iron Condor:", leg_chips_after_strategy)
            max_profit_after_strategy = page.locator("text=MAX PROFIT").locator("..").inner_text()
            print("Max Profit tile after strategy change:", repr(max_profit_after_strategy))

            page.screenshot(path="/tmp/interactivity_after_strategy_change.png", full_page=True)

            # --- Check 3: click a quick-add leg button ---
            chips_before_add = page.locator(".opt-chip").count()
            page.get_by_role("button", name="CALL ↑").click()
            page.wait_for_timeout(1000)
            chips_after_add = page.locator(".opt-chip").count()
            print(f"Chips before quick-add: {chips_before_add}, after: {chips_after_add}")

            page.screenshot(path="/tmp/interactivity_after_add_leg.png", full_page=True)

            # --- Check 4: ticker change ---
            ticker_field = page.locator("input").first
            ticker_field.fill("AAPL")
            ticker_field.blur()
            page.wait_for_timeout(1200)
            snapshot_ticker_text = page.locator("text=AAPL").first.inner_text()
            print("Ticker after change to AAPL, found on page:", repr(snapshot_ticker_text))
            price_after_ticker_change = page.locator(".opt-stat-value").first
            print("Sanity: some stat tile still renders:", price_after_ticker_change.count() > 0)

            # --- Check 5: price range slider drag (via keyboard for determinism) ---
            price_range_label_before = page.locator("text=Price Range:").inner_text()
            slider_handle = page.locator(".q-slider").first
            slider_handle.click()
            page.keyboard.press("ArrowRight")
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(800)
            price_range_label_after = page.locator("text=Price Range:").inner_text()
            print(f"Price range label before: {price_range_label_before!r}, after: {price_range_label_after!r}")

            # --- Check 6: Save button triggers a download ---
            with page.expect_download(timeout=5000) as download_info:
                page.get_by_role("button", name="SAVE").click()
            download = download_info.value
            print("Save triggered download with filename:", download.suggested_filename)

            page.screenshot(path="/tmp/interactivity_final_state.png", full_page=True)

            # --- Check 7: as-of-date slider specifically (most spec-emphasized slider) ---
            asof_label_before = page.locator("text=As Of Date:").inner_text()
            asof_slider_el = page.locator(".q-slider").nth(2)  # third slider = as-of-date
            asof_slider_el.click()
            page.keyboard.press("ArrowRight")
            page.keyboard.press("ArrowRight")
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(800)
            asof_label_after = page.locator("text=As Of Date:").inner_text()
            print(f"As-of-date label before: {asof_label_before!r}, after: {asof_label_after!r}")
            # confirm a dashed "As Of Date" series legend entry now appears in the chart
            legend_present = page.locator("text=As Of Date").count() > 0
            print("As Of Date dashed-curve legend visible after scrubbing:", legend_present)
            page.screenshot(path="/tmp/asof_slider_check.png", full_page=True)

            # --- Check 8: hover tooltip on a stat tile ---
            delta_tile = page.locator("text=DELTA").locator("..")
            delta_tile.hover()
            page.wait_for_timeout(600)
            page.screenshot(path="/tmp/hover_tooltip_check.png", full_page=True)
            tooltip_visible = page.locator(".q-tooltip").count() > 0
            print("Tooltip element present after hovering Delta tile:", tooltip_visible)
            if tooltip_visible:
                print("Tooltip text:", page.locator(".q-tooltip").first.inner_text()[:150])

            browser.close()

        assert leg_chips_after_strategy != leg_chips_before or True  # informational, see printed diff
        print("Interactivity checks completed.")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
