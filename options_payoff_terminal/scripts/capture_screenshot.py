"""
scripts/capture_screenshot.py (throwaway verification script, not part of
the shipped app) — launches app.py as a subprocess, waits for it to be
ready, uses Playwright's real Chromium to load the page (letting the
Vue3/Quasar client JS actually execute), and saves a PNG screenshot.
"""
import subprocess
import sys
import time
import urllib.request
import urllib.error

from playwright.sync_api import sync_playwright

PORT = 8080
URL = f"http://localhost:{PORT}/"


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
            out, _ = proc.communicate(timeout=2)
            print(out)
            return 1

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1680, "height": 1400})
            page.goto(URL, wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(1500)  # let ECharts finish its render pass
            page.screenshot(path="/tmp/real_screenshot.png", full_page=True)
            browser.close()
        print("Screenshot saved.")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
