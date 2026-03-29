import json
from unittest.mock import MagicMock, patch

from src.notifier import MAX_EMBEDS_PER_MESSAGE, DiscordNotifier
from src.scraper import FreeItem


def _make_item(n: int = 1) -> FreeItem:
    return FreeItem(
        sku=f"test-product-{n}",
        title=f"Test Product {n}",
        url=f"https://www.daz3d.com/test-product-{n}",
    )


def _mock_response(status: int) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestDiscordNotifier:
    def setup_method(self):
        self.notifier = DiscordNotifier("https://discord.com/api/webhooks/test/token")

    def test_send_empty_list(self):
        # Should succeed without making any HTTP calls
        with patch("urllib.request.urlopen") as mock_open:
            result = self.notifier.send([])
        assert result is True
        mock_open.assert_not_called()

    def test_send_single_item(self):
        with patch("urllib.request.urlopen", return_value=_mock_response(204)):
            result = self.notifier.send([_make_item()])
        assert result is True

    def test_embed_structure(self):
        captured: list[dict] = []

        def fake_urlopen(req, timeout=None):
            captured.append(json.loads(req.data.decode()))
            return _mock_response(204)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self.notifier.send([_make_item(1)])

        assert len(captured) == 1
        payload = captured[0]
        assert "embeds" in payload
        embeds = payload["embeds"]
        assert len(embeds) == 1
        embed = embeds[0]
        assert "New Free DAZ Item" in embed["title"]
        assert "Test Product 1" in embed["description"]
        assert "https://www.daz3d.com/test-product-1" in embed["description"]
        assert embed["color"] == 0x00B0F4

    def test_batching_over_10_items(self):
        items = [_make_item(i) for i in range(MAX_EMBEDS_PER_MESSAGE + 3)]
        call_count = 0

        def fake_urlopen(req, timeout=None):
            nonlocal call_count
            call_count += 1
            return _mock_response(204)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = self.notifier.send(items)

        assert result is True
        assert call_count == 2  # 10 + 3 → 2 batches

    def test_rate_limit_retry(self):
        import urllib.error

        call_count = 0

        def fake_urlopen(req, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise urllib.error.HTTPError(
                    url="",
                    code=429,
                    msg="Too Many Requests",
                    hdrs=None,
                    fp=__import__("io").BytesIO(b'{"retry_after": 0.1}'),
                )
            return _mock_response(204)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with patch("time.sleep"):  # don't actually sleep
                result = self.notifier.send([_make_item()])

        assert result is True
        assert call_count == 2

    def test_http_error_returns_false(self):
        import urllib.error

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(
                url="",
                code=500,
                msg="Internal Server Error",
                hdrs=None,
                fp=__import__("io").BytesIO(b"error"),
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = self.notifier.send([_make_item()])

        assert result is False
