# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.13] - 2026-08-20

### Added
- Test coverage raised from 43% to 98%, with new pytest suites covering
  `src/claimer.py`, `src/scraper.py`, and `src/main.py` (Playwright browser
  interactions mocked via `AsyncMock`/`MagicMock` for deterministic,
  network-free CI runs).

### Changed
- `codecov.yml`: project and patch coverage status checks are no longer
  `informational` — both now gate at the existing 80% target.

## [0.1.12] - 2026-07-21

### Fixed
- `src/claimer.py`: `_login` waited for the login email field via
  `page.wait_for_selector()`, which resolves to the *first* DOM match — a
  hidden duplicate `login[username]` input in the page header that never
  becomes visible. This caused every auto-claim login attempt to time out
  once DAZ's login page started rendering that duplicate field, even though
  the subsequent `.fill()`/`.click()` calls already correctly used `.last` to
  target the visible form. The visibility wait now also uses
  `.last.wait_for(state="visible")` to match.

## [0.1.11] - 2026-07-06

### Changed
- `src/claimer.py`: use `domcontentloaded` instead of `networkidle` when
  loading product and checkout pages; some DAZ pages never fire `networkidle`
  due to background analytics, causing valid items to be marked as failed.
- `src/main.py`: when the auto-claimer detects that an item is already in the
  DAZ library (`result.skipped`), record it in `owned_skus` and mark it
  notified so no Discord embed is sent — no action needed from the user.
- `src/main.py`: after a successful claim run, suppress individual Discord
  embeds for items that were auto-claimed (covered by the `send_claim_result`
  summary) and for items already owned; only failed items receive individual
  notifications.

## [0.1.10] - 2026-07-02

### Changed
- `AGENTS.md`: added Deployment Access section with SSH coordinates (`ssh truenas`),
  container name, data volume path, DB query pattern, and OpenSearch log query examples.
- `AGENTS.md`: corrected Dockerfile base image to `v1.61.0-jammy` and removed stale
  note that TrueNAS doesn't support `.env` files.

## [0.1.9] - 2026-07-01

### Added
- `DiscordNotifier.send_claim_result()`: sends a Discord embed after each auto-claim
  run summarising what was claimed, what failed, and whether checkout succeeded.
  Green for full success, yellow for partial, red for checkout failure or all-failed.
- `tests/test_notifier.py`: seven new tests covering all claim-result notification paths.

## [0.1.8] - 2026-06-30

### Added
- `src/claimer.py`: `DazClaimer` class that logs in to the DAZ store, adds all
  new free items to the cart one by one, and completes a single $0 checkout at
  the end of each cycle. Controlled by `AUTO_CLAIM=1`, `DAZ_EMAIL`, and
  `DAZ_PASSWORD` env vars. Successfully claimed items are written to `owned_skus`
  automatically, suppressing future notifications.
- `scripts/probe_claim.py`: interactive probe that validates every CSS selector
  in `claimer.py` against the live DAZ store, saves screenshots to
  `data/probe_claim/`, and dumps button HTML to aid selector identification.
  Run this before enabling `AUTO_CLAIM`.
- `src/config.py`: added `daz_email`, `daz_password`, and `auto_claim` settings.

### Changed
- `docker-compose.yml`: switched to `.env` bind-mount pattern
  (`/mnt/myzmirror/daz_data/.env:/app/.env:ro`) with `environment: {}`;
  all configuration now lives in the host `.env` file rather than inline in the
  compose file.
- `pyproject.toml`: disabled `duplicate-code`, `too-many-locals` pylint rules
  which fire as false positives on the browser context manager pattern and
  complex orchestration functions.
- `README.md`, `AGENTS.md`: updated for auto-claim feature, `.env` deployment
  pattern, revised directory layout, main loop pseudocode, and risk table.
- `AGENTS.md`: added documentation update as a mandatory step in the change
  process.

### Fixed
- `scripts/query_sku.py`: removed spurious `f` prefix from two plain string
  literals (ruff F541).

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
