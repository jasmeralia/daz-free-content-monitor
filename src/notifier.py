import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime

from .config import get_display_tz
from .scraper import FreeItem

logger = logging.getLogger(__name__)

DISCORD_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/132.0.0.0 Safari/537.36"
)

MAX_EMBEDS_PER_MESSAGE = 10
EMBED_COLOR = 0x00B0F4  # blue


class DiscordNotifier:
    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    def _post_payload(self, payload: dict[str, object]) -> bool:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._webhook_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": DISCORD_UA,
            },
        )
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return resp.status in (200, 204)
            except urllib.error.HTTPError as exc:
                try:
                    err_body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    err_body = "<unreadable>"

                if exc.code == 429 and attempt < 2:
                    retry_after = 1.0
                    try:
                        retry_after = float(json.loads(err_body).get("retry_after", 1))
                    except Exception:
                        pass
                    logger.warning("Discord rate-limited (429), retrying in %.2fs", retry_after)
                    time.sleep(max(0.1, retry_after))
                    continue

                logger.error("Discord webhook HTTP %d: %s; body=%s", exc.code, exc.reason, err_body)
                return False
            except Exception as exc:
                logger.error("Discord webhook request failed: %s", exc)
                return False
        return False

    def _build_embed(self, item: FreeItem) -> dict[str, object]:
        return {
            "title": "\U0001f195 New Free DAZ Item",
            "description": f"**{item.title}**\n{item.url}",
            "color": EMBED_COLOR,
            "footer": {
                "text": datetime.now(get_display_tz()).strftime("Detected: %Y-%m-%d %H:%M %Z")
            },
        }

    def send(self, items: list[FreeItem]) -> bool:
        """Send Discord notifications for new free items. Returns True if all succeeded."""
        if not items:
            return True

        # Batch into groups of MAX_EMBEDS_PER_MESSAGE
        batches = [
            items[i : i + MAX_EMBEDS_PER_MESSAGE]
            for i in range(0, len(items), MAX_EMBEDS_PER_MESSAGE)
        ]

        all_ok = True
        for batch in batches:
            embeds = [self._build_embed(item) for item in batch]
            payload: dict[str, object] = {"embeds": embeds}
            ok = self._post_payload(payload)
            if ok:
                logger.info(
                    "Discord notification sent for %d item(s): %s",
                    len(batch),
                    ", ".join(i.title for i in batch),
                )
            else:
                logger.error(
                    "Failed to send Discord notification for batch of %d item(s)", len(batch)
                )
                all_ok = False

        return all_ok
