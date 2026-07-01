import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime

from .claimer import ClaimResult
from .config import get_display_tz
from .scraper import FreeItem

logger = logging.getLogger(__name__)

DISCORD_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/132.0.0.0 Safari/537.36"
)

MAX_EMBEDS_PER_MESSAGE = 10
EMBED_COLOR = 0x00B0F4  # blue — new free item notifications
COLOR_SUCCESS = 0x57F287  # green — all claimed, checkout OK
COLOR_PARTIAL = 0xFEE75C  # yellow — some claimed, some failed
COLOR_FAILURE = 0xED4245  # red — checkout failed or all items failed


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

    def send_claim_result(self, result: ClaimResult) -> bool:
        """Send a Discord embed summarising an auto-claim run. Returns True on success."""
        if not result.claimed and not result.failed:
            return True  # nothing happened worth reporting

        lines: list[str] = []

        if result.claimed:
            titles = ", ".join(i.title for i in result.claimed)
            lines.append(f"**Claimed ({len(result.claimed)}):** {titles}")
        if result.failed:
            titles = ", ".join(i.title for i in result.failed)
            lines.append(f"**Failed ({len(result.failed)}):** {titles}")
        if result.skipped:
            lines.append(f"**Already owned:** {len(result.skipped)} item(s) skipped")

        if result.claimed and result.checkout_ok and not result.failed:
            color = COLOR_SUCCESS
            title = f"✅ Auto-claimed {len(result.claimed)} item(s) — checkout OK"
        elif result.claimed and result.checkout_ok and result.failed:
            color = COLOR_PARTIAL
            title = (
                f"⚠️ Auto-claimed {len(result.claimed)}, {len(result.failed)} failed — checkout OK"
            )
        elif result.claimed and not result.checkout_ok:
            color = COLOR_FAILURE
            title = f"❌ Checkout failed — {len(result.claimed)} item(s) added to cart"
            lines.append("_Items remain in cart — complete checkout manually._")
        else:
            color = COLOR_FAILURE
            title = f"❌ Auto-claim failed for {len(result.failed)} item(s)"

        embed: dict[str, object] = {
            "title": title,
            "description": "\n".join(lines),
            "color": color,
            "footer": {
                "text": datetime.now(get_display_tz()).strftime("Claimed: %Y-%m-%d %H:%M %Z")
            },
        }
        ok = self._post_payload({"embeds": [embed]})
        if ok:
            logger.info("Discord claim-result notification sent: %s", result.summary())
        else:
            logger.error("Failed to send Discord claim-result notification")
        return ok
