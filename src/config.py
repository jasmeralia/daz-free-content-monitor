"""Application-wide configuration loaded from environment / .env file."""

import logging
import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

logger = logging.getLogger(__name__)

_DEFAULT_TZ = "America/Los_Angeles"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "/app/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    discord_webhook_url: str = ""
    log_level: str = "INFO"
    log_file: str = "/app/data/daz_monitor.log"
    db_path: str = "/app/data/daz_monitor.db"
    check_interval_seconds: int = 3600
    dry_run: bool = False
    run_once: bool = False
    page_delay_min: float = 2.0
    page_delay_max: float = 5.0
    page_timeout_ms: int = 30000
    max_retries: int = 3
    startup_delay_seconds: int = 15
    display_timezone: str = _DEFAULT_TZ
    daz_email: str = ""
    daz_password: str = ""
    auto_claim: bool = False


def get_display_tz() -> ZoneInfo:
    """Return the configured display timezone, falling back to America/Los_Angeles."""
    tz_name = os.environ.get("DISPLAY_TIMEZONE", _DEFAULT_TZ).strip() or _DEFAULT_TZ
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError):
        logger.warning("Unknown timezone %r — falling back to %s", tz_name, _DEFAULT_TZ)
        return ZoneInfo(_DEFAULT_TZ)
