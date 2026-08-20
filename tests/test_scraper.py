from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeout

from src.scraper import (
    DazScraper,
    FreeItem,
    ScraperConfig,
    ScraperError,
    _is_free_price,
    _parse_card,
    _sku_from_url,
    extract_sku_from_url,
)


class TestIsFreePrice:
    def test_free_string(self):
        assert _is_free_price("FREE") is True

    def test_free_lowercase(self):
        assert _is_free_price("free") is True

    def test_zero_dollars(self):
        assert _is_free_price("$0.00") is True

    def test_zero_no_dollar(self):
        assert _is_free_price("0.00") is True

    def test_paid_price(self):
        assert _is_free_price("$9.99") is False

    def test_paid_with_free_in_name(self):
        # Should not match "freedom" or similar if not a price marker
        assert _is_free_price("$14.99") is False

    def test_empty_string(self):
        assert _is_free_price("") is False

    def test_whitespace(self):
        assert _is_free_price("  FREE  ") is True


class TestSkuFromUrl:
    def test_simple_slug(self):
        assert (
            _sku_from_url("https://www.daz3d.com/genesis-9-starter-essentials")
            == "genesis-9-starter-essentials"
        )

    def test_trailing_slash(self):
        assert _sku_from_url("https://www.daz3d.com/some-product/") == "some-product"

    def test_with_query_params(self):
        assert _sku_from_url("https://www.daz3d.com/some-product?ref=free") == "some-product"

    def test_short_slug(self):
        assert _sku_from_url("https://www.daz3d.com/item") == "item"


class TestParseCard:
    def test_valid_free_item(self):
        item = _parse_card(
            "https://www.daz3d.com/cool-item",
            "Cool Item",
            "FREE",
        )
        assert item == FreeItem(
            sku="cool-item",
            title="Cool Item",
            url="https://www.daz3d.com/cool-item",
        )

    def test_valid_zero_price(self):
        item = _parse_card(
            "https://www.daz3d.com/another-item",
            "Another Item",
            "$0.00",
        )
        assert item is not None
        assert item.sku == "another-item"

    def test_paid_item_rejected(self):
        item = _parse_card(
            "https://www.daz3d.com/paid-item",
            "Paid Item",
            "$9.99",
        )
        assert item is None

    def test_missing_href_rejected(self):
        item = _parse_card("", "Some Item", "FREE")
        assert item is None

    def test_missing_title_rejected(self):
        item = _parse_card("https://www.daz3d.com/item", "", "FREE")
        assert item is None

    def test_title_whitespace_stripped(self):
        item = _parse_card(
            "https://www.daz3d.com/item",
            "  Padded Title  ",
            "FREE",
        )
        assert item is not None
        assert item.title == "Padded Title"


def test_extract_sku_from_url():
    assert extract_sku_from_url("https://www.daz3d.com/some-item") == "some-item"


def _mock_playwright_start(browser: MagicMock) -> MagicMock:
    """Build the object returned by `await async_playwright().start()`."""
    playwright_instance = MagicMock()
    playwright_instance.chromium.launch = AsyncMock(return_value=browser)
    playwright_instance.stop = AsyncMock()
    async_playwright_return = MagicMock()
    async_playwright_return.start = AsyncMock(return_value=playwright_instance)
    return async_playwright_return


class TestContextManager:
    async def test_aenter_configures_browser_and_context(self):
        browser = MagicMock()
        browser.version = "124.0"
        context = MagicMock()
        context.add_init_script = AsyncMock()
        browser.new_context = AsyncMock(return_value=context)
        browser.close = AsyncMock()
        context.close = AsyncMock()

        with patch(
            "src.scraper.async_playwright",
            return_value=_mock_playwright_start(browser),
        ):
            scraper = DazScraper()
            result = await scraper.__aenter__()
            assert result is scraper
            assert scraper._context is context
            await scraper.__aexit__()

        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()

    async def test_aexit_noop_when_never_entered(self):
        scraper = DazScraper()
        await scraper.__aexit__()  # must not raise


class TestLoadPage:
    async def test_success(self):
        page = MagicMock()
        page.goto = AsyncMock()
        page.title = AsyncMock(return_value="DAZ 3D Free Models")
        page.wait_for_selector = AsyncMock()
        scraper = DazScraper()

        await scraper._load_page(page, "https://www.daz3d.com/free-3d-models")

        page.goto.assert_awaited_once()

    async def test_goto_timeout_raises_scraper_error(self):
        page = MagicMock()
        page.goto = AsyncMock(side_effect=PlaywrightTimeout("timeout"))
        scraper = DazScraper()

        with pytest.raises(ScraperError, match="Timeout loading"):
            await scraper._load_page(page, "https://www.daz3d.com/free-3d-models")

    async def test_waf_block_raises_scraper_error(self):
        page = MagicMock()
        page.goto = AsyncMock()
        page.title = AsyncMock(return_value="Access Denied")
        scraper = DazScraper()

        with pytest.raises(ScraperError, match="WAF"):
            await scraper._load_page(page, "https://www.daz3d.com/free-3d-models")

    async def test_missing_grid_treated_as_empty_page(self):
        page = MagicMock()
        page.goto = AsyncMock()
        page.title = AsyncMock(return_value="DAZ 3D")
        page.wait_for_selector = AsyncMock(side_effect=PlaywrightTimeout("no cards"))
        scraper = DazScraper()

        await scraper._load_page(page, "https://www.daz3d.com/free-3d-models")


class TestGetPageItems:
    async def test_parses_valid_items_and_skips_invalid(self):
        page = MagicMock()
        page.evaluate = AsyncMock(
            return_value=[
                {"href": "https://www.daz3d.com/item-1", "title": "Item 1", "price": "FREE"},
                {"href": "https://www.daz3d.com/item-2", "title": "Item 2", "price": "$9.99"},
                {"href": "", "title": "", "price": ""},
            ]
        )
        scraper = DazScraper()

        items = await scraper._get_page_items(page)

        assert [i.sku for i in items] == ["item-1"]


class TestScrapeAll:
    def _scraper_with_context(self) -> tuple[DazScraper, MagicMock]:
        scraper = DazScraper()
        page = MagicMock()
        page.close = AsyncMock()
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        scraper._context = context
        return scraper, page

    async def test_raises_when_context_not_initialized(self):
        scraper = DazScraper()
        with pytest.raises(ScraperError, match="not initialized"):
            await scraper._scrape_all(set())

    async def test_stops_on_empty_page(self):
        scraper, page = self._scraper_with_context()
        item = FreeItem("a", "A", "https://www.daz3d.com/a")

        with (
            patch.object(scraper, "_load_page", new=AsyncMock()),
            patch.object(scraper, "_get_page_items", new=AsyncMock(side_effect=[[item], []])),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            items = await scraper._scrape_all(set())

        assert [i.sku for i in items] == ["a"]
        page.close.assert_awaited_once()

    async def test_stops_when_all_skus_already_known_to_db(self):
        scraper, _ = self._scraper_with_context()
        item = FreeItem("known", "Known", "https://www.daz3d.com/known")

        with (
            patch.object(scraper, "_load_page", new=AsyncMock()),
            patch.object(scraper, "_get_page_items", new=AsyncMock(return_value=[item])),
        ):
            items = await scraper._scrape_all({"known"})

        assert [i.sku for i in items] == ["known"]

    async def test_stops_when_page_repeats_current_run_skus(self):
        scraper, _ = self._scraper_with_context()
        item = FreeItem("a", "A", "https://www.daz3d.com/a")

        with (
            patch.object(scraper, "_load_page", new=AsyncMock()),
            patch.object(scraper, "_get_page_items", new=AsyncMock(side_effect=[[item], [item]])),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            items = await scraper._scrape_all(set())

        assert [i.sku for i in items] == ["a"]

    async def test_dedupes_items_across_pages(self):
        scraper, _ = self._scraper_with_context()
        item_a = FreeItem("a", "A", "https://www.daz3d.com/a")
        item_b = FreeItem("b", "B", "https://www.daz3d.com/b")

        with (
            patch.object(scraper, "_load_page", new=AsyncMock()),
            patch.object(
                scraper,
                "_get_page_items",
                new=AsyncMock(side_effect=[[item_a], [item_a, item_b], []]),
            ),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            items = await scraper._scrape_all(set())

        assert {i.sku for i in items} == {"a", "b"}


class TestScrapeWithRetry:
    async def test_success_returns_items_without_error(self):
        scraper = DazScraper(ScraperConfig(max_retries=2))
        item = FreeItem("a", "A", "https://www.daz3d.com/a")

        with patch.object(scraper, "_scrape_all", new=AsyncMock(return_value=[item])):
            result = await scraper.scrape_with_retry(set())

        assert result.error is None
        assert result.items == [item]

    async def test_scraper_error_exhausts_retries(self):
        scraper = DazScraper(ScraperConfig(max_retries=1))

        with (
            patch.object(scraper, "_scrape_all", new=AsyncMock(side_effect=ScraperError("boom"))),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            result = await scraper.scrape_with_retry(set())

        assert result.items == []
        assert "Failed after 2 attempt(s)" in result.error

    async def test_unexpected_exception_exhausts_retries(self):
        scraper = DazScraper(ScraperConfig(max_retries=0))

        with patch.object(scraper, "_scrape_all", new=AsyncMock(side_effect=RuntimeError("oops"))):
            result = await scraper.scrape_with_retry(set())

        assert result.items == []
        assert "oops" in result.error

    async def test_succeeds_after_transient_error(self):
        scraper = DazScraper(ScraperConfig(max_retries=2))
        item = FreeItem("a", "A", "https://www.daz3d.com/a")
        call_count = 0

        async def flaky(_seen_skus):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ScraperError("transient")
            return [item]

        with (
            patch.object(scraper, "_scrape_all", new=flaky),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            result = await scraper.scrape_with_retry(set())

        assert result.error is None
        assert call_count == 2
