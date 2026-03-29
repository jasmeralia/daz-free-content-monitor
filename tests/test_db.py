import sqlite3

import pytest

from src.db import Database
from src.scraper import FreeItem


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


def _item(n: int, sku: str | None = None) -> FreeItem:
    s = sku or f"product-{n}"
    return FreeItem(sku=s, title=f"Product {n}", url=f"https://www.daz3d.com/{s}")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_schema_init(db):
    conn = sqlite3.connect(db.db_path)
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    tables = {r[0] for r in rows}
    conn.close()
    assert "free_items" in tables
    assert "owned_skus" in tables
    assert "seen_items" not in tables


# ---------------------------------------------------------------------------
# sync_free_items + get_pending_notifications
# ---------------------------------------------------------------------------


def test_sync_new_item_pending(db):
    """A brand-new item should appear in pending notifications."""
    db.sync_free_items([_item(1)])
    pending = db.get_pending_notifications(owned_skus=set())
    assert len(pending) == 1
    assert pending[0].sku == "product-1"


def test_sync_stable_item_not_re_pending(db):
    """An already-notified active item should not appear in pending again."""
    item = _item(1)
    db.sync_free_items([item])
    db.mark_notified(item.sku)
    db.sync_free_items([item])  # second cycle — still active
    pending = db.get_pending_notifications(owned_skus=set())
    assert pending == []


def test_sync_item_removed_then_reappears(db):
    """An item that leaves and returns to the free list should re-trigger notification."""
    item = _item(1)
    db.sync_free_items([item])  # cycle 1: active
    db.mark_notified(item.sku)
    db.sync_free_items([])  # cycle 2: removed
    db.sync_free_items([item])  # cycle 3: reappears
    pending = db.get_pending_notifications(owned_skus=set())
    assert len(pending) == 1
    assert pending[0].sku == item.sku


def test_sync_owned_never_pending(db):
    """An owned item should never appear in pending notifications."""
    item = _item(1)
    db.insert_owned_sku(item.sku, item.title)
    db.sync_free_items([item])
    pending = db.get_pending_notifications(owned_skus={item.sku})
    assert pending == []


def test_sync_owned_never_pending_on_reappear(db):
    """An owned item that reappears after being inactive should still be suppressed."""
    item = _item(1)
    db.insert_owned_sku(item.sku, item.title)
    db.sync_free_items([item])
    db.sync_free_items([])  # removed
    db.sync_free_items([item])  # reappears
    pending = db.get_pending_notifications(owned_skus={item.sku})
    assert pending == []


def test_sync_deactivates_missing(db):
    """Items absent from the current scrape should become inactive."""
    item = _item(1)
    db.sync_free_items([item])  # active
    db.sync_free_items([])  # removed — should deactivate

    # Confirm it comes back as pending when it reappears
    db.sync_free_items([item])
    pending = db.get_pending_notifications(owned_skus=set())
    assert len(pending) == 1  # would be 0 if it hadn't been deactivated


def test_sync_empty_scrape_deactivates_all(db):
    """An empty scrape result should deactivate all currently-active items."""
    db.sync_free_items([_item(1), _item(2)])
    db.sync_free_items([])
    pending = db.get_pending_notifications(owned_skus=set())
    assert pending == []


def test_sync_first_seen_preserved(db):
    """first_seen should not be updated when the item is already in the DB."""
    item = _item(1)
    db.sync_free_items([item])

    conn = sqlite3.connect(db.db_path)
    first_after_insert = conn.execute(
        "SELECT first_seen FROM free_items WHERE sku=?", (item.sku,)
    ).fetchone()[0]
    conn.close()

    db.sync_free_items([item])  # second cycle

    conn = sqlite3.connect(db.db_path)
    first_after_update = conn.execute(
        "SELECT first_seen FROM free_items WHERE sku=?", (item.sku,)
    ).fetchone()[0]
    conn.close()

    assert first_after_insert == first_after_update


def test_sync_mixed_new_and_existing(db):
    """Only new/reactivated items appear in pending, not already-notified active ones."""
    item_a = _item(1, "sku-a")
    item_b = _item(2, "sku-b")
    db.sync_free_items([item_a])
    db.mark_notified(item_a.sku)
    db.sync_free_items([item_a, item_b])
    pending_skus = {i.sku for i in db.get_pending_notifications(owned_skus=set())}
    assert "sku-b" in pending_skus
    assert "sku-a" not in pending_skus


# ---------------------------------------------------------------------------
# mark_notified
# ---------------------------------------------------------------------------


def test_mark_notified(db):
    """After mark_notified, item should no longer appear in pending."""
    item = _item(1)
    db.sync_free_items([item])
    assert len(db.get_pending_notifications(owned_skus=set())) == 1
    db.mark_notified(item.sku)
    assert db.get_pending_notifications(owned_skus=set()) == []


def test_failed_notification_retried(db):
    """An item that was synced but not marked notified should be in pending next cycle."""
    item = _item(1)
    db.sync_free_items([item])
    # Simulate: notification was attempted but failed — mark_notified NOT called
    # Next cycle: item still on free list
    db.sync_free_items([item])
    pending = db.get_pending_notifications(owned_skus=set())
    assert len(pending) == 1
    assert pending[0].sku == item.sku


# ---------------------------------------------------------------------------
# owned_skus
# ---------------------------------------------------------------------------


def test_insert_owned_sku(db):
    assert not db.is_owned("owned-sku")
    db.insert_owned_sku("owned-sku", "Owned Product")
    assert db.is_owned("owned-sku")


def test_insert_owned_sku_idempotent(db):
    db.insert_owned_sku("owned-sku", "Owned Product")
    db.insert_owned_sku("owned-sku", "Owned Product")
    assert db.is_owned("owned-sku")


def test_get_owned_skus(db):
    db.insert_owned_sku("sku-a", "Product A")
    db.insert_owned_sku("sku-b", "Product B")
    assert db.get_owned_skus() == {"sku-a", "sku-b"}


def test_get_owned_skus_empty(db):
    assert db.get_owned_skus() == set()


def test_upsert_owned_sku_updates_title(db):
    db.insert_owned_sku("upd-sku", None)
    db.upsert_owned_sku("upd-sku", "Now Has Title")
    assert db.is_owned("upd-sku")


# ---------------------------------------------------------------------------
# Schema migration from v0.1.0
# ---------------------------------------------------------------------------


def test_migration_from_seen_items(tmp_path):
    """
    A v0.1.0 database with seen_items should be automatically migrated to
    free_items on Database initialization, with no re-notification flood.
    """
    db_path = str(tmp_path / "legacy.db")

    # Manually create the old v0.1.0 schema
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE seen_items (
            sku TEXT PRIMARY KEY, title TEXT NOT NULL,
            url TEXT NOT NULL, first_seen TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE owned_skus (
            sku TEXT PRIMARY KEY, title TEXT, added_at TEXT
        )
    """)
    conn.execute(
        "INSERT INTO seen_items VALUES "
        "('legacy-sku', 'Legacy Item', 'https://www.daz3d.com/legacy-item', "
        "'2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    # Initialize with the new Database class — should trigger migration
    db = Database(db_path)

    # Old table should be gone
    conn = sqlite3.connect(db_path)
    old_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='seen_items'"
    ).fetchone()
    conn.close()
    assert old_table is None

    # Migrated row should be in free_items as active and already-notified
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT sku, is_active, notified_at FROM free_items WHERE sku='legacy-sku'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[1] == 1  # is_active
    assert row[2] is not None  # notified_at set → will not re-notify

    # Confirm the migrated item does NOT appear in pending notifications
    db.sync_free_items(
        [
            FreeItem(
                sku="legacy-sku",
                title="Legacy Item",
                url="https://www.daz3d.com/legacy-item",
            )
        ]
    )
    pending = db.get_pending_notifications(owned_skus=set())
    assert pending == []
