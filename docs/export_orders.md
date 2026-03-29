# Exporting Your DAZ Order History

This guide explains how to export your order history from the DAZ 3D website
so you can seed the `owned_skus` table and prevent re-notification for items
you already own.

## Steps

1. Log in to your DAZ 3D account at https://www.daz3d.com
2. Navigate to **My Account** → **Order History**
3. Look for an **Export** or **Download** button (typically CSV format)
4. Save the file (e.g. `daz_orders.csv`)

> **Note:** The export option location may change as DAZ updates their site.
> If you cannot find it, check the Account Dashboard or contact DAZ support.

## Importing the CSV

Copy the CSV into your data directory and run the import script:

```bash
docker compose run --rm daz-monitor python scripts/import_orders.py \
  --csv /app/data/daz_orders.csv
```

Or, if running outside Docker:

```bash
python scripts/import_orders.py \
  --csv /path/to/daz_orders.csv \
  --db /path/to/daz_monitor.db
```

The script will detect the SKU and product name columns automatically.
It prints a summary of how many rows were imported.

## Column Detection

The import script looks for these column names (case-insensitive):

| Field | Accepted column names |
|---|---|
| SKU / Item # | `sku`, `item #`, `item#`, `item number`, `product id`, `productid` |
| Product Name | `product name`, `title`, `name`, `description` |

If your CSV uses different column names, update the `SKU_COLUMN_HINTS` and
`TITLE_COLUMN_HINTS` lists at the top of `scripts/import_orders.py`.

## Re-running

The import is safe to re-run — rows are upserted, so existing SKUs will not
be duplicated. Run it again whenever you purchase new items and want to prevent
notifications for them.
