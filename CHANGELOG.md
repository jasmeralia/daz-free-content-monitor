# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/jasmeralia/daz-free-content-monitor/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/jasmeralia/daz-free-content-monitor/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/jasmeralia/daz-free-content-monitor/releases/tag/v0.1.0
