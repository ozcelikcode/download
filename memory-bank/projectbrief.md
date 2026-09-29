# Project Brief

Downloader is a minimal, self-hosted FastAPI download catalog. Visitors should find an application or file and reach its verified download destination without advertising detours or unnecessary steps.

## Core requirements

- Serve private local files or redirect to validated external HTTP(S) sources.
- Organize content by categories, tags, versions, and searchable metadata.
- Provide an administrator-only interface for content, media, navigation, appearance, site health, and audit records.
- Keep draft publication explicit and destructive operations confirmable and recoverable where possible.
- Offer light, dark, and system themes with a restrained, configurable accent color.
- Use an owner-key-protected first-run setup. The first screen and default installation language are English; the installed site uses one administrator-selected language.
- Keep system-provided default content aligned with the selected installation language. Preserve editorial content unless an administrator changes it.

## Constraints

- Use asynchronous FastAPI and SQLAlchemy, SQLite, Alembic, Pydantic v2, Jinja2, and Tailwind CSS.
- Paginate with `?page=x`. Use only `rounded-sm` Tailwind radius classes and avoid excessive visual effects.
- Do not provide visitor accounts or registration.

The original project brief is in `prompt.txt`; the working repository rules are in `agents.md`.
