# DAZ Free Item Monitor — Project Context

## Goal

A Dockerized Python service that periodically checks the DAZ 3D store for
free items, filters out already-owned products, and sends Discord webhook
notifications with direct links to new free items.

# MANDATORY CHANGE PROCESS

1. After any change in the repository, run `make lint` and `make test`.
2. Any errors or warnings must be resolved before proceeding.
3. Update the version (patch/Z only — see Versioning Rules) and run `make lint` again.
4. Add a new entry in CHANGELOG.md, and commit and push to both the
   master branch and a new tag specific to that version.

## Versioning Rules

- Version format is `X.Y.Z` (semver). Only the patch number (Z) may be bumped
  without explicit human approval. Bumping X (major) or Y (minor) requires the
  user to approve first — ask if you believe a bump is warranted.
- **Never modify or move a tag after it has been created.** Tags are immutable.
  If a release needs a fix, create a new version and a new tag.

## Timezone Behavior

- All timestamps (DB storage, Discord notifications, log output) use the
  timezone configured via the `DISPLAY_TIMEZONE` environment variable.
- Default: `America/Los_Angeles`. Valid values are IANA timezone names
  (e.g. `America/New_York`, `Europe/London`, `UTC`).
- The helper `src/config.py:get_display_tz()` reads this env var and falls
  back to the default for missing or invalid values.
- Do **not** hardcode `timezone.utc` or `datetime.UTC` anywhere; always call
  `get_display_tz()`. The only exception is if UTC is explicitly required for
  interoperability with an external system (document the reason in a comment).

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
│   └── mark_owned.md     # guide on marking items as owned
├── LICENSE               # MIT License
├── Makefile
├── README.md
├── requirements.txt      # modules actually required to run the app
├── requirements-dev.txt  # dev tools: ruff, mypy, pylint, includes requirements.txt
├── scripts/
│   ├── mark_owned.py     # mark items as owned by URL or SKU slug
│   └── query_sku.py      # inspect DB state for a product by URL or SKU slug
└── src/
    ├── main.py           # entrypoint, scheduler loop
    ├── config.py         # env-var config helpers (timezone, etc.)
    ├── scraper.py        # Playwright-based DAZ store scraper
    ├── db.py             # SQLite schema and queries
    └── notifier.py       # Discord webhook sender
```

## SQLite Schema

```sql
-- Active/inactive free listing tracker (replaces simple seen_items)
-- notified_at NULL = pending delivery; timestamp = successfully delivered
CREATE TABLE IF NOT EXISTS free_items (
    sku         TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    first_seen  TEXT NOT NULL,      -- ISO8601, when first seen as free
    last_seen   TEXT NOT NULL,      -- ISO8601, last time seen on free list
    is_active   INTEGER NOT NULL DEFAULT 1,  -- 1 = currently on free list
    notified_at TEXT                -- NULL until Discord delivery succeeds
);

-- Items you already own — permanently suppress all notifications
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
- Stop paginating when a page returns no products or a page is entirely
  composed of owned SKUs (early-exit optimization)

### Owned Items

- No CSV export exists on DAZ's site
- Use `scripts/mark_owned.py` to manually mark items as owned by URL or SKU
- Items in `owned_skus` are permanently suppressed — never notified about them

## Main Loop (src/main.py)

```
on startup:
  init db (runs schema migration from v0.1.0 if needed)

every CHECK_INTERVAL_SECONDS:
  owned_skus = db.get_owned_skus()
  result = scraper.scrape_with_retry(owned_skus)   # paginate free listings

  db.sync_free_items(result.items)
    → upsert all current items as is_active=1
    → reset notified_at=NULL for items that were inactive (reactivated)
    → set is_active=0 for items no longer on the free list

  pending = db.get_pending_notifications(owned_skus)
    → active items with notified_at IS NULL, excluding owned_skus

  for each batch of ≤10 pending items:
    ok = notifier.send(batch)
    if ok:
      db.mark_notified(sku) for each item in batch
    else:
      log error with SKU list — retry next cycle
```

**Notification guarantees:**
- Item appears → notified ✓
- Item stays on list next cycle → no duplicate ✓
- Item removed → marked inactive ✓
- Item reappears later → notified again ✓ (reset on reactivation)
- Discord delivery failure → retried every cycle until success ✓
- Item in owned_skus → never notified ✓

## Discord Notification Format

Each new free item gets an embed:

```
🆓 New Free DAZ Item

**[Product Title]**
https://www.daz3d.com/...
```

Up to 10 embeds are batched per webhook call. Rate-limit (429) responses are
retried with the `retry_after` delay. Failed batches are retried each poll cycle.

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
      - DISPLAY_TIMEZONE=America/Los_Angeles
```

## scripts/mark_owned.py

Marks one or more DAZ products as owned, permanently suppressing notifications.
Accepts DAZ product URLs or SKU slugs as positional arguments.

Usage:
```
docker compose run --rm daz-monitor python scripts/mark_owned.py \
  https://www.daz3d.com/genesis-9-starter-essentials

docker compose run --rm daz-monitor python scripts/mark_owned.py \
  some-product-slug another-product-slug
```

See `docs/mark_owned.md` for full details.

## Known Risks / Mitigations

| Risk | Mitigation |
|---|---|
| DAZ changes page structure | Playwright selectors in one file (`scraper.py`) — easy to update |
| Bot detection on listings page | Add random delays (2–5s) between page fetches; use real Chromium UA |
| Free item disappears before you claim it | Re-notification when item reappears on free list; owned_skus suppresses permanently |
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
