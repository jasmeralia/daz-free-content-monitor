# DAZ Free Content Monitor

A Dockerized Python service that periodically checks the DAZ 3D store for
free items, filters out products you already own, and sends Discord webhook
notifications with direct links to new free items.

## Features

- **Playwright scraping** — handles the JS-rendered DAZ store page
- **SQLite persistence** — deduplicates seen and owned items across restarts
- **Discord notifications** — one embed per item, batched, with rate-limit handling
- **Owned-items import** — seed your library from a DAZ order history CSV export
- **Dry-run mode** — scrape without writing to the DB or sending notifications

## Quick Start

1. Copy `docker-compose.yml` and fill in your `DISCORD_WEBHOOK_URL`.
2. Optionally import your existing library (see [docs/export_orders.md](docs/export_orders.md)).
3. Run:

```bash
docker compose up -d
```

## Configuration

All configuration is via environment variables set in `docker-compose.yml`:

| Variable | Default | Description |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | *(required)* | Discord webhook URL |
| `CHECK_INTERVAL_SECONDS` | `3600` | How often to check for new items |
| `DB_PATH` | `/app/data/daz_monitor.db` | SQLite database path |
| `LOG_FILE` | `/app/data/daz_monitor.log` | Log file path |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `PAGE_DELAY_MIN` | `2.0` | Minimum seconds between page fetches |
| `PAGE_DELAY_MAX` | `5.0` | Maximum seconds between page fetches |
| `PAGE_TIMEOUT_MS` | `30000` | Playwright navigation timeout (ms) |
| `MAX_RETRIES` | `3` | Scrape retry attempts on failure |
| `DRY_RUN` | `0` | Set to `1` to scrape without DB writes or notifications |
| `RUN_ONCE` | `0` | Set to `1` to exit after one check cycle |

## Importing Your Existing Library

See [docs/export_orders.md](docs/export_orders.md) for instructions on
exporting your DAZ order history and importing it:

```bash
docker compose run --rm daz-monitor python scripts/import_orders.py \
  --csv /app/data/daz_orders.csv
```

## Development

```bash
make venv                            # Create virtualenv and install deps
make lint PYTHON=.venv/bin/python    # Run ruff + pylint + mypy
make test PYTHON=.venv/bin/python    # Run tests with coverage
make image                           # Build Docker image locally
```

## Scraper Notes

CSS selectors for the DAZ product grid are defined as constants at the top of
`src/scraper.py`. If DAZ changes their page structure and scraping breaks,
update those constants first.

## License

MIT — see [LICENSE](LICENSE).
