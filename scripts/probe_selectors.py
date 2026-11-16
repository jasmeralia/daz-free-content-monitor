"""
Probe script: loads the DAZ free-models page with Playwright and dumps
the innerHTML of the first few rendered product cards so we can identify
the correct CSS selectors for scraper.py.

Usage:
    python scripts/probe_selectors.py
"""

import asyncio

from playwright.async_api import async_playwright

FREE_URL = "https://www.daz3d.com/free-3d-models"
CONTAINER = "#slabs-container"
ITEM_SEL = "#slabs-container .item"


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        ctx = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )

        page = await ctx.new_page()
        print(f"Loading {FREE_URL} ...")
        await page.goto(FREE_URL, wait_until="networkidle", timeout=60_000)

        print(f"Waiting for {ITEM_SEL} ...")
        try:
            await page.wait_for_selector(ITEM_SEL, timeout=30_000)
            print("Items found!")
        except Exception as e:
            print(f"wait_for_selector failed: {e}")
            # Fall back: dump container HTML
            container_html: str = await page.evaluate(
                f"document.querySelector({CONTAINER!r})?.innerHTML ?? 'CONTAINER NOT FOUND'"
            )
            print(f"\n--- Container innerHTML (first 2000 chars) ---\n{container_html[:2000]}")
            await browser.close()
            return

        # Dump first 3 items
        items_html: list[str] = await page.evaluate(
            f"""() => Array.from(document.querySelectorAll({ITEM_SEL!r}))
                    .slice(0, 3)
                    .map(el => el.outerHTML)"""
        )
        print(f"\nFound {len(items_html)} items (showing first 3):\n")
        for i, html in enumerate(items_html):
            print(f"--- Item {i + 1} ---")
            print(html[:1500])
            print()

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
