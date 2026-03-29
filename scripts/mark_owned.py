"""
Mark DAZ 3D products as owned to permanently suppress future notifications.

Accepts one or more DAZ product URLs or SKU slugs as arguments.  Run this
after you have acquired a free item so the monitor will never notify about
it again, even if it returns to the free list.

Usage:
    python scripts/mark_owned.py <url-or-sku> [<url-or-sku> ...]
    python scripts/mark_owned.py --db /app/data/daz_monitor.db <url-or-sku>

Examples:
    python scripts/mark_owned.py https://www.daz3d.com/genesis-9-starter-essentials
    python scripts/mark_owned.py genesis-9-starter-essentials another-product-slug
    python scripts/mark_owned.py https://www.daz3d.com/item-a https://www.daz3d.com/item-b

Docker Compose:
    docker compose run --rm daz-monitor python scripts/mark_owned.py <url-or-sku>

See docs/mark_owned.md for full details.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import Database  # noqa: E402
from src.scraper import extract_sku_from_url  # noqa: E402


def _resolve_sku(arg: str) -> str:
    if arg.startswith("http://") or arg.startswith("https://"):
        return extract_sku_from_url(arg)
    return arg.strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mark DAZ products as owned to suppress future notifications."
    )
    parser.add_argument(
        "items",
        nargs="+",
        metavar="URL_OR_SKU",
        help="DAZ product URL(s) or SKU slug(s) to mark as owned",
    )
    parser.add_argument(
        "--db",
        default="/app/data/daz_monitor.db",
        help="Path to the SQLite database (default: /app/data/daz_monitor.db)",
    )
    args = parser.parse_args()

    db = Database(args.db)

    for arg in args.items:
        sku = _resolve_sku(arg)
        if not sku:
            print(f"WARNING: Could not resolve SKU from {arg!r} — skipping", file=sys.stderr)
            continue
        db.upsert_owned_sku(sku=sku, title=None)
        print(f"Marked as owned: {sku}")


if __name__ == "__main__":
    main()
