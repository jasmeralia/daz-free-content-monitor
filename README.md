# DAZ Free Content Monitor

A Dockerized Python service that periodically checks the DAZ 3D store for
free items, filters out products you already own, and sends Discord webhook
notifications with direct links to new free items.

## Features

- **Playwright scraping** — handles the JS-rendered DAZ store page
- **SQLite persistence** — deduplicates seen and owned items across restarts
- **Discord notifications** — one embed per item, batched, with rate-limit handling
- **Auto-claim** — optional: uses a saved DAZ session that was authorized by a human, then adds new free items to cart and checks out once per cycle
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
| `AUTO_CLAIM` | `0` | Set to `1` to automatically claim free items using a saved sign-in session |
| `DAZ_STORAGE_STATE` | `/app/data/daz-auth.json` | Playwright session file created through the visible human sign-in flow |

## Auto-Claim

DAZ now requires a client-side Turnstile/authentication flow that does not
complete in the monitor's headless browser. Sign in manually through DAZ's
visible browser flow, including any challenge, and save the resulting session:

```bash
make venv
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/authorize_daz.py --output data/daz-auth.json
```

See [docs/authorize_daz.md](docs/authorize_daz.md) for session-file handling
and recovery details.

Copy the generated session file to the configured `DAZ_STORAGE_STATE` path on
the host and keep it private: it contains reusable login cookies. The helper
only opens the DAZ login page and waits for the logged-in marker; it does not
fill credentials or click sign-in. The monitor loads that session and reports
claims as failed if DAZ expires it. Re-run the visible authorization helper
when that happens. Do not automate or bypass DAZ's challenge.

After the session file is in place, set `AUTO_CLAIM=1`. The monitor saves any
updated browser session back to the same file at the end of a cycle.

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
make test PYTHON=.venv/bin/python    # Run tests and write coverage.xml for Codecov
make image                           # Build Docker image locally
```

The container uses the official Playwright Python Noble image and Python 3.12.
Keep the base image's Python version compatible with the minimum Python version
required by packages in `requirements.txt`. It runs as UID/GID 1000 to access
the TrueNAS data directory and mode-600 `.env` bind mount.

## Scraper Notes

CSS selectors for the DAZ product grid are defined as constants at the top of
`src/scraper.py`. If DAZ changes their page structure and scraping breaks,
run `scripts/probe_selectors.py` to dump the rendered HTML and identify new
selectors.

The auto-claim selectors (add-to-cart, checkout, authenticated marker) live at
the top of `src/claimer.py`. Sign-in itself is completed by a human using
`scripts/authorize_daz.py`; the service never submits credentials or attempts
to handle Turnstile. An expired session reports failed claims and keeps the
monitor cycle alive.

## License

MIT — see [LICENSE](LICENSE).
