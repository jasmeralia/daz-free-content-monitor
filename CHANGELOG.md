# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/jasmeralia/daz-free-content-monitor/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jasmeralia/daz-free-content-monitor/releases/tag/v0.1.0
