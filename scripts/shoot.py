"""Capture console screenshots with Playwright (used for the deck + report)."""
import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("AEGIS_URL", "http://127.0.0.1:5000")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "screenshots")
os.makedirs(OUT, exist_ok=True)


def shot(page, name, full=False):
    path = os.path.join(OUT, name + ".png")
    page.screenshot(path=path, full_page=full)
    print("saved", path)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000},
                               device_scale_factor=2)
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(700)
        shot(page, "01_login")

        page.fill("#li-user", "admin")
        page.fill("#li-pass", "Admin@Aegis2026")
        page.click("#li-submit")
        page.wait_for_selector("#pane-mfa", state="visible")
        page.wait_for_timeout(600)
        shot(page, "02_mfa")
        if page.query_selector("#fill-otp"):
            page.click("#fill-otp")
        page.click("#mfa-submit")
        page.wait_for_url("**/console", timeout=20000)
        page.wait_for_timeout(2500)
        shot(page, "03_overview")

        page.click('[data-view="risk"]')
        page.wait_for_timeout(1200)
        page.click('[data-preset="credential_stuffing"]')
        page.wait_for_timeout(2200)
        shot(page, "04_risk_console")

        page.click('[data-view="monitor"]')
        page.wait_for_timeout(700)
        page.click('#speed-seg button[data-sp="350"]')
        page.click("#mon-toggle")
        page.wait_for_timeout(9000)
        shot(page, "05_live_monitor")
        page.click("#mon-toggle")

        page.click('[data-view="vault"]')
        page.wait_for_timeout(1200)
        page.click("#ss-split")
        page.wait_for_timeout(1200)
        shot(page, "06_vault")
        if page.query_selector("[data-tamper]"):
            page.query_selector("[data-tamper]").click()
            page.wait_for_timeout(1500)
            shot(page, "07_tamper_detected")
            page.click("[data-close]")

        page.click('[data-view="model"]')
        page.wait_for_timeout(2500)
        shot(page, "08_model_lab")
        page.evaluate("window.scrollTo(0, 900)")
        page.wait_for_timeout(600)
        shot(page, "09_model_drift")

        page.click('[data-view="audit"]')
        page.wait_for_timeout(1200)
        page.click("#verify-btn")
        page.wait_for_timeout(1200)
        shot(page, "10_audit")

        page.click('[data-view="admin"]')
        page.wait_for_timeout(1500)
        shot(page, "11_admin")

        browser.close()


if __name__ == "__main__":
    main()
