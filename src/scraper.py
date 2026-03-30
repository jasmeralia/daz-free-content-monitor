"""
DAZ 3D free-items scraper using Playwright (headless Chromium).

CSS selector constants are isolated at the top of this file for easy updates
if DAZ changes their page structure.  Verify these against the live page at
https://www.daz3d.com/free-3d-models if scraping breaks.
"""

import asyncio
import logging
import random
import re
from dataclasses import dataclass

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeout,
)

logger = logging.getLogger(__name__)

FREE_URL = "https://www.daz3d.com/free-3d-models"

# ---------------------------------------------------------------------------
# CSS selectors — update here if DAZ restructures their page
# ---------------------------------------------------------------------------

# Container for each product card on the grid
PRODUCT_CARD_SELECTOR = "#slabs-container .item"

# Anchor with href inside a card pointing to the product page
PRODUCT_LINK_SELECTOR = "a.slab-link"

# Element carrying the product title text
PRODUCT_TITLE_SELECTOR = "h2"

# Element carrying the price (shows "Free" for free items)
PRODUCT_PRICE_SELECTOR = ".prices-disp"

# ---------------------------------------------------------------------------
# Price recognition
# ---------------------------------------------------------------------------

FREE_PRICE_MARKERS = frozenset({"free", "$0.00", "0.00"})


def _is_free_price(price_text: str) -> bool:
    normalized = price_text.strip().lower().replace(",", "").replace(" ", "")
    return any(marker in normalized for marker in FREE_PRICE_MARKERS)


def _sku_from_url(url: str) -> str:
    """Derive a stable SKU from the product URL path segment."""
    path = url.rstrip("/").split("?")[0]  # strip query params
    return path.rstrip("/").split("/")[-1]


def _parse_card(href: str, title: str, price_text: str) -> "FreeItem | None":
    """
    Validate and construct a FreeItem from raw card data.
    Returns None if the item is not free, or if required fields are missing.
    """
    if not href or not title:
        return None
    if not _is_free_price(price_text):
        return None
    sku = _sku_from_url(href)
    if not sku:
        return None
    return FreeItem(sku=sku, title=title.strip(), url=href)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class FreeItem:
    sku: str
    title: str
    url: str


@dataclass
class ScrapeResult:
    items: list[FreeItem]
    error: str | None = None


@dataclass
class ScraperConfig:
    page_delay_min: float = 2.0
    page_delay_max: float = 5.0
    page_timeout_ms: int = 30_000
    max_retries: int = 3
    headless: bool = True


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


class ScraperError(Exception):
    pass


class DazScraper:
    def __init__(self, config: ScraperConfig | None = None) -> None:
        self._cfg = config or ScraperConfig()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def __aenter__(self) -> "DazScraper":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._cfg.headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
        )
        await self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        logger.info(
            "Playwright browser context initialized (chromium %s)",
            self._browser.version,
        )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.debug("Playwright browser context closed")

    async def _load_page(self, page: Page, url: str) -> None:
        try:
            await page.goto(url, wait_until="networkidle", timeout=self._cfg.page_timeout_ms)
        except PlaywrightTimeout as exc:
            raise ScraperError(f"Timeout loading {url}") from exc

        title = await page.title()
        title_lower = title.lower()
        if any(kw in title_lower for kw in ("access denied", "forbidden", "blocked")):
            raise ScraperError(f"Possible WAF block — page title: {title!r}")

        # Wait for at least one product card to confirm the grid rendered
        try:
            await page.wait_for_selector(PRODUCT_CARD_SELECTOR, timeout=self._cfg.page_timeout_ms)
        except PlaywrightTimeout:
            # Gracefully treat a missing grid as an empty page (end of pagination)
            logger.debug("No product cards found at %s — treating as empty page", url)

    async def _get_page_items(self, page: Page) -> list[FreeItem]:
        """Extract free items from the currently rendered page via DOM evaluation."""
        # Build the JS selectors into the evaluate call so we don't need
        # string interpolation inside the JS template.
        card_sel = PRODUCT_CARD_SELECTOR
        link_sel = PRODUCT_LINK_SELECTOR
        title_sel = PRODUCT_TITLE_SELECTOR
        price_sel = PRODUCT_PRICE_SELECTOR

        raw: list[dict[str, str]] = await page.evaluate(
            f"""() => {{
                const cards = document.querySelectorAll({card_sel!r});
                return Array.from(cards).map(card => {{
                    const link = card.querySelector({link_sel!r});
                    const titleEl = card.querySelector({title_sel!r});
                    const priceEl = card.querySelector({price_sel!r});
                    return {{
                        href: link ? link.href : '',
                        title: titleEl ? titleEl.textContent.trim() : '',
                        price: priceEl ? priceEl.textContent.trim() : '',
                    }};
                }});
            }}"""
        )

        items: list[FreeItem] = []
        for d in raw:
            item = _parse_card(d.get("href", ""), d.get("title", ""), d.get("price", ""))
            if item:
                items.append(item)
        return items

    async def _scrape_all(self, seen_skus: set[str]) -> list[FreeItem]:
        if self._context is None:
            raise ScraperError("Browser context not initialized")

        page = await self._context.new_page()
        all_items: list[FreeItem] = []

        try:
            for page_num in range(1, 500):  # hard cap to prevent runaway loops
                if page_num > 1:
                    delay = random.uniform(self._cfg.page_delay_min, self._cfg.page_delay_max)
                    logger.debug("Waiting %.1fs before page %d", delay, page_num)
                    await asyncio.sleep(delay)

                url = FREE_URL if page_num == 1 else f"{FREE_URL}?page={page_num}"
                logger.debug("Fetching page %d: %s", page_num, url)

                await self._load_page(page, url)
                page_items = await self._get_page_items(page)

                if not page_items:
                    logger.info("Page %d returned no items — end of listings", page_num)
                    break

                all_items.extend(page_items)
                logger.info("Page %d: %d item(s) found", page_num, len(page_items))

                # Early stop: if every SKU on this page is already known, all
                # subsequent (older) pages will also be known.
                page_skus = {i.sku for i in page_items}
                if page_skus.issubset(seen_skus):
                    logger.info("Page %d: all SKUs already seen — stopping pagination", page_num)
                    break
        finally:
            await page.close()

        # Deduplicate by SKU (pages can overlap)
        seen: set[str] = set()
        unique: list[FreeItem] = []
        for item in all_items:
            if item.sku not in seen:
                seen.add(item.sku)
                unique.append(item)

        logger.info("Scrape complete: %d unique free item(s) found", len(unique))
        return unique

    async def scrape_with_retry(self, seen_skus: set[str]) -> ScrapeResult:
        last_error: Exception | None = None
        for attempt in range(self._cfg.max_retries + 1):
            try:
                items = await self._scrape_all(seen_skus)
                return ScrapeResult(items=items)
            except ScraperError as exc:
                last_error = exc
                logger.error("Scrape error on attempt %d: %s", attempt + 1, exc)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.exception("Unexpected error on attempt %d", attempt + 1)

            if attempt < self._cfg.max_retries:
                wait = 30.0 * (2**attempt) + random.uniform(0, 10)
                logger.info("Retrying in %.0fs", wait)
                await asyncio.sleep(wait)

        return ScrapeResult(
            items=[],
            error=f"Failed after {self._cfg.max_retries + 1} attempt(s): {last_error}",
        )


# ---------------------------------------------------------------------------
# Utility: extract SKU from product URL (used in import_orders and tests)
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[a-z0-9][a-z0-9\-]*[a-z0-9]", re.IGNORECASE)


def extract_sku_from_url(url: str) -> str:
    """Public wrapper around _sku_from_url for use in other modules."""
    return _sku_from_url(url)
