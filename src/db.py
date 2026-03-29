import logging
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .config import get_display_tz
from .scraper import FreeItem

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS free_items (
    sku         TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1,
    notified_at TEXT
);

CREATE TABLE IF NOT EXISTS owned_skus (
    sku      TEXT PRIMARY KEY,
    title    TEXT,
    added_at TEXT
);
"""


def _now() -> str:
    return datetime.now(get_display_tz()).isoformat()


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _get_conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._get_conn() as conn:
            conn.executescript(SCHEMA)  # creates tables (issues implicit COMMIT)
        with self._get_conn() as conn:
            self._migrate(conn)  # atomic migration transaction
        logger.debug("Database initialized at %s", self.db_path)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Migrate v0.1.0 seen_items table to free_items if present."""
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='seen_items'"
        ).fetchone()
        if row is None:
            return
        # Treat all previously-seen items as already-notified to avoid a
        # re-notification flood on first startup after upgrade.
        cursor = conn.execute("""
            INSERT OR IGNORE INTO free_items
                (sku, title, url, first_seen, last_seen, is_active, notified_at)
            SELECT sku, title, url, first_seen, first_seen, 1, first_seen
            FROM seen_items
        """)
        conn.execute("DROP TABLE seen_items")
        logger.info("Migrated seen_items → free_items (%d row(s))", cursor.rowcount)

    def sync_free_items(self, items: list[FreeItem]) -> None:
        """
        Upsert all scraped items as active, deactivate items no longer on the
        free list, and reset notified_at to NULL for reactivated items so they
        trigger a new notification.
        """
        now = _now()
        current_skus = {item.sku for item in items}

        with self._get_conn() as conn:
            for item in items:
                conn.execute(
                    """
                    INSERT INTO free_items
                        (sku, title, url, first_seen, last_seen, is_active, notified_at)
                    VALUES (?, ?, ?, ?, ?, 1, NULL)
                    ON CONFLICT(sku) DO UPDATE SET
                        title       = excluded.title,
                        url         = excluded.url,
                        last_seen   = excluded.last_seen,
                        is_active   = 1,
                        notified_at = CASE
                            WHEN free_items.is_active = 0 THEN NULL
                            ELSE free_items.notified_at
                        END
                    """,
                    (item.sku, item.title, item.url, now, now),
                )

            if current_skus:
                placeholders = ",".join("?" * len(current_skus))
                conn.execute(
                    f"UPDATE free_items SET is_active = 0 "
                    f"WHERE is_active = 1 AND sku NOT IN ({placeholders})",
                    tuple(current_skus),
                )
            else:
                conn.execute("UPDATE free_items SET is_active = 0 WHERE is_active = 1")

    def get_pending_notifications(self, owned_skus: set[str]) -> list[FreeItem]:
        """Return active items that have not yet been successfully notified."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT sku, title, url FROM free_items WHERE is_active = 1 AND notified_at IS NULL"
            ).fetchall()
        return [
            FreeItem(sku=r["sku"], title=r["title"], url=r["url"])
            for r in rows
            if r["sku"] not in owned_skus
        ]

    def mark_notified(self, sku: str) -> None:
        """Record that a notification was successfully delivered for this SKU."""
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE free_items SET notified_at = ? WHERE sku = ?",
                (_now(), sku),
            )

    def get_owned_skus(self) -> set[str]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT sku FROM owned_skus").fetchall()
            return {r["sku"] for r in rows}

    def is_owned(self, sku: str) -> bool:
        with self._get_conn() as conn:
            row = conn.execute("SELECT 1 FROM owned_skus WHERE sku = ?", (sku,)).fetchone()
            return row is not None

    def insert_owned_sku(self, sku: str, title: str | None = None) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO owned_skus (sku, title, added_at)
                VALUES (?, ?, ?)
                """,
                (sku, title, _now()),
            )

    def upsert_owned_sku(self, sku: str, title: str | None = None) -> None:
        """Insert or update an owned SKU (used by mark_owned script)."""
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO owned_skus (sku, title, added_at)
                VALUES (?, ?, ?)
                ON CONFLICT(sku) DO UPDATE SET
                    title = COALESCE(excluded.title, title)
                """,
                (sku, title, _now()),
            )
