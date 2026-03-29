# DAZ Free Item Monitor — Project Context

## Goal

A Dockerized Python service that periodically checks the DAZ 3D store for
free items, filters out already-owned products, and sends Discord webhook
notifications with direct links to new free items.

# MANDATORY CHANGE PROCESS

1. After any change in the repository, run `make lint` and `make test`.
2. Any errors or warnings must be resolved before proceeding.
3. Update the version and run `make lint` again.
4. Add a new entry in CHANGELOG.md, and commit and push to both the 
master branch and a new tag specific to that version.

## Architecture

Same pattern as `adult_sub_monitor`: Playwright scraping, SQLite persistence,
Discord webhook notifications, Docker Compose deployment on TrueNAS SCALE
(Goldeye).

## Stack

- **Python 3.12**
- **Playwright** (async, Chromium) — for JS-rendered DAZ store pages
- **SQLite** (`data/daz_monitor.db`) — persists seen items and owned SKUs
- **APScheduler** or simple `asyncio.sleep` loop — hourly cadence
- **Discord webhook** — notification delivery
- **Docker Compose** — deployment

## Directory Layout

```
daz-monitor/
├── CLAUDE.md
├── docker-compose.yml
├── Dockerfile
├── docs/
│   └── export_orders.md  # guide on how to export order CSV
├── LICENSE               # MIT License
├── Makefile
├── README.md
├── requirements.txt      # modules actually required to run the app
├── requirements-dev.txt  # dev tools: ruff, mypy, pylint, includes requirements.txt
├── scripts/
│   └── import_orders.py  # one-shot CSV import for owned items
└── src/
    ├── main.py           # entrypoint, scheduler loop
    ├── scraper.py        # Playwright-based DAZ store scraper
    ├── db.py             # SQLite schema and queries
    └── notifier.py       # Discord webhook sender
```

## SQLite Schema

```sql
-- Products seen on the free listing (deduplication)
CREATE TABLE IF NOT EXISTS seen_items (
    sku         TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    first_seen  TEXT NOT NULL       -- ISO8601
);

-- Items you already own (seeded from CSV, kept up to date incrementally)
CREATE TABLE IF NOT EXISTS owned_skus (
    sku         TEXT PRIMARY KEY,
    title       TEXT,
    added_at    TEXT
);
```

## Scraping Strategy

### Free Listings Page

Target URL: `https://www.daz3d.com/free-3d-models`

- Paginate through all pages (URL param: `?page=N`)
- For each product card, extract:
  - SKU (from product URL slug or data attribute)
  - Title
  - Product URL
  - Price confirmation (assert "FREE" / "$0.00" to avoid false positives)
- Stop paginating when a page returns no products or a page already fully
  seen in `seen_items`

### Owned Items (Optional / Phase 2)

- DAZ lets you export order history from your account page
- `scripts/import_orders.py` reads the CSV and populates `owned_skus`
- Run manually when you want to refresh the owned list
- New free items auto-added via the monitor are appended to `owned_skus`
  after notification so they won't re-notify

## Main Loop (src/main.py)

```
on startup:
  init db
  load owned SKUs into memory set

every CHECK_INTERVAL_SECONDS:
  fetch all current free items from store
  for each item:
    if sku in owned_skus → skip
    if sku in seen_items → skip
    else:
      insert into seen_items
      send Discord notification
      (optional) insert into owned_skus so it doesn't re-notify
```

## Discord Notification Format

Each new free item gets an embed:

```
🆓 New Free DAZ Item

**[Product Title]**
https://www.daz3d.com/...

React with ✅ once added to your library.
```

Batch multiple new items into a single webhook call if several appear at once
(Discord allows up to 10 embeds per message). Use a delay between Discord posts
to prevent rate limiting.

## Dockerfile Notes

- Base: `mcr.microsoft.com/playwright/python:v1.44.0-jammy` (includes
  Chromium, avoids manual browser install)
- Or: `python:3.12-slim` + `playwright install --with-deps chromium` in build
- Run as non-root user
- `data/` directory should be a host mounted volume so SQLite persists across
  container restarts
- Environmental variables should be included in docker-compose.yml as TrueNAS
  does not support .env files.

## Docker Compose (sketch)

```yaml
services:
  daz-monitor:
    # build: .
    image: ghcr.io/jasmeralia/daz-free-content-monitor:latest
    restart: unless-stopped
    volumes:
      - /mnt/myzmirror/daz_data:/app/data
    environment:
      - PYTHONUNBUFFERED=1
      - DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
      - CHECK_INTERVAL_SECONDS=3600
```

## scripts/import_orders.py

Accepts the DAZ order history CSV export and upserts into `owned_skus`.
DAZ CSV columns vary but typically include Order #, Product Name, SKU/Item #,
Date. Map accordingly.

Usage:
```
docker compose run --rm daz-monitor python scripts/import_orders.py \
  --csv /app/data/daz_orders.csv
```

## Known Risks / Mitigations

| Risk | Mitigation |
|---|---|
| DAZ changes page structure | Playwright selectors in one file (`scraper.py`) — easy to update |
| Bot detection on listings page | Add random delays (2–5s) between page fetches; use real Chromium UA |
| Bot detection on account pages | Use Option A (CSV) instead of live library scrape |
| Free item disappears before you claim it | Notification includes direct URL; some DAZ free items are permanent |
| SQLite corruption on hard shutdown | WAL mode enabled; volume is on TrueNAS ZFS |

## Notes

- Similar architecture to `adult_sub_monitor` — reuse session management
  and webhook patterns where possible
- DAZ SKUs are stable identifiers; use them (not titles) as primary keys
- The free page does not require login to scrape — Phase 1 avoids auth
entirely

## Makefile

Implement lint checking with a combination of ruff, pylint, and mypy.
Create a Makefile that has a `lint` target to run these from within
the virtual environment. 

All Makefile targets should accept a PYTHON argument so that it
can be run via `make lint PYTHON=.venv/bin/python` or `make lint
PYTHON=.venv-win/Scripts/python.exe`.

Add Makefile targets `venv` and `venv-win` which bootstrap the
virtual environment for WSL or Windows, and then install the
pip requirements.

Add support for `make help` that works on Windows, and a `make
image` that builds the Docker image.

Unit testing and test coverage reporting via `make test` is
also desired.

## GitHub Action

A GitHub Action should run linting on all master commits. A new
tag should trigger linting, testing, and building the Docker image,
with that new image being uploaded to GHCR as `:<TAG>` and `:latest`
