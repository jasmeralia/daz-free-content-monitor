# Marking Items as Owned

Use this when you have acquired a free item and want the monitor to stop
notifying about it permanently — even if it reappears on the free list later.

## When to use it

- You claimed a free item and don't want any future reminders about it.
- You already own something that appeared in a first-run notification.

If you simply miss a notification and the item goes off the free list, you do
**not** need to do anything — you will be notified again if it ever returns.

## Usage

```bash
# By product URL
python scripts/mark_owned.py https://www.daz3d.com/genesis-9-starter-essentials

# By SKU slug (last path segment of the product URL)
python scripts/mark_owned.py genesis-9-starter-essentials

# Multiple items at once
python scripts/mark_owned.py https://www.daz3d.com/item-a https://www.daz3d.com/item-b

# Custom database path
python scripts/mark_owned.py --db /custom/path/daz_monitor.db <url-or-sku>
```

## Docker Compose

```bash
docker compose run --rm daz-monitor python scripts/mark_owned.py \
  https://www.daz3d.com/genesis-9-starter-essentials
```

## Notes

- The script is safe to run multiple times with the same SKU (idempotent).
- Titles are not stored when marking manually; this has no functional impact.
- To find the SKU for a product, copy the last path segment of its URL.
  For example: `https://www.daz3d.com/genesis-9-starter-essentials` → SKU is
  `genesis-9-starter-essentials`.
