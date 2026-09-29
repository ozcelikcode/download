# Secure operation

Passwords are stored as randomly salted scrypt hashes (N=131072, r=8, p=1). A legacy bcrypt hash is upgraded after a successful sign-in. Changing the password or username invalidates existing administrator sessions. Rotating `APP_SECRET_KEY` invalidates all sessions.

First-run setup requires a private `SETUP_TOKEN` to verify server ownership. The token is not written to URLs, cookies, or audit logs. Generate or rotate it with `make setup-key`, then restart the server. Public content, administration, and uploads stay closed until installation finishes. Migrations preserve the installed status of existing sites.

Maintenance actions require the current password, a session-bound confirmation valid for five minutes, and an exact match of the site name. Every scope invalidates old administrator sessions, including on public pages. SQLite-backed attempt limits protect setup, sign-in, password verification, and reset actions. Sensitive forms have a 16 KiB request-body limit, including streamed requests without a content-length header.

An operating-system lock enforces a single application process. A reset waits for active requests and background work. If cleanup is interrupted, a persistent maintenance marker keeps the site closed until cleanup resumes at startup. Deletion is limited to two validated data roots; broad, overlapping, code, database, or symlink roots are rejected. Targets outside those roots are not followed.

SQLite `secure_delete` is enabled, but SSD behavior, WAL files, operating-system snapshots, and external backups prevent a guarantee of forensic erasure. A full reset does not remove `.env` secrets, the hosting account, or external backups. Returning to setup does not remove the application code.

In production, set `APP_BASE_URL=https://your-domain` and terminate HTTPS at a trusted reverse proxy. This enables Secure cookies and HSTS. Trust forwarded headers only from the real proxy addresses; do not use an unrestricted `forwarded-allow-ips`.

Keep `.env` and the SQLite database outside the web root and accessible only to the service account. Never commit `.env`. Rotate previously disclosed keys; removing a key from Git history alone is insufficient.

The application does not encrypt its entire SQLite database. Use operating-system disk encryption and encrypted backups where needed. Password hashing and data encryption address different risks. Published downloads remain readable by visitors.

Sign-in logs include the trusted client IP, but not passwords. Failed sign-ins and rate-limit events are marked critical. Audit records are subject to the configured retention limit of 50, 100, 200, 500, or 800 records; they are not an immutable external security archive.

Stop the server with `Ctrl+C` in the terminal running `make dev`. Restart after changing `.env`.
