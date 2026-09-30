# System Patterns

## Architecture

- FastAPI routes are split between public, administration, setup, and reports modules.
- Database models, Pydantic schemas, CRUD operations, Jinja2 templates, and static assets remain separate.
- SQLite access uses asynchronous SQLAlchemy sessions and Alembic migrations.
- Public pagination uses query parameters.

## Security and lifecycle

- Signed per-user sessions, server-side role checks, CSRF checks, throttling, request-size limits, sanitized rich text, and validated URLs protect application boundaries.
- The `users` table stores roles and password hashes. An active administrator must remain; manager requests to delete editors require administrator approval. Raw client IPs and user-agent strings are not persisted by application tables.
- Local downloads are stored outside the public static root and served only through controlled routes.
- Standalone pages use a dedicated `pages` table and `/page/{slug}` route. Private and draft pages return 404 to visitors, omit indexing and caching, and require the existing signed administrator session.
- Page HTML is sanitized on save and render. Audit records note content changes without recording the private body. Public menus and sitemap omit private, draft, and deleted pages.
- Remote link checks block private-network targets and pin resolved addresses.
- Setup requires a server-held owner key. Reset requires password verification, a short-lived challenge, and the exact site name.
- Full reset clears site data but not application code or server configuration. Uninstall returns to setup.

## UI and localization

- Jinja2 and Tailwind provide server-rendered pages; small JavaScript modules handle interactions such as menus, confirmations, toasts, and compact audit rows.
- `app/i18n.py` provides the shared interface/system-message catalog, with Spanish and French catalogs in `app/locales/`. Language is site-wide, not a visitor cookie preference.
- The default installation language is English. The protected category and hero defaults are created in the chosen language. `content_language` remains stable when `site_language` changes.
- Existing editorial records are not renamed when the administrator changes the interface language.
- SEO editing lives in Site Health; color theme and visual composition live in Appearance; log retention lives in Activity Log.
