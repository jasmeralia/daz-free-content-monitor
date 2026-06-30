"""
Probe script: validate DAZ store login and checkout CSS selectors in claimer.py.

Navigates login → product page → checkout, checks each selector, and saves
screenshots to data/probe_claim/ so you can identify the correct selectors
and update the constants in src/claimer.py.

Usage:
    DAZ_EMAIL=you@example.com DAZ_PASSWORD=secret python scripts/probe_claim.py
    python scripts/probe_claim.py --email you@example.com --password secret
    python scripts/probe_claim.py --product https://www.daz3d.com/some-free-item
    python scripts/probe_claim.py --headless

Runs headed (visible browser) by default so you can watch what happens.
After running, open data/probe_claim/ to review screenshots alongside the
selector output, then update the constants at the top of src/claimer.py.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright  # noqa: E402

from src.claimer import (  # noqa: E402
    ADD_TO_CART_SELECTOR,
    ALREADY_OWNED_SELECTOR,
    CART_BADGE_SELECTOR,
    CHECKOUT_URL,
    LOGGED_IN_SELECTOR,
    LOGIN_EMAIL_SELECTOR,
    LOGIN_PASSWORD_SELECTOR,
    LOGIN_SUBMIT_SELECTOR,
    LOGIN_URL,
    ORDER_SUCCESS_SELECTOR,
    PLACE_ORDER_SELECTOR,
)

SCREENSHOT_DIR = Path("data/probe_claim")
DEFAULT_PRODUCT_URL = "https://www.daz3d.com/genesis-9-starter-essentials"


def _check(label: str, found: bool) -> None:
    mark = "FOUND    " if found else "NOT FOUND"
    print(f"    [{mark}] {label}")


async def probe(email: str, password: str, product_url: str, headless: bool) -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await ctx.new_page()

        # ── 1. Login page ───────────────────────────────────────────────────
        print(f"\n[1] Login page: {LOGIN_URL}")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60_000)
        shot = SCREENSHOT_DIR / "01_login_page.png"
        await page.screenshot(path=str(shot), full_page=True)
        print(f"    Screenshot: {shot}")

        email_el = await page.query_selector(LOGIN_EMAIL_SELECTOR)
        pwd_el = await page.query_selector(LOGIN_PASSWORD_SELECTOR)
        sub_el = await page.query_selector(LOGIN_SUBMIT_SELECTOR)
        _check(f"LOGIN_EMAIL_SELECTOR    {LOGIN_EMAIL_SELECTOR!r}", bool(email_el))
        _check(f"LOGIN_PASSWORD_SELECTOR {LOGIN_PASSWORD_SELECTOR!r}", bool(pwd_el))
        _check(f"LOGIN_SUBMIT_SELECTOR   {LOGIN_SUBMIT_SELECTOR!r}", bool(sub_el))

        # ── 2. Submit login ─────────────────────────────────────────────────
        print(f"\n[2] Submitting login as {email}")
        if email_el and pwd_el and sub_el:
            await page.fill(LOGIN_EMAIL_SELECTOR, email)
            await page.fill(LOGIN_PASSWORD_SELECTOR, password)
            await page.screenshot(path=str(SCREENSHOT_DIR / "02_login_filled.png"), full_page=True)
            await page.click(LOGIN_SUBMIT_SELECTOR)
            await page.wait_for_load_state("networkidle", timeout=30_000)
            await page.screenshot(path=str(SCREENSHOT_DIR / "03_post_login.png"), full_page=True)
            print(f"    URL after submit: {page.url}")
            logged_in = await page.query_selector(LOGGED_IN_SELECTOR)
            _check(f"LOGGED_IN_SELECTOR {LOGGED_IN_SELECTOR!r}", bool(logged_in))
        else:
            print("    SKIPPED — fix login form selectors above first")

        # ── 3. Product page ─────────────────────────────────────────────────
        print(f"\n[3] Product page: {product_url}")
        await page.goto(product_url, wait_until="networkidle", timeout=30_000)
        await page.screenshot(path=str(SCREENSHOT_DIR / "04_product_page.png"), full_page=True)

        add_btn = await page.query_selector(ADD_TO_CART_SELECTOR)
        owned_el = await page.query_selector(ALREADY_OWNED_SELECTOR)
        badge = await page.query_selector(CART_BADGE_SELECTOR)
        _check(f"ADD_TO_CART_SELECTOR   {ADD_TO_CART_SELECTOR!r}", bool(add_btn))
        _check(f"ALREADY_OWNED_SELECTOR {ALREADY_OWNED_SELECTOR!r}", bool(owned_el))
        _check(f"CART_BADGE_SELECTOR    {CART_BADGE_SELECTOR!r}", bool(badge))

        # Dump button-like elements to help find the right Add to Cart selector
        btn_html: str = await page.evaluate(
            """() => {
                const sels = ['button', '[class*="add-to-cart"]', '[class*="AddToCart"]',
                              '[class*="buy"]', '[class*="purchase"]', '[class*="cart"]'];
                const seen = new Set();
                const out = [];
                for (const s of sels) {
                    for (const el of document.querySelectorAll(s)) {
                        const h = el.outerHTML;
                        if (!seen.has(h)) { seen.add(h); out.push(h); }
                        if (out.length >= 8) return out.join('\\n---\\n');
                    }
                }
                return out.join('\\n---\\n') || 'none found';
            }"""
        )
        print(f"\n    Button-like elements on product page:\n{btn_html[:3000]}")

        # ── 4. Checkout page ────────────────────────────────────────────────
        print(f"\n[4] Checkout: {CHECKOUT_URL}")
        await page.goto(CHECKOUT_URL, wait_until="networkidle", timeout=30_000)
        await page.screenshot(path=str(SCREENSHOT_DIR / "05_checkout.png"), full_page=True)
        print(f"    URL: {page.url}")

        place_btn = await page.query_selector(PLACE_ORDER_SELECTOR)
        success_el = await page.query_selector(ORDER_SUCCESS_SELECTOR)
        _check(f"PLACE_ORDER_SELECTOR   {PLACE_ORDER_SELECTOR!r}", bool(place_btn))
        _check(f"ORDER_SUCCESS_SELECTOR {ORDER_SUCCESS_SELECTOR!r}", bool(success_el))

        checkout_html: str = await page.evaluate(
            "() => (document.querySelector('form, main, .checkout-container') "
            "    ?? document.body).innerHTML"
        )
        print(f"\n    Checkout page HTML (first 3000 chars):\n{checkout_html[:3000]}")

        await browser.close()

    print(f"\nAll screenshots saved to: {SCREENSHOT_DIR}/")
    print("Update selector constants at the top of src/claimer.py based on this output.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe DAZ store claim-flow selectors and save screenshots"
    )
    parser.add_argument("--email", default=os.environ.get("DAZ_EMAIL", ""))
    parser.add_argument("--password", default=os.environ.get("DAZ_PASSWORD", ""))
    parser.add_argument(
        "--product",
        default=DEFAULT_PRODUCT_URL,
        help=f"Product URL to probe for Add-to-Cart selector (default: {DEFAULT_PRODUCT_URL})",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser headless (default: headed so you can watch)",
    )
    args = parser.parse_args()

    if not args.email or not args.password:
        print(
            "ERROR: Provide DAZ_EMAIL/DAZ_PASSWORD env vars or --email/--password flags",
            file=sys.stderr,
        )
        sys.exit(1)

    asyncio.run(probe(args.email, args.password, args.product, args.headless))


if __name__ == "__main__":
    main()
