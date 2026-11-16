# Authorizing DAZ auto-claim

DAZ's client-side sign-in and Turnstile flow requires a human. The monitor does
not submit credentials or interact with the challenge. To authorize a session,
run this helper on a desktop with a graphical browser:

```bash
make venv
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/authorize_daz.py --output data/daz-auth.json
```

Sign in manually in the opened DAZ browser and complete any challenge there.
The helper waits for the account's logged-in marker, writes Playwright storage
state, and closes the browser. It does not add products to the cart or visit
checkout.

Copy `data/daz-auth.json` to the host path configured by `DAZ_STORAGE_STATE`.
The default container path is `/app/data/daz-auth.json`, under the mounted data
volume. The session file contains reusable authentication cookies: keep it
private, do not commit it, and restrict access to it. The helper writes it with
owner-only permissions (`0600`).

Set `AUTO_CLAIM=1` after the session file is installed. The monitor loads the
session and saves refreshed session state after each claim cycle. If DAZ expires
the session, the monitor reports the claims as failed and continues normal
scraping/notifications. Run the helper again to authorize a fresh session.

This procedure uses DAZ's sign-in page as intended. Do not attempt to automate
or bypass Turnstile.
