"""
Import DAZ 3D order history CSV into the owned_skus table.

DAZ CSV column names vary across exports. This script uses flexible column
detection to handle common variations.

Usage:
    python scripts/import_orders.py --csv /app/data/daz_orders.csv
    python scripts/import_orders.py --csv /app/data/daz_orders.csv --db /app/data/daz_monitor.db

See docs/export_orders.md for instructions on exporting your order history.
"""

import argparse
import csv
import sys
from pathlib import Path

# Allow importing from src/ when run from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import Database  # noqa: E402

# Candidate column names for SKU / item number (case-insensitive substring match)
SKU_COLUMN_HINTS = ["sku", "item #", "item#", "item number", "product id", "productid"]

# Candidate column names for product name / title
TITLE_COLUMN_HINTS = ["product name", "title", "name", "description"]


def _find_column(headers: list[str], hints: list[str]) -> str | None:
    """Return the first header that contains any hint substring (case-insensitive)."""
    headers_lower = [h.lower().strip() for h in headers]
    for hint in hints:
        for i, h in enumerate(headers_lower):
            if hint in h:
                return headers[i]
    return None


def import_csv(csv_path: str, db_path: str) -> int:
    """
    Read the CSV and upsert into owned_skus.  Returns the number of rows imported.
    """
    db = Database(db_path)

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            print("ERROR: CSV has no headers.", file=sys.stderr)
            sys.exit(1)

        headers = list(reader.fieldnames)
        sku_col = _find_column(headers, SKU_COLUMN_HINTS)
        title_col = _find_column(headers, TITLE_COLUMN_HINTS)

        if not sku_col:
            print(
                f"ERROR: Could not find a SKU column. Headers found: {headers}\n"
                f"Expected one of: {SKU_COLUMN_HINTS}",
                file=sys.stderr,
            )
            sys.exit(1)

        if not title_col:
            print(
                f"WARNING: Could not find a title column. Headers found: {headers}\n"
                f"SKUs will be imported without titles."
            )

        count = 0
        skipped = 0
        for row in reader:
            sku = row.get(sku_col, "").strip()
            title = row.get(title_col, "").strip() if title_col else None

            if not sku:
                skipped += 1
                continue

            db.upsert_owned_sku(sku=sku, title=title or None)
            count += 1

    print(f"Imported {count} SKU(s). Skipped {skipped} row(s) with empty SKU.")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Import DAZ order history CSV into owned_skus")
    parser.add_argument("--csv", required=True, help="Path to DAZ order history CSV file")
    parser.add_argument(
        "--db",
        default="/app/data/daz_monitor.db",
        help="Path to the SQLite database (default: /app/data/daz_monitor.db)",
    )
    args = parser.parse_args()

    if not Path(args.csv).exists():
        print(f"ERROR: CSV file not found: {args.csv}", file=sys.stderr)
        sys.exit(1)

    import_csv(args.csv, args.db)


if __name__ == "__main__":
    main()
