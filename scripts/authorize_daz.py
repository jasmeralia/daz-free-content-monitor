"""Open a visible DAZ sign-in session and save its Playwright storage state.

Run this on a desktop with a graphical browser available. Complete DAZ's sign-in
and any challenge manually in the opened browser. This script never fills
credentials or clicks the sign-in button.

Usage:
    python scripts/authorize_daz.py [--output data/daz-auth.json]
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.claimer import LOGGED_IN_SELECTOR, LOGIN_URL


async def authorize(output: Path, timeout_seconds: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context(locale="en-US")
        page = await context.new_page()
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        print("Sign in to DAZ in the opened browser, including any security challenge.")
        print(f"Waiting up to {timeout_seconds} seconds for {LOGGED_IN_SELECTOR!r}.")

        try:
            await page.locator(LOGGED_IN_SELECTOR).wait_for(
                state="visible", timeout=timeout_seconds * 1000
            )
            await context.storage_state(path=str(output))
            os.chmod(output, 0o600)
            print(f"Authorized session saved to {output} (permissions 0600).")
        finally:
            await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/daz-auth.json"))
    parser.add_argument("--timeout", type=int, default=900, help="Sign-in wait in seconds")
    args = parser.parse_args()
    asyncio.run(authorize(args.output, args.timeout))


if __name__ == "__main__":
    main()
