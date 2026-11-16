from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeout

from src.claimer import (
    ClaimerConfig,
    ClaimerError,
    ClaimResult,
    DazClaimer,
)
from src.scraper import FreeItem


def _item(n: int = 1) -> FreeItem:
    return FreeItem(
        sku=f"product-{n}",
        title=f"Product {n}",
        url=f"https://www.daz3d.com/product-{n}",
    )


def _mock_playwright_start(browser: MagicMock) -> MagicMock:
    """Build the object returned by `await async_playwright().start()`."""
    playwright_instance = MagicMock()
    playwright_instance.chromium.launch = AsyncMock(return_value=browser)
    playwright_instance.stop = AsyncMock()
    async_playwright_return = MagicMock()
    async_playwright_return.start = AsyncMock(return_value=playwright_instance)
    return async_playwright_return


class TestClaimResult:
    def test_summary_format(self):
        result = ClaimResult(
            claimed=[_item(1)], skipped=[_item(2)], failed=[_item(3)], checkout_ok=True
        )
        assert result.summary() == "claimed=1, skipped=1, failed=1, checkout_ok=True"


class TestContextManager:
    async def test_aenter_configures_browser_and_context(self):
        browser = MagicMock()
        context = MagicMock()
        context.storage_state = AsyncMock()
        browser.new_context = AsyncMock(return_value=context)
        browser.close = AsyncMock()
        context.close = AsyncMock()

        with patch(
            "src.claimer.async_playwright",
            return_value=_mock_playwright_start(browser),
        ):
            claimer = DazClaimer("data/daz-auth.json")
            result = await claimer.__aenter__()
            assert result is claimer
            assert claimer._context is context
            await claimer.__aexit__()

        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()

    async def test_aexit_noop_when_never_entered(self):
        claimer = DazClaimer("data/daz-auth.json")
        await claimer.__aexit__()  # must not raise


class TestClaimItems:
    def _claimer_with_context(self) -> tuple[DazClaimer, MagicMock]:
        claimer = DazClaimer("data/daz-auth.json")
        page = MagicMock()
        page.close = AsyncMock()
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        claimer._context = context
        return claimer, page

    async def test_empty_items_returns_default_result_without_login(self):
        claimer, _ = self._claimer_with_context()
        with patch.object(claimer, "_login", new=AsyncMock()) as mock_login:
            result = await claimer.claim_items([])
        assert result == ClaimResult()
        mock_login.assert_not_called()

    async def test_raises_when_context_not_initialized(self):
        claimer = DazClaimer("data/daz-auth.json")
        with pytest.raises(ClaimerError, match="Not started"):
            await claimer.claim_items([_item(1)])

    async def test_login_failure_marks_all_items_failed_without_crashing(self):
        claimer, page = self._claimer_with_context()
        items = [_item(1), _item(2)]

        with patch.object(
            claimer, "_login", new=AsyncMock(side_effect=ClaimerError("login timed out"))
        ):
            result = await claimer.claim_items(items)

        assert result.failed == items
        assert result.claimed == []
        page.close.assert_awaited_once()

    async def test_added_items_checked_out_successfully(self):
        claimer, page = self._claimer_with_context()
        items = [_item(1), _item(2)]

        with (
            patch.object(claimer, "_login", new=AsyncMock()),
            patch.object(claimer, "_add_to_cart", new=AsyncMock(return_value="added")),
            patch.object(claimer, "_checkout", new=AsyncMock(return_value=True)),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            result = await claimer.claim_items(items)

        assert result.claimed == items
        assert result.checkout_ok is True
        page.close.assert_awaited_once()

    async def test_checkout_failure_moves_claimed_to_failed(self):
        claimer, _ = self._claimer_with_context()
        items = [_item(1)]

        with (
            patch.object(claimer, "_login", new=AsyncMock()),
            patch.object(claimer, "_add_to_cart", new=AsyncMock(return_value="added")),
            patch.object(claimer, "_checkout", new=AsyncMock(return_value=False)),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            result = await claimer.claim_items(items)

        assert result.claimed == []
        assert result.failed == items
        assert result.checkout_ok is False

    async def test_no_items_added_skips_checkout(self):
        claimer, _ = self._claimer_with_context()
        items = [_item(1)]

        with (
            patch.object(claimer, "_login", new=AsyncMock()),
            patch.object(claimer, "_add_to_cart", new=AsyncMock(return_value="failed")),
            patch.object(claimer, "_checkout", new=AsyncMock()) as mock_checkout,
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            result = await claimer.claim_items(items)

        mock_checkout.assert_not_called()
        assert result.failed == items
        assert result.checkout_ok is False

    async def test_mixed_outcomes(self):
        claimer, _ = self._claimer_with_context()
        items = [_item(1), _item(2), _item(3)]
        outcomes = {"product-1": "added", "product-2": "skipped", "product-3": "failed"}

        async def fake_add_to_cart(_page, item):
            return outcomes[item.sku]

        with (
            patch.object(claimer, "_login", new=AsyncMock()),
            patch.object(claimer, "_add_to_cart", new=fake_add_to_cart),
            patch.object(claimer, "_checkout", new=AsyncMock(return_value=True)),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            result = await claimer.claim_items(items)

        assert [i.sku for i in result.claimed] == ["product-1"]
        assert [i.sku for i in result.skipped] == ["product-2"]
        assert [i.sku for i in result.failed] == ["product-3"]


class TestLogin:
    def _page_for_login(self) -> MagicMock:
        page = MagicMock()
        page.goto = AsyncMock()
        page.query_selector = AsyncMock(return_value=MagicMock())
        page.url = "https://www.daz3d.com/customer/account/"
        return page

    async def test_existing_human_authorized_session_is_accepted(self):
        claimer = DazClaimer("data/daz-auth.json")
        page = self._page_for_login()

        await claimer._login(page)

        page.goto.assert_awaited_once()
        assert page.goto.await_args.kwargs["wait_until"] == "domcontentloaded"
        page.query_selector.assert_awaited_once_with("a[href*='logout']")

    async def test_missing_session_requests_visible_human_authorization(self):
        claimer = DazClaimer("data/daz-auth.json")
        page = self._page_for_login()
        page.query_selector = AsyncMock(return_value=None)

        with pytest.raises(ClaimerError, match="sign-in session is missing or expired"):
            await claimer._login(page)

    async def test_still_on_login_page_raises(self):
        claimer = DazClaimer("data/daz-auth.json")
        page = self._page_for_login()
        page.url = "https://www.daz3d.com/customer/account/login/"

        with pytest.raises(ClaimerError, match="sign-in session is missing or expired"):
            await claimer._login(page)


class TestAddToCart:
    async def test_goto_timeout_returns_failed(self):
        claimer = DazClaimer("data/daz-auth.json")
        page = MagicMock()
        page.goto = AsyncMock(side_effect=PlaywrightTimeout("timeout"))

        outcome = await claimer._add_to_cart(page, _item(1))

        assert outcome == "failed"

    async def test_already_owned_returns_skipped(self):
        claimer = DazClaimer("data/daz-auth.json")
        page = MagicMock()
        page.goto = AsyncMock()
        page.query_selector = AsyncMock(return_value=MagicMock())

        outcome = await claimer._add_to_cart(page, _item(1))

        assert outcome == "skipped"

    async def test_add_to_cart_button_not_found_returns_failed(self):
        claimer = DazClaimer("data/daz-auth.json")
        page = MagicMock()
        page.goto = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)
        page.wait_for_selector = AsyncMock(return_value=None)

        outcome = await claimer._add_to_cart(page, _item(1))

        assert outcome == "failed"

    async def test_add_to_cart_button_timeout_returns_failed(self):
        claimer = DazClaimer("data/daz-auth.json")
        page = MagicMock()
        page.goto = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)
        page.wait_for_selector = AsyncMock(side_effect=PlaywrightTimeout("timeout"))

        outcome = await claimer._add_to_cart(page, _item(1))

        assert outcome == "failed"

    async def test_successful_add_returns_added(self):
        claimer = DazClaimer("data/daz-auth.json")
        page = MagicMock()
        page.goto = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)
        btn = MagicMock()
        btn.click = AsyncMock()
        page.wait_for_selector = AsyncMock(return_value=btn)
        page.wait_for_timeout = AsyncMock()

        outcome = await claimer._add_to_cart(page, _item(1))

        assert outcome == "added"
        btn.click.assert_awaited_once()


class TestCheckout:
    async def test_place_order_button_not_found_returns_false(self):
        claimer = DazClaimer("data/daz-auth.json")
        page = MagicMock()
        page.goto = AsyncMock()
        page.wait_for_selector = AsyncMock(return_value=None)

        assert await claimer._checkout(page) is False

    async def test_success_via_success_element(self):
        claimer = DazClaimer("data/daz-auth.json")
        page = MagicMock()
        page.goto = AsyncMock()
        btn = MagicMock()
        btn.click = AsyncMock()
        page.wait_for_selector = AsyncMock(return_value=btn)
        page.wait_for_load_state = AsyncMock()
        page.query_selector = AsyncMock(return_value=MagicMock())
        page.url = "https://www.daz3d.com/checkout/onepage/success/"

        assert await claimer._checkout(page) is True

    async def test_success_via_url_when_no_success_element(self):
        claimer = DazClaimer("data/daz-auth.json")
        page = MagicMock()
        page.goto = AsyncMock()
        btn = MagicMock()
        btn.click = AsyncMock()
        page.wait_for_selector = AsyncMock(return_value=btn)
        page.wait_for_load_state = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)
        page.url = "https://www.daz3d.com/checkout/onepage/thankyou/"

        assert await claimer._checkout(page) is True

    async def test_no_confirmation_still_treated_as_success(self, caplog):
        import logging

        claimer = DazClaimer("data/daz-auth.json")
        page = MagicMock()
        page.goto = AsyncMock()
        btn = MagicMock()
        btn.click = AsyncMock()
        page.wait_for_selector = AsyncMock(return_value=btn)
        page.wait_for_load_state = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)
        page.url = "https://www.daz3d.com/checkout/onepage/"

        with caplog.at_level(logging.WARNING):
            outcome = await claimer._checkout(page)

        assert outcome is True
        assert "success page not confirmed" in caplog.text

    async def test_timeout_returns_false(self):
        claimer = DazClaimer("data/daz-auth.json")
        page = MagicMock()
        page.goto = AsyncMock(side_effect=PlaywrightTimeout("timeout"))

        assert await claimer._checkout(page) is False

    async def test_unexpected_exception_returns_false(self):
        claimer = DazClaimer("data/daz-auth.json")
        page = MagicMock()
        page.goto = AsyncMock(side_effect=RuntimeError("boom"))

        assert await claimer._checkout(page) is False


class TestClaimerConfig:
    def test_defaults(self):
        cfg = ClaimerConfig()
        assert cfg.page_timeout_ms == 30_000
        assert cfg.item_delay_min == 1.5
        assert cfg.item_delay_max == 3.5
