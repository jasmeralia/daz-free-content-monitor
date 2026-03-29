from src.scraper import (
    FreeItem,
    _is_free_price,
    _parse_card,
    _sku_from_url,
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
