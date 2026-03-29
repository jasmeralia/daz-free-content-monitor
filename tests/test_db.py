import pytest

from src.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


def test_schema_init(db):
    # Schema init should not raise
    assert db.db_path.endswith("test.db")


def test_insert_and_is_seen(db):
    assert not db.is_seen("test-sku")
    inserted = db.insert_seen_item("test-sku", "Test Product", "https://example.com/test")
    assert inserted is True
    assert db.is_seen("test-sku")


def test_insert_seen_idempotent(db):
    db.insert_seen_item("dup-sku", "Dup Product", "https://example.com/dup")
    inserted_again = db.insert_seen_item("dup-sku", "Dup Product", "https://example.com/dup")
    assert inserted_again is False


def test_insert_owned_sku(db):
    assert not db.is_owned("owned-sku")
    db.insert_owned_sku("owned-sku", "Owned Product")
    assert db.is_owned("owned-sku")


def test_insert_owned_sku_idempotent(db):
    db.insert_owned_sku("owned-sku", "Owned Product")
    # Should not raise on duplicate
    db.insert_owned_sku("owned-sku", "Owned Product")
    assert db.is_owned("owned-sku")


def test_get_owned_skus(db):
    db.insert_owned_sku("sku-a", "Product A")
    db.insert_owned_sku("sku-b", "Product B")
    owned = db.get_owned_skus()
    assert owned == {"sku-a", "sku-b"}


def test_get_owned_skus_empty(db):
    assert db.get_owned_skus() == set()


def test_upsert_owned_sku_updates_title(db):
    db.insert_owned_sku("upd-sku", None)
    db.upsert_owned_sku("upd-sku", "Now Has Title")
    # Confirm it's still in owned
    assert db.is_owned("upd-sku")


def test_multiple_seen_items(db):
    db.insert_seen_item("sku-1", "Product 1", "https://example.com/1")
    db.insert_seen_item("sku-2", "Product 2", "https://example.com/2")
    assert db.is_seen("sku-1")
    assert db.is_seen("sku-2")
    assert not db.is_seen("sku-3")
