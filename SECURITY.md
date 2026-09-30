# Secure operation

Passwords are stored as randomly salted scrypt hashes (N=131072, r=8, p=1). A legacy bcrypt hash is upgraded after a successful sign-in. Changing a password or username invalidates that user's existing sessions. Rotating `APP_SECRET_KEY` invalidates all sessions.

Staff accounts have administrator, manager, or editor roles. Authorization is enforced server-side on every protected route, not by hidden navigation alone. Administrators manage critical settings and accounts; managers can request an editor's deletion, which remains pending until an administrator approves it. Account removal and demotion cannot leave the site without an active administrator. Sensitive account changes require current-password verification.

First-run setup requires a private `SETUP_TOKEN` to verify server ownership. The token is not written to URLs, cookies, or audit logs. Generate or rotate it with `make setup-key`, then restart the server. Public content, administration, and uploads stay closed until installation finishes. Migrations preserve the installed status of existing sites.

Maintenance actions require the current password, a session-bound confirmation valid for five minutes, and an exact match of the site name. Every scope invalidates old administrator sessions, including on public pages. SQLite-backed attempt limits protect setup, sign-in, password verification, and reset actions. Sensitive forms have a 16 KiB request-body limit, including streamed requests without a content-length header.

An operating-system lock enforces a single application process. A reset waits for active requests and background work. If cleanup is interrupted, a persistent maintenance marker keeps the site closed until cleanup resumes at startup. Deletion is limited to two validated data roots; broad, overlapping, code, database, or symlink roots are rejected. Targets outside those roots are not followed.

SQLite `secure_delete` is enabled, but SSD behavior, WAL files, operating-system snapshots, and external backups prevent a guarantee of forensic erasure. A full reset does not remove `.env` secrets, the hosting account, or external backups. Returning to setup does not remove the application code.

In production, set `APP_BASE_URL=https://your-domain` and terminate HTTPS at a trusted reverse proxy. This enables Secure cookies and HSTS. Trust forwarded headers only from the real proxy addresses; do not use an unrestricted `forwarded-allow-ips`.

Keep `.env` and the SQLite database outside the web root and accessible only to the service account. Never commit `.env`. Rotate previously disclosed keys; removing a key from Git history alone is insufficient.

The application does not encrypt its entire SQLite database. Use operating-system disk encryption and encrypted backups where needed. Password hashing and data encryption address different risks. Published downloads remain readable by visitors.

The database does not store raw client IP addresses or browser user-agent strings. Quotas use keyed HMAC client identifiers; rotating `APP_SECRET_KEY` also resets their continuity. Existing stored addresses are anonymized by the user-account migration, historical audit entries containing addresses are redacted, and the legacy administrator credential copy is removed after transfer to the users table. Default Uvicorn access logging is disabled in the supplied Makefile. Check reverse-proxy, hosting, backup, and operating-system logs separately; the application cannot control those external records. Public HTTP errors are recorded as `anonymous` with route patterns rather than full URLs or request bodies. Failed sign-ins and rate-limit events are marked critical. Audit records are subject to the configured retention limit of 50, 100, 200, 500, or 800 records; they are not an immutable external security archive.

Passwords are not end-to-end encrypted: this server must verify them. They are protected in transit by HTTPS and stored as one-way salted hashes. Published site content and server-managed private pages are likewise not end-to-end encrypted. Use encrypted backups and disk encryption when protecting data at rest.

The supplied server commands use `app/logging.json` for English, plain-text UTC console logs. Terminal controls are escaped. Exception traces include error types and code locations, but omit exception values and source lines because those may contain submitted secrets or SQL parameters. Account mutations revalidate the acting session and role after acquiring the database write lock.

Stop the server with `Ctrl+C` in the terminal running `make dev`. Restart after changing `.env`.
