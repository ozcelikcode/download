# Agent Rules

This project is a minimal download site built with FastAPI and Tailwind CSS. Follow these rules when changing it.

## Coding standards

- Use Python 3.12+, type hints, and Pydantic v2 for backend code.
- Keep FastAPI routes and SQLAlchemy database work asynchronous.
- Preserve the separation between routers, models, schemas, and templates; do not concentrate features in `main.py`.
- Use only `rounded-sm` for Tailwind corner-radius classes. Avoid exaggerated shadows and keep the interface minimal.
- Write code identifiers, comments, docstrings, and project documentation in English. User-facing translations are maintained separately.

## Pace and safety

- Work in medium-sized, independently working increments.
- Inspect the current implementation before editing, verify each increment, and preserve existing user data and unrelated changes.
- Do not move to another feature while the current increment is broken.

## Architecture

- Use SQLite and Alembic migrations for schema changes.
- Use Jinja2 for frontend templates. Add JavaScript only when interaction requires it.
- Use Lucide icons.
- Paginate dynamic content with `?page=x`, never a `/page/2` path.

## Errors and logging

- Render custom Jinja2 pages for user-facing 404 and 500 errors.
- Log backend failures clearly with Python's `logging` module without exposing secrets.

## Communication

- Be direct. Explain the technical change and the next step without unnecessary ceremony.
