"""
DAZ 3D store auto-claimer.

Logs in, adds all given free items to the cart one by one, then completes
a single $0 checkout at the end. Only one checkout is performed regardless
of how many items are added.

Selector constants are isolated at the top. Run scripts/probe_claim.py
to dump screenshots and selector matches when DAZ changes their store UI.
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from playwright.async_api import TimeoutError as PlaywrightTimeout

from .scraper import FreeItem

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Store URLs
# ---------------------------------------------------------------------------

LOGIN_URL = "https://www.daz3d.com/customer/account/login/"
CHECKOUT_URL = "https://www.daz3d.com/checkout/onepage/"

# ---------------------------------------------------------------------------
# CSS selectors — UNVERIFIED placeholders.
# Run: python scripts/probe_claim.py --email YOU@EXAMPLE.COM --password SECRET
# to get screenshots and selector matches, then update these constants.
# ---------------------------------------------------------------------------

# Login form — scoped to #login-form to avoid duplicate hidden header inputs
LOGIN_EMAIL_SELECTOR = "#login-form input[name='login[username]']"
LOGIN_PASSWORD_SELECTOR = "#login-form input[name='login[password]']"
LOGIN_SUBMIT_SELECTOR = "#send2"

# Element present only when authenticated (secondary check after URL-based check)
# Logout link reliably appears only when logged in
LOGGED_IN_SELECTOR = "a[href*='logout']"

# Product page: "Add to Cart" button (absent when item is already owned)
ADD_TO_CART_SELECTOR = "button.btn-cart"

# Product page: indicator that item is already in the user's library
# VERIFIED: button with class btn-product-owned / btn-purchased appears when owned
ALREADY_OWNED_SELECTOR = "button.btn-product-owned, button.btn-purchased"

# Header cart item count badge (sanity-check after add)
# UNVERIFIED — needs a probe run while logged in with items in cart
CART_BADGE_SELECTOR = ".cart-count, #header-cart-count"

# Checkout: final submit button for $0 orders (Magento 1.x onepage checkout review step)
# UNVERIFIED — checkout page 404s when cart is empty; verify on first real claim run
PLACE_ORDER_SELECTOR = (
    "#review-form-submit, "
    "button.btn-place-order, "
    "#review-buttons-container button, "
    "button[onclick*='review.save']"
)

# Success page element present after a completed order
# UNVERIFIED — verify on first real claim run through a completed checkout
ORDER_SUCCESS_SELECTOR = ".success-msg, .success-msg-box, h1.page-title"

# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass
class ClaimResult:
    claimed: list[FreeItem] = field(default_factory=list)
    skipped: list[FreeItem] = field(default_factory=list)  # already in library
    failed: list[FreeItem] = field(default_factory=list)
    checkout_ok: bool = False

    def summary(self) -> str:
        return (
            f"claimed={len(self.claimed)}, skipped={len(self.skipped)}, "
            f"failed={len(self.failed)}, checkout_ok={self.checkout_ok}"
        )


class ClaimerError(Exception):
    pass


@dataclass
class ClaimerConfig:
    page_timeout_ms: int = 30_000
    item_delay_min: float = 1.5
    item_delay_max: float = 3.5


# ---------------------------------------------------------------------------
# Claimer
# ---------------------------------------------------------------------------


class DazClaimer:
    """
    Playwright-based DAZ store claimer.

    Use as an async context manager:
        async with DazClaimer(email, password) as claimer:
            result = await claimer.claim_items(items)
    """

    def __init__(
        self,
        email: str,
        password: str,
        config: ClaimerConfig | None = None,
    ) -> None:
        self._email = email
        self._password = password
        self._cfg = config or ClaimerConfig()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def __aenter__(self) -> "DazClaimer":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
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
        logger.info("DazClaimer browser context initialized")
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.debug("DazClaimer browser context closed")

    async def claim_items(self, items: list[FreeItem]) -> ClaimResult:
        """
        Login, add every item to the cart, then do one checkout at the end.
        Returns a ClaimResult with per-item outcomes and overall checkout status.
        """
        result = ClaimResult()
        if not items:
            return result

        if self._context is None:
            raise ClaimerError("Not started — use 'async with DazClaimer(...) as claimer'")

        page = await self._context.new_page()
        try:
            await self._login(page)

            for item in items:
                delay = random.uniform(self._cfg.item_delay_min, self._cfg.item_delay_max)
                await asyncio.sleep(delay)
                outcome = await self._add_to_cart(page, item)
                if outcome == "added":
                    result.claimed.append(item)
                elif outcome == "skipped":
                    result.skipped.append(item)
                else:
                    result.failed.append(item)

            if result.claimed:
                result.checkout_ok = await self._checkout(page)
                if not result.checkout_ok:
                    logger.error("Checkout failed — %d item(s) remain in cart", len(result.claimed))
                    result.failed.extend(result.claimed)
                    result.claimed = []
            else:
                logger.info("No new items added to cart; skipping checkout")
        finally:
            await page.close()

        logger.info("Claim run complete: %s", result.summary())
        return result

    async def _login(self, page: Page) -> None:
        logger.info("Logging in to DAZ store as %s", self._email)
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=self._cfg.page_timeout_ms)

        try:
            # .last skips the hidden duplicate login form in the page header — wait_for_selector()
            # would resolve to that first (hidden) match and never see it become visible
            await page.locator(LOGIN_EMAIL_SELECTOR).last.wait_for(
                state="visible", timeout=self._cfg.page_timeout_ms
            )
        except PlaywrightTimeout as exc:
            raise ClaimerError(
                f"Login form not found at {LOGIN_URL} — "
                f"update LOGIN_EMAIL_SELECTOR (current: {LOGIN_EMAIL_SELECTOR!r}). "
                "Run scripts/probe_claim.py to find the correct selectors."
            ) from exc

        # Use .last to skip any hidden duplicate fields in the page header
        await page.locator(LOGIN_EMAIL_SELECTOR).last.fill(self._email)
        await page.locator(LOGIN_PASSWORD_SELECTOR).last.fill(self._password)
        async with page.expect_navigation(
            wait_until="networkidle", timeout=self._cfg.page_timeout_ms
        ):
            await page.locator(LOGIN_SUBMIT_SELECTOR).last.click()

        # Primary check: we should no longer be on the login URL
        if "/customer/account/login" in page.url:
            raise ClaimerError(
                f"Login failed — still on login page after submit (url={page.url}). "
                "Check DAZ_EMAIL / DAZ_PASSWORD credentials."
            )
        # Secondary CSS check if LOGGED_IN_SELECTOR is configured
        if LOGGED_IN_SELECTOR:
            logged_in = await page.query_selector(LOGGED_IN_SELECTOR)
            if not logged_in:
                logger.warning(
                    "LOGGED_IN_SELECTOR %r not found on %s — "
                    "update the selector or ignore if login otherwise succeeded",
                    LOGGED_IN_SELECTOR,
                    page.url,
                )
        logger.info("Login successful (url=%s)", page.url)

    async def _add_to_cart(self, page: Page, item: FreeItem) -> str:
        """
        Navigate to a product page and click Add to Cart.
        Returns 'added', 'skipped' (already in library), or 'failed'.
        """
        try:
            await page.goto(
                item.url, wait_until="domcontentloaded", timeout=self._cfg.page_timeout_ms
            )
        except PlaywrightTimeout:
            logger.warning("Timeout loading product page for %s — marking failed", item.sku)
            return "failed"

        already_owned = await page.query_selector(ALREADY_OWNED_SELECTOR)
        if already_owned:
            logger.info("Already in library — skipping: %s", item.sku)
            return "skipped"

        try:
            btn = await page.wait_for_selector(ADD_TO_CART_SELECTOR, timeout=10_000)
            if btn is None:
                logger.warning("Add to Cart button not found for %s", item.sku)
                return "failed"
            await btn.click()
            await page.wait_for_timeout(1500)
            logger.info("Added to cart: %s (%s)", item.title, item.sku)
            return "added"
        except PlaywrightTimeout:
            logger.warning("Add to Cart button timed out for %s", item.sku)
            return "failed"

    async def _checkout(self, page: Page) -> bool:
        """Navigate to checkout and complete the $0 order. Returns True on success."""
        logger.info("Proceeding to checkout")
        timeout = self._cfg.page_timeout_ms
        try:
            await page.goto(CHECKOUT_URL, wait_until="domcontentloaded", timeout=timeout)

            btn = await page.wait_for_selector(PLACE_ORDER_SELECTOR, timeout=timeout)
            if btn is None:
                logger.error(
                    "Place Order button not found — "
                    "update PLACE_ORDER_SELECTOR. Run scripts/probe_claim.py."
                )
                return False

            await btn.click()
            await page.wait_for_load_state("networkidle", timeout=self._cfg.page_timeout_ms)

            success_el = await page.query_selector(ORDER_SUCCESS_SELECTOR)
            url_ok = "success" in page.url.lower() or "thank" in page.url.lower()
            if success_el or url_ok:
                logger.info("Checkout completed successfully (url=%s)", page.url)
                return True

            # No explicit failure detected — assume success but warn for investigation
            logger.warning(
                "Order submitted but success page not confirmed (url=%s). "
                "Update ORDER_SUCCESS_SELECTOR or check checkout flow manually.",
                page.url,
            )
            return True
        except PlaywrightTimeout as exc:
            logger.error("Checkout timed out: %s", exc)
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected checkout error: %s", exc)
            return False
