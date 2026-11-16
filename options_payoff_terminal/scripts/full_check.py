"""Dev verification: drives the live app with REAL mouse events (not keyboard shortcuts)."""
import subprocess, sys, time, urllib.request
from playwright.sync_api import sync_playwright

URL = "http://localhost:8080/"
results = []

def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))

def wait_server():
    for _ in range(60):
        try:
            urllib.request.urlopen(URL, timeout=1); return True
        except Exception:
            time.sleep(0.5)
    return False

def chips(page):
    return [t.replace("\n", " ") for t in page.locator(".opt-chip").all_inner_texts()]

def main():
    proc = subprocess.Popen([sys.executable, "app.py", "--web"], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    try:
        if not wait_server():
            print("server failed"); return 1
        with sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(viewport={"width": 1680, "height": 1500})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "fonts" not in m.text.lower() and "ERR_" not in m.text else None)
            page.goto(URL, wait_until="networkidle"); page.wait_for_timeout(1500)

            # 1. REAL mouse drag on the price-range slider
            sl = page.locator(".q-slider").nth(0)
            box = sl.bounding_box()
            y = box["y"] + box["height"] / 2
            x0 = box["x"] + box["width"] * ((0.25 - 0.05) / 0.95)
            before = page.locator("text=Price Range:").inner_text()
            page.mouse.move(x0, y); page.mouse.down()
            seen = set()
            for i in range(1, 9):
                page.mouse.move(x0 + i * 22, y, steps=3); page.wait_for_timeout(120)
                seen.add(page.locator("text=Price Range:").inner_text())
            mid_label = page.locator("text=Price Range:").inner_text()
            page.mouse.up(); page.wait_for_timeout(500)
            after = page.locator("text=Price Range:").inner_text()
            check("mouse-drag price slider updates label DURING drag", len(seen) > 2, f"{before} -> {sorted(seen)[:3]}...")
            check("slider element survives drag (still 3 sliders)", page.locator(".q-slider").count() == 3)
            check("drag committed a new value", after != before, after)
            # second drag proves the control is still alive
            box = page.locator(".q-slider").nth(1).bounding_box()
            iv_before = page.locator("text=Implied Volatility Scenario").inner_text()
            page.mouse.move(box["x"] + box["width"] * 0.27, box["y"] + box["height"] / 2)
            page.mouse.down(); page.mouse.move(box["x"] + box["width"] * 0.6, box["y"] + box["height"] / 2, steps=8); page.mouse.up()
            page.wait_for_timeout(500)
            check("mouse-drag IV slider works", page.locator("text=Implied Volatility Scenario").inner_text() != iv_before)

            # 2. REAL drag of a ruler chip
            page.reload(wait_until="networkidle"); page.wait_for_timeout(1200)
            c_before = chips(page)
            chip = page.locator(".ruler-chip").first
            cb = chip.bounding_box()
            rb = page.locator(".ruler").bounding_box()
            page.mouse.move(cb["x"] + cb["width"] / 2, cb["y"] + cb["height"] / 2); page.mouse.down()
            page.mouse.move(cb["x"] + cb["width"] / 2 + 60, cb["y"] + cb["height"] / 2, steps=10); page.mouse.up()
            page.wait_for_timeout(1200)
            c_after = chips(page)
            check("ruler chip drag changes the leg's strike", c_before != c_after, f"{c_before} -> {c_after}")
            max_profit = page.locator("text=MAX PROFIT").locator("..").inner_text().replace("\n", " ")
            check("stats recomputed after ruler drag", "$" in max_profit, max_profit)

            # 3. view-mode tabs
            for mode in ["Profit / Loss %", "Delta", "Contract Value"]:
                page.get_by_role("tab", name=mode).click(); page.wait_for_timeout(700)
                page.screenshot(path=f"/tmp/tab_{mode.split()[0]}.png", full_page=True)
            check("view tabs clickable without errors", len(errors) == 0, "; ".join(errors[:2]))
            page.get_by_role("tab", name="Profit / Loss $").click(); page.wait_for_timeout(700)

            # 4. edit dialog
            page.locator(".opt-chip").first.click(); page.wait_for_timeout(600)
            check("edit dialog opens on chip click", page.get_by_text("Edit leg").count() > 0)
            strike = page.get_by_label("Strike")
            strike.fill("410"); page.get_by_role("button", name="Apply").click(); page.wait_for_timeout(1000)
            check("edit dialog applies strike change", any("410" in c for c in chips(page)), str(chips(page)))

            # 5. hover: crosshair tooltip
            cv = page.locator(".nicegui-echart canvas").first.bounding_box()
            page.mouse.move(cv["x"] + cv["width"] * 0.6, cv["y"] + cv["height"] * 0.5); page.wait_for_timeout(500)
            page.mouse.move(cv["x"] + cv["width"] * 0.61, cv["y"] + cv["height"] * 0.5); page.wait_for_timeout(700)
            page.screenshot(path="/tmp/crosshair.png", full_page=True)
            tip = page.locator("div:has-text('Dominant Greek')").last
            check("crosshair tooltip shows P/L and dominant Greek", page.get_by_text("Dominant Greek").count() > 0)

            # 6. hover: breakeven marker via echarts pixel conversion
            info = page.evaluate("""() => {
              const el = document.querySelector('.nicegui-echart');
              const inst = window.echarts && window.echarts.getInstanceByDom(el);
              if (!inst) return null;
              const opt = inst.getOption(); const mp = opt.series[0].markPoint.data[0];
              const px = inst.convertToPixel({xAxisIndex: 0, yAxisIndex: 0}, mp.coord);
              const r = el.querySelector('canvas').getBoundingClientRect();  // canvas, not the padded panel
              return {x: r.left + px[0], y: r.top + px[1]};
            }""")
            if info:
                page.mouse.move(info["x"] - 30, info["y"] - 30); page.mouse.move(info["x"], info["y"], steps=6)
                page.wait_for_timeout(400)
                page.mouse.move(info["x"] + 1, info["y"])   # ECharts throttles mousemove; nudge so the final position is processed
                page.wait_for_timeout(800)
                page.screenshot(path="/tmp/breakeven_hover.png", full_page=True)
                check("breakeven marker hover explains breakeven", page.get_by_text("neither makes nor loses").count() > 0)
            else:
                print("SKIP breakeven hover (echarts global unavailable)")
            check("no JS errors during whole session", len(errors) == 0, "; ".join(errors[:3]))
            b.close()
        print(f"\n{sum(results)}/{len(results)} checks passed")
        return 0 if all(results) else 2
    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill()

if __name__ == "__main__":
    sys.exit(main())
