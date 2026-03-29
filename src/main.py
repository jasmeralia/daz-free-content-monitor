import asyncio
import logging
import logging.handlers
import os
import platform
import random
import sys
import time
from pathlib import Path

from .db import Database
from .notifier import DiscordNotifier
from .scraper import DazScraper, ScraperConfig
from .version import get_app_version

logger = logging.getLogger(__name__)


def _setup_logging(log_level: str, log_file: str) -> None:
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    level = getattr(logging, log_level.upper(), logging.INFO)

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10_485_760, backupCount=5
    )
    file_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)


def _log_runtime_info() -> None:
    logger.info("DAZ Free Content Monitor %s starting", get_app_version())
    logger.info("  python=%s  platform=%s", platform.python_version(), platform.platform())


def _get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _get_env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except ValueError:
        logger.warning("Invalid value for %s, using default %.1f", key, default)
        return default


def _get_env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        logger.warning("Invalid value for %s, using default %d", key, default)
        return default


def _get_env_bool(key: str) -> bool:
    return os.environ.get(key, "").lower() in ("1", "true", "yes")


def _load_scraper_config() -> ScraperConfig:
    return ScraperConfig(
        page_delay_min=_get_env_float("PAGE_DELAY_MIN", 2.0),
        page_delay_max=_get_env_float("PAGE_DELAY_MAX", 5.0),
        page_timeout_ms=_get_env_int("PAGE_TIMEOUT_MS", 30_000),
        max_retries=_get_env_int("MAX_RETRIES", 3),
    )


async def run_once(
    db: Database,
    scraper: DazScraper,
    notifier: DiscordNotifier,
    dry_run: bool,
) -> int:
    """
    Run one check cycle. Returns 0 on success, 1 on partial/scrape failure.
    """
    owned_skus = db.get_owned_skus()
    seen_skus = db.get_seen_skus()

    logger.info("Starting check (owned=%d, seen=%d)", len(owned_skus), len(seen_skus))

    result = await scraper.scrape_with_retry(seen_skus | owned_skus)

    if result.error:
        logger.error("Scrape failed: %s", result.error)
        return 1

    new_items = [
        item for item in result.items if item.sku not in owned_skus and item.sku not in seen_skus
    ]

    logger.info(
        "Scrape complete: %d total, %d new",
        len(result.items),
        len(new_items),
    )

    if not new_items:
        return 0

    if dry_run:
        logger.info("[DRY RUN] Would notify for %d item(s):", len(new_items))
        for item in new_items:
            logger.info("  %s — %s", item.sku, item.title)
        return 0

    for item in new_items:
        db.insert_seen_item(item.sku, item.title, item.url)

    ok = notifier.send(new_items)
    if not ok:
        logger.error("One or more Discord notifications failed")
        return 1

    return 0


def main() -> None:
    log_level = _get_env("LOG_LEVEL", "INFO")
    log_file = _get_env("LOG_FILE", "/app/data/daz_monitor.log")
    _setup_logging(log_level, log_file)
    _log_runtime_info()

    webhook_url = _get_env("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        logger.error("DISCORD_WEBHOOK_URL is not set — exiting")
        sys.exit(1)

    db_path = _get_env("DB_PATH", "/app/data/daz_monitor.db")
    check_interval = _get_env_int("CHECK_INTERVAL_SECONDS", 3600)
    dry_run = _get_env_bool("DRY_RUN")
    run_once_flag = _get_env_bool("RUN_ONCE")
    scraper_cfg = _load_scraper_config()

    if dry_run:
        logger.info("=== DRY RUN MODE — no DB writes or notifications ===")

    db = Database(db_path)
    notifier = DiscordNotifier(webhook_url)

    while True:

        async def _cycle() -> int:
            async with DazScraper(scraper_cfg) as scraper:
                return await run_once(db, scraper, notifier, dry_run)

        exit_code = asyncio.run(_cycle())

        if run_once_flag:
            sys.exit(exit_code)

        jitter = random.uniform(-check_interval * 0.1, check_interval * 0.1)
        sleep_for = max(60, check_interval + int(jitter))
        logger.info(
            "Cycle complete (exit=%d). Sleeping %ds before next check.", exit_code, sleep_for
        )
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
