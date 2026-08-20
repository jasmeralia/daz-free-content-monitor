import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.claimer import ClaimerConfig, ClaimResult
from src.main import (
    _autoclaim,
    _get_env,
    _get_env_bool,
    _get_env_float,
    _get_env_int,
    _load_claimer_config,
    _load_scraper_config,
    _log_runtime_info,
    _setup_logging,
    main,
    run_once,
)
from src.scraper import FreeItem, ScrapeResult


def _item(n: int = 1) -> FreeItem:
    return FreeItem(
        sku=f"product-{n}",
        title=f"Product {n}",
        url=f"https://www.daz3d.com/product-{n}",
    )


# ---------------------------------------------------------------------------
# Env var helpers
# ---------------------------------------------------------------------------


class TestGetEnv:
    def test_present(self, monkeypatch):
        monkeypatch.setenv("SOME_KEY", "  value  ")
        assert _get_env("SOME_KEY") == "value"

    def test_missing_uses_default(self, monkeypatch):
        monkeypatch.delenv("SOME_KEY", raising=False)
        assert _get_env("SOME_KEY", "fallback") == "fallback"


class TestGetEnvFloat:
    def test_valid(self, monkeypatch):
        monkeypatch.setenv("F", "3.5")
        assert _get_env_float("F", 1.0) == 3.5

    def test_missing_uses_default(self, monkeypatch):
        monkeypatch.delenv("F", raising=False)
        assert _get_env_float("F", 1.0) == 1.0

    def test_invalid_uses_default(self, monkeypatch):
        monkeypatch.setenv("F", "not-a-number")
        assert _get_env_float("F", 2.5) == 2.5


class TestGetEnvInt:
    def test_valid(self, monkeypatch):
        monkeypatch.setenv("I", "42")
        assert _get_env_int("I", 1) == 42

    def test_missing_uses_default(self, monkeypatch):
        monkeypatch.delenv("I", raising=False)
        assert _get_env_int("I", 7) == 7

    def test_invalid_uses_default(self, monkeypatch):
        monkeypatch.setenv("I", "nope")
        assert _get_env_int("I", 9) == 9


class TestGetEnvBool:
    @pytest.mark.parametrize("val", ["1", "true", "True", "yes", "YES"])
    def test_truthy(self, monkeypatch, val):
        monkeypatch.setenv("B", val)
        assert _get_env_bool("B") is True

    @pytest.mark.parametrize("val", ["0", "false", "no", ""])
    def test_falsy(self, monkeypatch, val):
        monkeypatch.setenv("B", val)
        assert _get_env_bool("B") is False

    def test_missing(self, monkeypatch):
        monkeypatch.delenv("B", raising=False)
        assert _get_env_bool("B") is False


# ---------------------------------------------------------------------------
# Config loaders
# ---------------------------------------------------------------------------


class TestLoadClaimerConfig:
    def test_disabled(self, monkeypatch):
        monkeypatch.delenv("AUTO_CLAIM", raising=False)
        assert _load_claimer_config() is None

    def test_enabled_missing_credentials(self, monkeypatch):
        monkeypatch.setenv("AUTO_CLAIM", "1")
        monkeypatch.delenv("DAZ_EMAIL", raising=False)
        monkeypatch.delenv("DAZ_PASSWORD", raising=False)
        assert _load_claimer_config() is None

    def test_enabled_with_credentials(self, monkeypatch):
        monkeypatch.setenv("AUTO_CLAIM", "1")
        monkeypatch.setenv("DAZ_EMAIL", "user@example.com")
        monkeypatch.setenv("DAZ_PASSWORD", "hunter2")
        result = _load_claimer_config()
        assert result is not None
        email, password, cfg = result
        assert email == "user@example.com"
        assert password == "hunter2"
        assert isinstance(cfg, ClaimerConfig)


class TestLoadScraperConfig:
    def test_defaults(self, monkeypatch):
        for key in ("PAGE_DELAY_MIN", "PAGE_DELAY_MAX", "PAGE_TIMEOUT_MS", "MAX_RETRIES"):
            monkeypatch.delenv(key, raising=False)
        cfg = _load_scraper_config()
        assert cfg.page_delay_min == 2.0
        assert cfg.page_delay_max == 5.0
        assert cfg.page_timeout_ms == 30_000
        assert cfg.max_retries == 3

    def test_overrides(self, monkeypatch):
        monkeypatch.setenv("PAGE_DELAY_MIN", "1.0")
        monkeypatch.setenv("PAGE_DELAY_MAX", "2.0")
        monkeypatch.setenv("PAGE_TIMEOUT_MS", "5000")
        monkeypatch.setenv("MAX_RETRIES", "1")
        cfg = _load_scraper_config()
        assert cfg.page_delay_min == 1.0
        assert cfg.page_delay_max == 2.0
        assert cfg.page_timeout_ms == 5000
        assert cfg.max_retries == 1


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------


class TestSetupLogging:
    def test_creates_log_file_and_handlers(self, tmp_path):
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        original_level = root.level
        log_file = tmp_path / "nested" / "app.log"
        try:
            _setup_logging("DEBUG", str(log_file))
            assert log_file.parent.is_dir()
            assert root.level == logging.DEBUG
            assert len(root.handlers) == 2
        finally:
            for handler in list(root.handlers):
                root.removeHandler(handler)
                handler.close()
            for handler in original_handlers:
                root.addHandler(handler)
            root.setLevel(original_level)

    def test_invalid_level_falls_back_to_info(self, tmp_path):
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        original_level = root.level
        log_file = tmp_path / "app.log"
        try:
            _setup_logging("NOT_A_LEVEL", str(log_file))
            assert root.level == logging.INFO
        finally:
            for handler in list(root.handlers):
                root.removeHandler(handler)
                handler.close()
            for handler in original_handlers:
                root.addHandler(handler)
            root.setLevel(original_level)


def test_log_runtime_info(caplog):
    with caplog.at_level(logging.INFO):
        _log_runtime_info()
    assert "DAZ Free Content Monitor" in caplog.text


# ---------------------------------------------------------------------------
# _autoclaim
# ---------------------------------------------------------------------------


class TestAutoclaim:
    async def test_claimed_and_skipped_recorded(self):
        claimed = [_item(1)]
        skipped = [_item(2)]
        failed = [_item(3)]
        claimer = MagicMock()
        claimer.claim_items = AsyncMock(
            return_value=ClaimResult(claimed=claimed, skipped=skipped, failed=failed)
        )
        db = MagicMock()

        result = await _autoclaim(claimer, db, claimed + skipped + failed)

        db.insert_owned_sku.assert_any_call("product-1", "Product 1")
        db.insert_owned_sku.assert_any_call("product-2", "Product 2")
        db.mark_notified.assert_called_once_with("product-2")
        assert result.claimed == claimed
        assert result.failed == failed

    async def test_no_skipped_or_failed(self):
        claimer = MagicMock()
        claimer.claim_items = AsyncMock(return_value=ClaimResult(claimed=[_item(1)]))
        db = MagicMock()

        result = await _autoclaim(claimer, db, [_item(1)])

        db.mark_notified.assert_not_called()
        assert result.claimed == [_item(1)]


# ---------------------------------------------------------------------------
# run_once
# ---------------------------------------------------------------------------


class TestRunOnce:
    def _deps(self):
        db = MagicMock()
        db.get_owned_skus.return_value = set()
        scraper = MagicMock()
        notifier = MagicMock()
        return db, scraper, notifier

    async def test_scrape_error_returns_1(self):
        db, scraper, notifier = self._deps()
        scraper.scrape_with_retry = AsyncMock(return_value=ScrapeResult(items=[], error="boom"))

        code = await run_once(db, scraper, notifier, dry_run=False)

        assert code == 1
        db.sync_free_items.assert_not_called()

    async def test_no_pending_returns_0(self):
        db, scraper, notifier = self._deps()
        scraper.scrape_with_retry = AsyncMock(return_value=ScrapeResult(items=[_item(1)]))
        db.get_pending_notifications.return_value = []

        code = await run_once(db, scraper, notifier, dry_run=False)

        assert code == 0
        notifier.send.assert_not_called()

    async def test_dry_run_without_claimer_sends_nothing(self):
        db, scraper, notifier = self._deps()
        scraper.scrape_with_retry = AsyncMock(return_value=ScrapeResult(items=[_item(1)]))
        db.get_pending_notifications.return_value = [_item(1)]

        code = await run_once(db, scraper, notifier, dry_run=True)

        assert code == 0
        notifier.send.assert_not_called()
        db.mark_notified.assert_not_called()

    async def test_dry_run_with_claimer_skips_claiming(self):
        db, scraper, notifier = self._deps()
        scraper.scrape_with_retry = AsyncMock(return_value=ScrapeResult(items=[_item(1)]))
        db.get_pending_notifications.return_value = [_item(1)]
        claimer = MagicMock()
        claimer.claim_items = AsyncMock()

        code = await run_once(db, scraper, notifier, dry_run=True, claimer=claimer)

        assert code == 0
        claimer.claim_items.assert_not_called()
        notifier.send_claim_result.assert_not_called()

    async def test_claimer_removes_handled_items_from_notify_queue(self):
        db, scraper, notifier = self._deps()
        items = [_item(1), _item(2), _item(3), _item(4)]
        scraper.scrape_with_retry = AsyncMock(return_value=ScrapeResult(items=items))
        db.get_pending_notifications.return_value = items
        claimer = MagicMock()
        claimer.claim_items = AsyncMock(
            return_value=ClaimResult(
                claimed=[items[0]], skipped=[items[1]], failed=[items[2]], checkout_ok=True
            )
        )
        notifier.send.return_value = True

        code = await run_once(db, scraper, notifier, dry_run=False, claimer=claimer)

        notifier.send_claim_result.assert_called_once()
        sent_batch = notifier.send.call_args[0][0]
        sent_skus = {i.sku for i in sent_batch}
        assert sent_skus == {"product-3", "product-4"}
        assert code == 0

    async def test_notify_batches_over_ten(self):
        db, scraper, notifier = self._deps()
        items = [_item(i) for i in range(15)]
        scraper.scrape_with_retry = AsyncMock(return_value=ScrapeResult(items=items))
        db.get_pending_notifications.return_value = items
        notifier.send.return_value = True

        code = await run_once(db, scraper, notifier, dry_run=False)

        assert notifier.send.call_count == 2
        assert db.mark_notified.call_count == 15
        assert code == 0

    async def test_notify_failure_returns_1_and_skips_mark_notified(self):
        db, scraper, notifier = self._deps()
        items = [_item(1)]
        scraper.scrape_with_retry = AsyncMock(return_value=ScrapeResult(items=items))
        db.get_pending_notifications.return_value = items
        notifier.send.return_value = False

        code = await run_once(db, scraper, notifier, dry_run=False)

        assert code == 1
        db.mark_notified.assert_not_called()

    async def test_retry_items_logged(self, caplog):
        db, scraper, notifier = self._deps()
        scraper.scrape_with_retry = AsyncMock(return_value=ScrapeResult(items=[_item(1)]))
        # Pending includes an item not present in this scrape's results.
        db.get_pending_notifications.return_value = [_item(1), _item(2)]
        notifier.send.return_value = True

        with caplog.at_level(logging.WARNING):
            code = await run_once(db, scraper, notifier, dry_run=False)

        assert "Retrying" in caplog.text
        assert code == 0


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


class TestMain:
    def _scraper_ctx(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    def test_missing_webhook_exits_1(self, monkeypatch, tmp_path):
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        monkeypatch.setenv("LOG_FILE", str(tmp_path / "app.log"))
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        try:
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            for handler in list(root.handlers):
                root.removeHandler(handler)
                handler.close()
            for handler in original_handlers:
                root.addHandler(handler)
        assert exc_info.value.code == 1

    def test_run_once_success(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/x/y")
        monkeypatch.setenv("RUN_ONCE", "1")
        monkeypatch.setenv("STARTUP_DELAY_SECONDS", "0")
        monkeypatch.setenv("LOG_FILE", str(tmp_path / "app.log"))
        monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
        monkeypatch.delenv("AUTO_CLAIM", raising=False)

        root = logging.getLogger()
        original_handlers = list(root.handlers)
        scraper_ctx = self._scraper_ctx()
        try:
            with (
                patch("src.main.Database", return_value=MagicMock()),
                patch("src.main.DiscordNotifier", return_value=MagicMock()),
                patch("src.main.DazScraper", return_value=scraper_ctx),
                patch("src.main.run_once", new=AsyncMock(return_value=0)) as mock_run_once,
                pytest.raises(SystemExit) as exc_info,
            ):
                main()
        finally:
            for handler in list(root.handlers):
                root.removeHandler(handler)
                handler.close()
            for handler in original_handlers:
                root.addHandler(handler)

        assert exc_info.value.code == 0
        mock_run_once.assert_awaited_once()
        # No claimer configured — run_once is called without a claimer arg at all.
        assert len(mock_run_once.call_args[0]) == 4

    def test_run_once_with_auto_claim(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/x/y")
        monkeypatch.setenv("RUN_ONCE", "1")
        monkeypatch.setenv("STARTUP_DELAY_SECONDS", "0")
        monkeypatch.setenv("LOG_FILE", str(tmp_path / "app.log"))
        monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
        monkeypatch.setenv("AUTO_CLAIM", "1")
        monkeypatch.setenv("DAZ_EMAIL", "user@example.com")
        monkeypatch.setenv("DAZ_PASSWORD", "hunter2")

        root = logging.getLogger()
        original_handlers = list(root.handlers)
        scraper_ctx = self._scraper_ctx()
        claimer_ctx = self._scraper_ctx()
        try:
            with (
                patch("src.main.Database", return_value=MagicMock()),
                patch("src.main.DiscordNotifier", return_value=MagicMock()),
                patch("src.main.DazScraper", return_value=scraper_ctx),
                patch("src.main.DazClaimer", return_value=claimer_ctx),
                patch("src.main.run_once", new=AsyncMock(return_value=0)) as mock_run_once,
                pytest.raises(SystemExit) as exc_info,
            ):
                main()
        finally:
            for handler in list(root.handlers):
                root.removeHandler(handler)
                handler.close()
            for handler in original_handlers:
                root.addHandler(handler)

        assert exc_info.value.code == 0
        claimer_arg = mock_run_once.call_args[0][4]
        assert claimer_arg is claimer_ctx

    def test_loop_continues_when_not_run_once(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/x/y")
        monkeypatch.delenv("RUN_ONCE", raising=False)
        monkeypatch.setenv("STARTUP_DELAY_SECONDS", "0")
        monkeypatch.setenv("CHECK_INTERVAL_SECONDS", "60")
        monkeypatch.setenv("LOG_FILE", str(tmp_path / "app.log"))
        monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
        monkeypatch.delenv("AUTO_CLAIM", raising=False)

        root = logging.getLogger()
        original_handlers = list(root.handlers)
        scraper_ctx = self._scraper_ctx()
        try:
            with (
                patch("src.main.Database", return_value=MagicMock()),
                patch("src.main.DiscordNotifier", return_value=MagicMock()),
                patch("src.main.DazScraper", return_value=scraper_ctx),
                patch("src.main.run_once", new=AsyncMock(return_value=0)),
                patch("time.sleep", side_effect=RuntimeError("stop-loop")) as mock_sleep,
                pytest.raises(RuntimeError, match="stop-loop"),
            ):
                main()
        finally:
            for handler in list(root.handlers):
                root.removeHandler(handler)
                handler.close()
            for handler in original_handlers:
                root.addHandler(handler)

        mock_sleep.assert_called_once()

    def test_startup_delay_sleeps(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/x/y")
        monkeypatch.setenv("RUN_ONCE", "1")
        monkeypatch.setenv("STARTUP_DELAY_SECONDS", "5")
        monkeypatch.setenv("LOG_FILE", str(tmp_path / "app.log"))
        monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
        monkeypatch.delenv("AUTO_CLAIM", raising=False)

        root = logging.getLogger()
        original_handlers = list(root.handlers)
        scraper_ctx = self._scraper_ctx()
        try:
            with (
                patch("src.main.Database", return_value=MagicMock()),
                patch("src.main.DiscordNotifier", return_value=MagicMock()),
                patch("src.main.DazScraper", return_value=scraper_ctx),
                patch("src.main.run_once", new=AsyncMock(return_value=0)),
                patch("time.sleep") as mock_sleep,
                pytest.raises(SystemExit),
            ):
                main()
        finally:
            for handler in list(root.handlers):
                root.removeHandler(handler)
                handler.close()
            for handler in original_handlers:
                root.addHandler(handler)

        mock_sleep.assert_any_call(5)
