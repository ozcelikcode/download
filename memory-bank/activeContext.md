# Active Context

## Current focus

Maintain secure standalone pages alongside the four-language interface and installation-language defaults. Preserve existing site data during migrations.

## Current decisions

- Setup and Settings list languages in the order English, Spanish, French, Turkish. The first setup screen defaults to English.
- `site_language` controls the interface; `content_language` records the installation language. Later interface changes do not rename categories or rewrite hero/editorial content.
- Setup creates a protected category named `General`, `General`, `Général`, or `Genel` and matching default hero text. Full reset recreates both in `content_language`, including after interrupted cleanup. Uninstall returns to English-first setup.
- Existing installed sites inherit their current language as `content_language` through an Alembic migration; existing records are preserved.
- Spanish and French have full catalog-key coverage across public, admin, setup, and system messages. Report labels and locale metadata are localized separately.
- Public pages may be published and added to menus. Private pages are administrator-only; drafts and deleted pages are invisible to visitors. Deletion moves pages to a dedicated Trash, and restoration returns a draft.

## Recent verification

- The full suite passes 249 tests, including page publication, private access, HTML sanitization, CSRF, and page Trash.
- Alembic revision `p3a5c7e9f014` has been applied to the local database; SQLite integrity check and anonymous HTTP smoke checks passed.

## Next step

Review remaining legacy Turkish comments, docstrings, and developer-only log strings for the repository-wide English-language convention without changing user-facing behavior. Continue copy review for nuanced Spanish/French phrasing.
