# Progress

## Working capabilities

- Shared `/panel` routes, UTF-8/localized permission responses, and password-confirmed self-service account closure retaining all owned site data and immutable ownership anchors. Last-administrator protection and stale-session invalidation are covered by regression tests.

- Configurable IANA display zones in General Settings, with daylight saving support and unchanged UTC storage/logging. Audit, dashboard, requests, correspondence, reports, and shared date filters follow the selected zone. Time-zone settings and known previous backup schemas are covered by regression tests.

- Public sign-in navigation and registration applications, with password-confirmed administrator/manager approval or rejection. Pending applicants cannot sign in; approved accounts start as unverified editors. HTTPS, CSRF, keyed quotas, queue limits, and four translations are covered.
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

- Latest request items 4–7: personal/default manager/editor media quotas, editor category request workflow/permission changes, editor analytics and staff statistics. None is claimed complete by the panel/account increment.

- Review nuanced Spanish/French phrasing beyond the verified complete catalog-key coverage.
- Remove remaining legacy Turkish code comments and docstrings without changing user-facing behavior.
- Keep all Markdown project documentation in English.

## Verification

The registration increment passes 396 tests with warnings treated as errors, including the optional Web Crypto harness. Global `/login`, old-bookmark redirection, native form submission through to both staff review lists, dashboard queue counts, receipt forgery prevention, approval boundaries, pending-access denial, duplicate/conflicting credentials, replay rejection, public CSRF, queue limits, remote HTTPS enforcement, all four languages, pagination, and prior backup-schema compatibility pass. Unavailable usernames produce explicit warnings; successful receipts are emitted only after a commit. A disposable live HTTP application was persisted, verified, and removed without creating an account. Live migration head is `y2d4f6a8b903`; populated-copy upgrade preserves existing row counts with valid integrity/foreign keys. The private recovery snapshot is retained under `Documents/Project Archives/download/migration-snapshots/2026-10-04/`; disposable migration copies are automatically removed.

The maintenance increment passes 338 tests with warnings treated as errors, including the shipped browser Web Crypto recovery/export/import protocol, authenticated encryption tampering rejection, latest-plus-seven-history retention, latest-backup protection, admin boundaries, all trash-retention options, pending-request family safety, public hiding, reviewed import, scheduler catch-up/manual operation, and database/media rollback after a failed restore. Live migration head is `w0b2d4f6a781`; populated-copy upgrade, SQLite integrity and foreign keys pass, and user/content/taxonomy/page/media row counts match the pre-migration recovery copy. Alembic detects no missing operations. New frontend JavaScript syntax checks and live lifespan/home/sign-in smoke checks pass. Actual browser visual review remains pending because a browser executable is unavailable in the local test runtime.

The previous editorial increment passed 313 tests, covering editor isolation, shared default categories, complete category moves, publication review and stale-revision checks, publisher verification, private correspondence, live media/version-history protections, validation recovery, reviewed deletion, and prior security workflows. Its populated-copy upgrade to `t7e9a1c3d458` preserved row counts and passed SQLite integrity/foreign-key checks. The temporary migration copy was removed and the recovery backup retained outside the repository. Existing administrator-authored content remains unchanged on interface-language changes.
