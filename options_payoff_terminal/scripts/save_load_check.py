"""
scripts/save_load_check.py (dev verification tool) — confirms the Save
button produces JSON that the Load dialog can consume to restore state.
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
            return 1

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1680, "height": 1400})
            page.goto(URL, wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(1000)

            # Switch to Iron Condor so the saved JSON is distinguishable
            # from the default Bull Call Spread.
            page.locator("text=Strategy").locator("..").locator("input, div.q-field__control").first.click()
            page.wait_for_timeout(300)
            page.locator(".q-item__label", has_text="Iron Condor").first.click()
            page.wait_for_timeout(1000)

            with page.expect_download(timeout=5000) as download_info:
                page.get_by_role("button", name="SAVE").click()
            download = download_info.value
            save_path = "/tmp/saved_strategy.json"
            download.save_as(save_path)
            with open(save_path) as f:
                saved_json_text = f.read()
            print("Saved JSON:", saved_json_text[:300])

            # Now switch to a different strategy so we can tell Load worked
            page.locator("text=Strategy").locator("..").locator("input, div.q-field__control").first.click()
            page.wait_for_timeout(300)
            page.locator(".q-item__label", has_text="Long Straddle").first.click()
            page.wait_for_timeout(1000)
            chips_after_switch = page.locator(".opt-chip").all_inner_texts()
            print("Chips after switching to Long Straddle:", chips_after_switch)

            # Open Load dialog, paste the saved JSON, confirm
            page.get_by_role("button", name="LOAD").click()
            page.wait_for_timeout(500)
            page.locator("textarea").fill(saved_json_text)
            page.locator("div[role='dialog']").get_by_role("button", name="Load", exact=True).click()
            page.wait_for_timeout(1200)

            chips_after_load = page.locator(".opt-chip").all_inner_texts()
            print("Chips after Load (should match Iron Condor's 4 legs):", chips_after_load)

            page.screenshot(path="/tmp/save_load_final.png", full_page=True)
            browser.close()

        print("Save/Load round-trip check complete.")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
