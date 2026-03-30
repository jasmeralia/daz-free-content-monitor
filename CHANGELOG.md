# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.7] - 2026-03-29

### Fixed
- `scraper.py`: stop pagination immediately when a page's items are all
  already collected in the current run. The DAZ free catalog uses
  client-side-only pagination — `?page=N` returns the same 16 items on
  every URL — so the loop was previously running all 499 iterations to
  the hard cap before stopping.

## [0.1.6] - 2026-03-29

### Fixed
- `scraper.py`: corrected all four CSS selectors to match the actual rendered
  DAZ store DOM — `PRODUCT_CARD_SELECTOR` (`#slabs-container .item`),
  `PRODUCT_LINK_SELECTOR` (`a.slab-link`), `PRODUCT_TITLE_SELECTOR` (`h2`),
  and `PRODUCT_PRICE_SELECTOR` (`.prices-disp`). The previous selectors
  matched nothing, causing every scrape to return zero items.

## [0.1.5] - 2026-03-29

### Added
- `STARTUP_DELAY_SECONDS` env var (default `15`) — sleep before the first
  scrape cycle to allow the container network to stabilize, preventing
  `ERR_NETWORK_CHANGED` errors at boot

## [0.1.4] - 2026-03-29

### Added
- `src/config.py` — `get_display_tz()` helper; reads `DISPLAY_TIMEZONE` env var
  (IANA zone name, default `America/Los_Angeles`) and falls back to default on
  invalid input
- `DISPLAY_TIMEZONE` env var wired into `docker-compose.yml` (default
  `America/Los_Angeles`)
- `tzdata==2025.2` added to `requirements.txt` to ensure timezone data is
  available in all Docker base images

### Changed
- All timestamps (`free_items`, `owned_skus`, Discord embed footer) now use the
  configured display timezone instead of UTC
- Discord embed footer timezone abbreviation is now dynamic (`%Z`) rather than
  the hardcoded string `"UTC"`

## [0.1.3] - 2026-03-29

### Fixed
- `ImportError: cannot import name 'UTC' from 'datetime'` on Python 3.10 (Docker runtime);
  replaced `datetime.UTC` with `timezone.utc` in `src/db.py` and `src/notifier.py`

### Changed
- `pyproject.toml` ruff and mypy `target-version`/`python_version` corrected to `3.10`
  to match the Docker base image and prevent future 3.11+ syntax from being auto-suggested

## [0.1.2] - 2026-03-29

### Added
- `scripts/query_sku.py` — CLI to inspect DB state for a product by URL or SKU slug,
  showing all columns from `free_items` and `owned_skus` in a human-readable format

## [0.1.1] - 2026-03-29

### Added
- `scripts/mark_owned.py` — CLI to mark DAZ products as owned by URL or SKU slug,
  permanently suppressing future notifications for that item
- `docs/mark_owned.md` — usage guide for the new script
- Notification retry: failed Discord deliveries are retried every poll cycle
  until successful; failures are logged with SKU list for investigation

### Changed
- Notification tracking redesigned: `seen_items` replaced by `free_items` with
  `is_active` and `notified_at` columns
  - Items that disappear from the free list and later reappear now trigger a
    new notification (previously silenced forever after first notify)
  - `notified_at` is reset to `NULL` on reactivation so the item re-queues
- `Database.sync_free_items()` replaces `insert_seen_item` / `get_seen_skus`;
  performs the full upsert + deactivate in one atomic call
- `Database.get_pending_notifications()` and `Database.mark_notified()` added
  to manage per-item delivery state
- Automatic schema migration from v0.1.0 `seen_items` on first startup
  (existing seen items are imported as already-notified — no re-notification flood)

### Removed
- `scripts/import_orders.py` and `docs/export_orders.md` (DAZ does not offer
  a CSV order export)

## [0.1.0] - 2026-03-29

### Added
- Initial implementation of DAZ 3D free item monitor
- Playwright-based scraper for `https://www.daz3d.com/free-3d-models` with
  pagination, random delays, and retry logic
- SQLite persistence (`seen_items`, `owned_skus` tables) with WAL mode
- Discord webhook notifications (batched embeds, rate-limit handling)
- `scripts/import_orders.py` for seeding owned SKUs from DAZ order CSV export
- Makefile with `venv`, `venv-win`, `lint`, `test`, `image`, and `clean` targets
- GitHub Actions CI: lint on every `master` push; lint + test + Docker build/push on `v*` tags
- Docker image based on `mcr.microsoft.com/playwright/python:v1.44.0-jammy`

[Unreleased]: https://github.com/jasmeralia/daz-free-content-monitor/compare/v0.1.4...HEAD
[0.1.4]: https://github.com/jasmeralia/daz-free-content-monitor/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/jasmeralia/daz-free-content-monitor/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/jasmeralia/daz-free-content-monitor/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/jasmeralia/daz-free-content-monitor/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/jasmeralia/daz-free-content-monitor/releases/tag/v0.1.0
