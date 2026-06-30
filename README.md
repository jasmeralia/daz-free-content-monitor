# DAZ Free Content Monitor

A Dockerized Python service that periodically checks the DAZ 3D store for
free items, filters out products you already own, and sends Discord webhook
notifications with direct links to new free items.

## Features

- **Playwright scraping** — handles the JS-rendered DAZ store page
- **SQLite persistence** — deduplicates seen and owned items across restarts
- **Discord notifications** — one embed per item, batched, with rate-limit handling
- **Auto-claim** — optional: logs in and adds all new free items to cart, checks out once per cycle
- **Dry-run mode** — scrape without writing to the DB or sending notifications

## Quick Start

1. Create a `.env` file with at minimum your Discord webhook URL (see Configuration below).
2. Deploy:

```bash
docker compose up -d
```

## Configuration

All configuration lives in a `.env` file bind-mounted into the container at `/app/.env`.
The `docker-compose.yml` already includes the volume mount; create the file at
`/mnt/myzmirror/daz_data/.env` on the host.

| Variable | Default | Description |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | *(required)* | Discord webhook URL |
| `CHECK_INTERVAL_SECONDS` | `3600` | How often to check for new items |
| `DB_PATH` | `/app/data/daz_monitor.db` | SQLite database path |
| `LOG_FILE` | `/app/data/daz_monitor.log` | Log file path |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `DISPLAY_TIMEZONE` | `America/Los_Angeles` | IANA timezone for timestamps |
| `PAGE_DELAY_MIN` | `2.0` | Minimum seconds between page fetches |
| `PAGE_DELAY_MAX` | `5.0` | Maximum seconds between page fetches |
| `PAGE_TIMEOUT_MS` | `30000` | Playwright navigation timeout (ms) |
| `MAX_RETRIES` | `3` | Scrape retry attempts on failure |
| `DRY_RUN` | `0` | Set to `1` to scrape without DB writes or notifications |
| `RUN_ONCE` | `0` | Set to `1` to exit after one check cycle |
| `AUTO_CLAIM` | `0` | Set to `1` to automatically claim free items (requires credentials below) |
| `DAZ_EMAIL` | — | DAZ account email (required when `AUTO_CLAIM=1`) |
| `DAZ_PASSWORD` | — | DAZ account password (required when `AUTO_CLAIM=1`) |

## Auto-Claim

When `AUTO_CLAIM=1` is set, each cycle the monitor logs in to the DAZ store,
adds all newly-discovered free items to the cart, and completes a single $0
checkout at the end. Successfully claimed items are marked owned automatically
so they never trigger repeat notifications.

**Before enabling, validate the CSS selectors against the live site:**

```bash
docker compose run --rm daz-monitor python scripts/probe_claim.py \
  --email your@email.com --password yourpassword \
  --product https://www.daz3d.com/some-free-item
```

This saves screenshots to `data/probe_claim/` and reports which selectors in
`src/claimer.py` matched. Update any that show `NOT FOUND` before enabling
`AUTO_CLAIM`.

## Marking Items as Owned Manually

See [docs/mark_owned.md](docs/mark_owned.md) for instructions on permanently
suppressing notifications for items you already own.

```bash
docker compose run --rm daz-monitor python scripts/mark_owned.py \
  https://www.daz3d.com/genesis-9-starter-essentials
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
run `scripts/probe_selectors.py` to dump the rendered HTML and identify new
selectors.

The auto-claim selectors (login, add-to-cart, checkout) live at the top of
`src/claimer.py` and can be re-validated with `scripts/probe_claim.py`.

## License

MIT — see [LICENSE](LICENSE).
