"""
Query all stored data for a DAZ product by URL or SKU slug.

Prints a summary of the item's state in both the free_items and owned_skus
tables.  Useful for debugging notification state or confirming that mark_owned
took effect.

Usage:
    python scripts/query_sku.py <url-or-sku> [<url-or-sku> ...]
    python scripts/query_sku.py --db /custom/path/daz_monitor.db <url-or-sku>

Examples:
    python scripts/query_sku.py https://www.daz3d.com/genesis-9-starter-essentials
    python scripts/query_sku.py genesis-9-starter-essentials another-product-slug
"""

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scraper import extract_sku_from_url  # noqa: E402


def _resolve_sku(arg: str) -> str:
    if arg.startswith("http://") or arg.startswith("https://"):
        return extract_sku_from_url(arg)
    return arg.strip()


def _query_sku(conn: sqlite3.Connection, sku: str) -> None:
    print(f"SKU: {sku}")
    print("-" * 60)

    row = conn.execute(
        "SELECT title, url, first_seen, last_seen, is_active, notified_at "
        "FROM free_items WHERE sku = ?",
        (sku,),
    ).fetchone()

    if row:
        status = "active" if row["is_active"] else "inactive"
        notified = row["notified_at"] if row["notified_at"] else "pending (not yet delivered)"
        print(f"  [free_items]")
        print(f"    title      : {row['title']}")
        print(f"    url        : {row['url']}")
        print(f"    first_seen : {row['first_seen']}")
        print(f"    last_seen  : {row['last_seen']}")
        print(f"    status     : {status}")
        print(f"    notified_at: {notified}")
    else:
        print("  [free_items]  — not found")

    owned = conn.execute(
        "SELECT title, added_at FROM owned_skus WHERE sku = ?",
        (sku,),
    ).fetchone()

    if owned:
        title = owned["title"] or "(none)"
        print(f"  [owned_skus]")
        print(f"    title    : {title}")
        print(f"    added_at : {owned['added_at']}")
    else:
        print("  [owned_skus]  — not found")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query all DB data for one or more DAZ products."
    )
    parser.add_argument(
        "items",
        nargs="+",
        metavar="URL_OR_SKU",
        help="DAZ product URL(s) or SKU slug(s) to look up",
    )
    parser.add_argument(
        "--db",
        default="/app/data/daz_monitor.db",
        help="Path to the SQLite database (default: /app/data/daz_monitor.db)",
    )
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"ERROR: database not found: {args.db}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    for arg in args.items:
        sku = _resolve_sku(arg)
        if not sku:
            print(f"WARNING: Could not resolve SKU from {arg!r} — skipping", file=sys.stderr)
            continue
        _query_sku(conn, sku)

    conn.close()


if __name__ == "__main__":
    main()
