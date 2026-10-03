# Progress

## Working capabilities

- Shared read-only default categories for editors; true category moves that preserve the empty source. Staff editorial approval with revision checks, password-confirmed verified editors, and public publisher names/role-colored badges. Private editor-to-staff correspondence with replies and per-account quotas. Published media and version-history changes cannot bypass editor review.

- Public download catalog, search and filters, content detail pages, related items, version history, and safe local/external download flow.
- Role-aware workflows for content, drafts, categories, tags, media, navigation, appearance, account settings, Site Health, link reports, and audit records; administrators manage staff accounts and approve manager deletion requests.
- Standalone public and administrator-only private pages with explicit publishing, sanitized rich text, menu integration, and page Trash.
- Owner-key-protected setup, three reset scopes, session invalidation, private download storage, and recovery after interrupted cleanup.
- CSRF, password hashing, login and download limits, upload/URL validation, audit logging, and custom error pages.
- Responsive interface, light/dark/system themes, accessibility behaviors, and consistent toast feedback.
- Shared admin headings and navigation, theme-consistent action buttons, safe DOM-based category/icon interactions, and English UTC console logs with exception-payload suppression.
- Personal editor dashboards and user-ID-based isolation for content, taxonomy, and media, including direct URLs, aggregates, references, upload progress, and bulk actions. Editor content deletion requires staff approval; withdrawal/rejection restores the content.
- Site-wide English/Spanish/French/Turkish interface setting; English is the default for a new installation. Setup and full reset create protected categories and hero content in the separately retained installation language.

## In progress

- Review nuanced Spanish/French phrasing beyond the verified complete catalog-key coverage.
- Remove remaining legacy Turkish code comments and docstrings without changing user-facing behavior.
- Keep all Markdown project documentation in English.

## Verification

The maintenance increment passes 338 tests with warnings treated as errors, including the shipped browser Web Crypto recovery/export/import protocol, authenticated encryption tampering rejection, latest-plus-seven-history retention, latest-backup protection, admin boundaries, all trash-retention options, pending-request family safety, public hiding, reviewed import, scheduler catch-up/manual operation, and database/media rollback after a failed restore. Live migration head is `w0b2d4f6a781`; populated-copy upgrade, SQLite integrity and foreign keys pass, and user/content/taxonomy/page/media row counts match the pre-migration recovery copy. Alembic detects no missing operations. New frontend JavaScript syntax checks and live lifespan/home/sign-in smoke checks pass. Actual browser visual review remains pending because a browser executable is unavailable in the local test runtime.

The previous editorial increment passed 313 tests, covering editor isolation, shared default categories, complete category moves, publication review and stale-revision checks, publisher verification, private correspondence, live media/version-history protections, validation recovery, reviewed deletion, and prior security workflows. Its populated-copy upgrade to `t7e9a1c3d458` preserved row counts and passed SQLite integrity/foreign-key checks. The temporary migration copy was removed and the recovery backup retained outside the repository. Existing administrator-authored content remains unchanged on interface-language changes.
