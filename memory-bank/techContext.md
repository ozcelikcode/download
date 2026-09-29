# Technical Context

## Stack

- Python 3.12+, FastAPI, Pydantic v2
- Async SQLAlchemy, aiosqlite, SQLite, Alembic
- Jinja2, Tailwind CSS, locally served Lucide icons
- Small vanilla JavaScript modules and pytest/pytest-asyncio tests

## Main paths

- `app/routers/`: public, admin, setup, and report routes
- `app/models.py`, `app/crud.py`, `app/schemas.py`: persistence and validation
- `app/i18n.py`: interface and system-message localization
- `app/health.py`, `app/seo.py`: site-health and public URL checks
- `app/templates/`, `app/static/`: Jinja pages and browser assets
- `storage/downloads/`: private local downloads
- `tests/`: isolated SQLite and upload-directory fixtures

## Development

```bash
make install
make migrate
make dev
.venv/bin/pytest -q
```

Use Alembic for schema changes. Before delivery, run the relevant and full test suites, `git diff --check`, and dependency or syntax checks when appropriate. Tests use temporary storage and never modify the working site's database.

The Python 3.12 virtual environment is local and ignored by Git. The development reload watcher is limited to `app/`.
