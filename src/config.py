"""
Application-wide configuration helpers read from environment variables.
"""

import logging
import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

_DEFAULT_TZ = "America/Los_Angeles"


def get_display_tz() -> ZoneInfo:
    """
    Return the configured display timezone.

    Reads DISPLAY_TIMEZONE from the environment; defaults to America/Los_Angeles.
    Falls back to the default if the configured value is not a valid IANA zone name.
    """
    tz_name = os.environ.get("DISPLAY_TIMEZONE", _DEFAULT_TZ).strip() or _DEFAULT_TZ
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError):
        logger.warning("Unknown timezone %r — falling back to %s", tz_name, _DEFAULT_TZ)
        return ZoneInfo(_DEFAULT_TZ)
