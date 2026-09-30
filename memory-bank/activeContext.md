# Active Context

## Current focus

Maintain role-based staff access and private pages alongside the four-language interface. Preserve existing site data during migrations.

## Current decisions

- Setup and Settings list languages in the order English, Spanish, French, Turkish. The first setup screen defaults to English.
- `site_language` controls the interface; `content_language` records the installation language. Later interface changes do not rename categories or rewrite hero/editorial content.
- Setup creates a protected category named `General`, `General`, `Général`, or `Genel` and matching default hero text. Full reset recreates both in `content_language`, including after interrupted cleanup. Uninstall returns to English-first setup.
- Existing installed sites inherit their current language as `content_language` through an Alembic migration; existing records are preserved.
- Spanish and French have full catalog-key coverage across public, admin, setup, and system messages. Report labels and locale metadata are localized separately.
- Public pages may be published and added to menus. Private pages are administrator-only; drafts and deleted pages are invisible to visitors. Deletion moves pages to a dedicated Trash, and restoration returns a draft.
- Staff accounts have administrator, manager, and editor roles. Administrators control critical account/reset actions; managers can request editor deletion pending administrator approval; editors can manage routine content, categories, tags, and media. The last active administrator cannot be removed or demoted.
- Raw client addresses and user-agent strings are not stored in the application database. Login/download quotas use keyed HMAC client identifiers. Visitor 404/500 events are logged anonymously without raw URLs.
- Admin pages share breadcrumbs and descriptive headings; account navigation, sidebar groups, and action buttons follow the existing theme.
- Console logs use English messages, UTC timestamps, and a shared plain-text format. Exception traces retain error types and code locations but omit exception values and source lines to avoid leaking submitted data.
- Category deletion and icon previews use DOM APIs instead of interpolating editable values into JavaScript or HTML. Account mutations revalidate the acting user's session and role under the database write lock.

## Recent verification

- The full suite passes 272 tests, including role boundaries, administrator continuity, concurrent actor demotion, page publication, private access, HTML sanitization, CSRF, page Trash, and safe console logging.
- A requirements audit found no known dependency vulnerabilities. Live startup/shutdown and home/sign-in HTTP smoke checks passed with the shared logging configuration.
- Alembic revision `r5c7e9a1b236` has been applied to the local database after backups and populated-copy migration tests; SQLite integrity, autogeneration, and HTTP smoke checks passed.

## Next step

Review remaining legacy Turkish comments and docstrings for the repository-wide English-language convention without changing user-facing behavior. Continue copy review for nuanced Spanish/French phrasing and browser-level layout verification.
