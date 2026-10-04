# Downloader

Downloader is a self-hosted download catalog built with FastAPI, Jinja2, SQLite, and Tailwind CSS. It provides a public site and an administration panel for managing applications, files, categories, tags, media, navigation, themes, language, and audit records.

## Features

- Local file uploads and external download sources
- Version history, latest-version links, SHA-256 checksums, and operating-system metadata
- Search, category and tag filtering, featured items, and query-string pagination
- One administrator-controlled interface language (English, Spanish, French, or Turkish), shared by the public site and admin panel; English is the new-installation default and existing content remains unchanged when the interface language changes
- Configurable branding, color themes, light and dark modes, navigation, and hero layout
- Bulk content operations and safe category deletion with content transfer
- Automatic application drafts with live save status and manual finalization
- Media archive, link health reports, and paginated audit logs
- Administrator-only default and individual storage quotas for managers/editors, with combined file/image usage and safe in-place replacement
- Administrator-only encrypted backups with browser-held recovery keys, manual export/import, optional 1/3/5/7/14-day schedules, and a protected latest backup plus seven historical archives
- Opt-in trash expiry (15/30/60/90/120/240/360 days), protected editorial deletion requests, and single/bulk publication hiding
- Administrator, manager, and editor accounts with server-side permissions, reviewed editor-deletion requests, and a last-administrator safeguard
- Public sign-in and registration applications; administrator/manager approval creates an unverified editor account, with no access while approval is pending
- Scrypt password hashing, signed sessions, CSRF protection, login throttling, and anonymous visitor-error logs
- Owner-key protected first-run setup, deployment checks, and two-step maintenance/reset controls
- SSRF protection for outbound URL checks and remote icon imports
- Locally served Lucide, Quill, and Cropper.js assets

Sign in at `/login` and apply at `/register`. The staff dashboard links to pending applications at `/panel/registrations`; only administrators/managers can review them. Existing usernames do not create another account or application. Unavailable usernames show a conflict warning without distinguishing an account from a pending request. A success receipt appears only after a new request is committed. `/panel/login` is only a redirect for old bookmarks.

Choose the display time zone in **Settings → General**, after the language options. IANA zones support daylight saving automatically. Stored timestamps and console logs remain UTC; changing the display zone does not rewrite historical records. The initial display zone is UTC.

All staff roles use `/panel`; changing this address is not a substitute for authorization. Old `/admin` GET bookmarks redirect to the new routes, where the same permissions are enforced. Existing private media URLs and metadata remain compatible. Permission-denied browser pages are localized HTML; API errors explicitly declare UTF-8.

**Settings → Account → Delete my account** requires the current password, the exact current username, and explicit acknowledgment. Closure invalidates sign-in credentials and sessions, but preserves content, taxonomy, media, and correspondence. A non-login identity tombstone anchors existing ownership; the last active administrator cannot close their account.

**Users → Default storage quotas** configures editor and manager defaults separately. Each active manager/editor has a personal override under **Media storage quota**; clearing it follows the role default. Only an administrator can change these settings, with password confirmation and HTTPS (loopback development is exempt). Choices are 64/128/256/512/1024/2048/4096/8192/16384/32768 MB, where MB means 1024² bytes. Initial defaults are 256 MB for editors and 1024 MB for managers; administrators are unlimited. Role changes clear the personal override.

Images and files share the owner's quota, including unused media and media belonging to trashed content. Stored image size is counted after processing; legacy media URL aliases count once. Unowned legacy site assets remain site assets rather than being assigned to an arbitrary user. Lowering a limit never removes existing files. At or above the limit, replacement may keep or reduce the stored size, but cannot add storage. Direct uploads, content-form uploads, branding images, remote icons, and crop copies use the same SQLite-serialized quota/publication check. In-place replacement is charged to the existing owner, not the acting staff member. The independent per-upload size limit still applies.

## Requirements

- Python 3.12 or later
- Linux or macOS (a single application process owns the SQLite database)
- SQLite 3
- GNU Make
- `curl` for downloading the standalone Tailwind CSS compiler during setup
- Node.js is optional for the browser Web Crypto compatibility regression test; `BACKUP_TEST_NODE` may point to a non-PATH executable. The application itself does not require Node.js.

## Quick start

```bash
make install
make setup
make dev
```

`make setup` creates a private `.env` file with random session and setup keys, then applies migrations. It refuses to overwrite an existing `.env`. Save the printed setup key privately. Open `http://127.0.0.1:8000`: the installation screen appears until you enter that key, create an administrator account, and confirm the site settings. No public content or uploads are served before installation.

The first installation screen opens in English. Choose English, Spanish, French, or Turkish there before submitting the form, in that order. Setup creates the protected default category (`General`, `General`, `Général`, or `Genel`) and default hero content in the selected language. The installation content language is stored separately from the interface language. Changing the interface language later does not rewrite existing content; a full reset recreates defaults in the original installation language. Returning to setup restores English as the initial choice.

For a new production installation, choose the final domain when preparing the configuration:

```bash
make setup SITE_URL=https://downloads.example.com
```

Complete the deployment steps below before opening production setup. The browser cannot purchase hosting, configure DNS, or provision TLS; it verifies the application configuration and asks you to confirm the infrastructure checks. `APP_BASE_URL` remains the source of truth for the public URL and secure cookies.

For an **existing installation**, use `.venv/bin/pip install -r requirements.txt` and `make migrate`, then restart the server. Existing accounts and content are preserved. The new migration records the existing site language as its initial content language. Do not run `make setup` over your existing configuration. To enable returning to setup, run `make setup-key`, save the printed key, and restart the server.

Stop the development server with `Ctrl+C` in the terminal that runs `make dev`. Wait for the shell prompt to return before starting it again.

## Configuration

Settings are loaded from `.env` through `pydantic-settings`.

| Variable | Purpose | Default |
|---|---|---|
| `APP_SECRET_KEY` | Signs sessions and security tokens. Use a long random value. | Development placeholder |
| `APP_BASE_URL` | Canonical public URL. An HTTPS value enables secure cookies and HSTS. | `http://localhost:8000` |
| `ADMIN_USERNAME` | Legacy account fallback used only when migrating an older installed database. | `admin` |
| `ADMIN_PASSWORD_HASH` | Legacy password-hash fallback used only during migration. New accounts live in SQLite. | Empty |
| `SETUP_TOKEN` | Private setup/reinstallation key generated by `make setup` or rotated by `make setup-key`. At least 32 characters. | Empty (setup disabled) |
| `DATABASE_URL` | SQLAlchemy database connection string. | `sqlite+aiosqlite:///./download.db` |
| `UPLOAD_DIR` | Storage directory for uploaded files and images. | `app/static/uploads` |
| `DOWNLOAD_DIR` | Private storage for downloadable files; keep outside the static directory. | `storage/downloads` |
| `MAX_UPLOAD_SIZE_MB` | Maximum upload size in megabytes. | `500` |
| `RATE_LIMIT_DOWNLOADS_PER_HOUR` | Download allowance per anonymous client key and hour. | `10` |
| `DEBUG` | Enables development error details. Keep disabled in production. | `false` |

Generate a suitable application secret with:

```bash
openssl rand -hex 32
```

## Development

Install the development dependencies and run the test suite with:

```bash
make install-dev
make test
```

Tailwind CSS is compiled into `app/static/css/tailwind.css`. Rebuild it after adding or changing utility classes in templates:

```bash
make css
```

During frontend work, the watcher can rebuild CSS as templates change:

```bash
make css-watch
```

Create and apply database migrations with:

```bash
make migration msg="describe the schema change"
make migrate
```

## Database and uploads

The default database is `download.db`. The database, `app/static/uploads`, and `storage/downloads` are runtime data and are intentionally excluded from Git. Downloadable files are kept outside the public static tree and are served only through `/dl/{slug}`. Files named `download.db-wal` and `download.db-shm` are SQLite working files, not backup copies. Do not delete them while the application is running.

For a consistent manual backup, stop the application and copy `download.db`, `app/static/uploads`, and `storage/downloads`. Store `.env` separately as a secret. Keep backups outside both data directories. You can checkpoint the WAL after all application processes have stopped:

```bash
.venv/bin/python -c 'import sqlite3; connection = sqlite3.connect("download.db"); print(connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()); connection.close()'
```

Alembic migrations preserve existing content and should be applied before every deployment that changes the schema.

## Local frontend dependencies

Runtime JavaScript and stylesheet dependencies are stored in the repository and served from `/static/vendor`; the application does not require a CDN in the browser.

| Package | Version | Location |
|---|---:|---|
| Lucide | 1.24.0 | `app/static/vendor/lucide/1.24.0` |
| Quill | 2.0.3 | `app/static/vendor/quill/2.0.3` |
| Cropper.js | 1.6.2 | `app/static/vendor/cropperjs/1.6.2` |

Each package directory includes its upstream license. When updating a package, replace its distributable files and license together, use a versioned directory, and update the corresponding template paths.

## Production

Apply migrations and run the production target:

```bash
make migrate
make prod
```

`make prod` binds to `0.0.0.0:8000` with one worker. Use a firewall to expose only your reverse proxy, not port 8000. The application takes an operating-system lock beside the database; a second application process using the same database refuses to start. Keep SQLite on a local persistent disk, not a shared/network filesystem.

Before completing production setup:

1. Provision a Linux server/container with Python 3.12+, persistent storage and a dedicated unprivileged service account. Ephemeral/serverless storage is unsuitable for this SQLite deployment.
2. Point the domain's DNS A/AAAA records at the server. Configure a TLS certificate and redirect HTTP to HTTPS at the reverse proxy.
3. Set `APP_BASE_URL=https://your-domain`, `DEBUG=false`, and `FORWARDED_ALLOW_IPS` to the actual proxy address in the service environment. Ensure Uvicorn receives the original HTTPS scheme. The browser setup blocks production HTTP and debug mode.
4. Forward requests through the application, including uploaded images. Do not expose the project directory, database, `.env`, private downloads, or uploads through a separate static web-server alias: doing so bypasses setup/maintenance access controls.
5. Restrict public Host headers to your configured domain at the proxy. Forward `Host`, `X-Forwarded-Proto` and a sanitized client IP. Configure request-size/time limits; the application also limits unauthenticated forms to 16 KiB and authenticated upload requests to `MAX_UPLOAD_SIZE_MB` plus 1 MiB of form overhead.
6. Make the database directory and dedicated upload/download directories writable only by the service account. Keep `.env` mode 0600. Run the process under a service manager with restart-on-failure, then complete `/setup` over HTTPS.
7. Arrange off-server backups and test restoring the database, both data directories, and secret configuration together.

Only trust forwarded headers from known proxy addresses; never use `FORWARDED_ALLOW_IPS=*`. Moving to multiple application workers requires redesigning the database, request coordination and progress state; it is not supported by this deployment.

## Standalone pages

Use **Content → Pages** to create an editorial page at `/page/{slug}`. Save a draft first or publish explicitly. Public pages can be added to the header or footer from **Settings → Menus**; only published public pages appear in the page picker or sitemap.

Private pages require a valid administrator session. Visitors receive a generic 404, including for drafts and deleted pages. Private responses disable caching and indexing, suppress referrers, and block third-party images. Private pages are not visitor password links and cannot be shared with non-administrators. Changing a public page to private or a draft disables matching menu entries.

Deleting a page moves it to **Pages → Trash**. Restore brings it back as a draft; permanent deletion is available from the page trash. A full-site reset removes pages, while a settings-only reset retains them.

## Reset and removal

Use **Settings → Maintenance and Reset**. First select a scope and verify the current administrator password. Then, within five minutes, type the exact displayed site name and acknowledge permanent deletion. Confirmation is tied to the authenticated session, account and selected action. CSRF checks and password-attempt limits apply. Every successful reset invalidates all existing administrator sessions.

| Action | Removed | Preserved |
|---|---|---|
| Settings only | Branding, appearance, SEO, navigation and other site preferences | Content, files, logs, administrator account, language, server configuration |
| Entire site | All content, categories, tags, uploaded/downloadable files, navigation, activity/download/link records; settings restored | Administrator account, language, server configuration |
| Delete and return to setup | Entire-site data plus administrator account | Application code and server configuration; site remains closed until setup succeeds |

Returning to setup is disabled unless `SETUP_TOKEN` is configured. Anyone revisiting the site still needs the server's private key to reinstall. Environment variables and infrastructure are deliberately not deleted; unregister domains or cancel hosting directly with their providers if desired.

Reset waits for in-flight requests and background downloads. The database records pending file cleanup before files are deleted. If cleanup fails or the process stops, the site remains unavailable; fix directory permissions and restart to resume cleanup. The stored data-directory paths must still match configuration. Do not remove `site_lifecycle` records or change data directories to bypass this check.

Inside the checkout, only the standard `app/static/uploads` and `storage/downloads` data roots can be used. For custom storage, use dedicated physical directories outside the checkout; do not use symlink roots or broad shared folders.

Settings-only reset retains media even if it was previously used by a logo or hero. Full reset includes unlinked files in both dedicated storage directories, but never follows symlinks to outside files. `.gitkeep` placeholders remain. External backups and operating-system logs are outside these operations. This is application-data deletion, not a forensic disk wipe.

See [SECURITY.md](SECURITY.md) for deployment and data-protection guidance.

## Project structure

```text
app/
├── main.py              FastAPI application and middleware
├── config.py            Environment-based settings
├── crud.py              Asynchronous database operations
├── dependencies.py      Authentication and shared dependencies
├── models.py            SQLAlchemy models
├── routers/             Public and administration routes
├── schemas.py           Pydantic schemas
├── static/              Compiled CSS, uploads, and vendor assets
├── templates/           Public and administration Jinja templates
└── templating.py        Jinja environment and helpers
alembic/                 Database migration environment and revisions
tests/                   Integration and security tests
Makefile                 Development and production commands
requirements.txt         Runtime Python dependencies
requirements-dev.txt     Test dependencies
```

## Common commands

| Command | Description |
|---|---|
| `make dev` | Run the local server with automatic reload. |
| `make setup` | Generate a new private configuration and migrate a fresh installation. Never overwrites `.env`. |
| `make setup-key` | Rotate the server-only setup/reinstallation key; restart afterward. |
| `make prod` | Run the production server with one worker. |
| `make migrate` | Apply all pending Alembic migrations. |
| `make migration msg="..."` | Generate a migration from model changes. |
| `make hash` | Prompt for an admin password and print its scrypt hash. |
| `make test` | Run the test suite against isolated temporary databases. |
| `make css` | Compile and minify Tailwind CSS. |
| `make css-watch` | Recompile Tailwind CSS while templates change. |
