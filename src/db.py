import logging
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_items (
    sku        TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    url        TEXT NOT NULL,
    first_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS owned_skus (
    sku      TEXT PRIMARY KEY,
    title    TEXT,
    added_at TEXT
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


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
            conn.executescript(SCHEMA)
        logger.debug("Database initialized at %s", self.db_path)

    def is_seen(self, sku: str) -> bool:
        with self._get_conn() as conn:
            row = conn.execute("SELECT 1 FROM seen_items WHERE sku = ?", (sku,)).fetchone()
            return row is not None

    def insert_seen_item(self, sku: str, title: str, url: str) -> bool:
        """Insert item into seen_items. Returns True if newly inserted."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO seen_items (sku, title, url, first_seen)
                VALUES (?, ?, ?, ?)
                """,
                (sku, title, url, _now()),
            )
            return cursor.rowcount > 0

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

    def get_seen_skus(self) -> set[str]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT sku FROM seen_items").fetchall()
            return {r["sku"] for r in rows}

    def upsert_owned_sku(self, sku: str, title: str | None = None) -> None:
        """Insert or update an owned SKU (used by import_orders script)."""
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
