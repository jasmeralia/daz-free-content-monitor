"""Read-only inspection of DAZ auto-claim selectors.

This probe never enters credentials, submits forms, adds items to the cart, or
places an order. For an authenticated inspection, pass a human-authorized
storage-state file created by scripts/authorize_daz.py.

Usage:
    python scripts/probe_claim.py [--storage-state data/daz-auth.json]
    python scripts/probe_claim.py --product https://www.daz3d.com/some-item
"""

import argparse
import asyncio
import sys
from pathlib import Path

from playwright.async_api import Page, async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.claimer import (  # noqa: E402
    ADD_TO_CART_SELECTOR,
    ALREADY_OWNED_SELECTOR,
    CART_BADGE_SELECTOR,
    CHECKOUT_URL,
    LOGGED_IN_SELECTOR,
    LOGIN_URL,
    ORDER_SUCCESS_SELECTOR,
    PLACE_ORDER_SELECTOR,
)

DEFAULT_PRODUCT_URL = "https://www.daz3d.com/genesis-9-starter-essentials"


async def _check(page: Page, label: str, selector: str) -> None:
    match = "FOUND" if await page.query_selector(selector) else "NOT FOUND"
    print(f"[{match}] {label}: {selector}")


async def probe(product_url: str, storage_state: Path | None) -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=str(storage_state) if storage_state else None,
            locale="en-US",
        )
        page = await context.new_page()

        print(f"Login marker at {LOGIN_URL}")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
        await _check(page, "authenticated marker", LOGGED_IN_SELECTOR)

        print(f"\nProduct selectors at {product_url}")
        await page.goto(product_url, wait_until="domcontentloaded", timeout=60_000)
        await _check(page, "add to cart", ADD_TO_CART_SELECTOR)
        await _check(page, "already owned", ALREADY_OWNED_SELECTOR)
        await _check(page, "cart badge", CART_BADGE_SELECTOR)

        print(f"\nCheckout selectors at {CHECKOUT_URL} (read only)")
        await page.goto(CHECKOUT_URL, wait_until="domcontentloaded", timeout=60_000)
        await _check(page, "place order button", PLACE_ORDER_SELECTOR)
        await _check(page, "order success marker", ORDER_SUCCESS_SELECTOR)

        await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product", default=DEFAULT_PRODUCT_URL)
    parser.add_argument("--storage-state", type=Path)
    args = parser.parse_args()
    if args.storage_state and not args.storage_state.is_file():
        parser.error(f"storage state file does not exist: {args.storage_state}")
    asyncio.run(probe(args.product, args.storage_state))


if __name__ == "__main__":
    main()
