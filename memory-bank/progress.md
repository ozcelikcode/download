# Progress

## Working capabilities

- Administrator-only default/individual manager/editor media quotas, personal library usage, combined stored file/image accounting, alias deduplication, fresh authorization, and SQLite-serialized staged publication. Quota failure preserves replaced files; lowered quotas retain existing data. Direct/content/branding/remote/crop paths and known previous backup schemas are covered.

- Shared `/panel` routes, UTF-8/localized permission responses, and password-confirmed self-service account closure retaining all owned site data and immutable ownership anchors. Last-administrator protection and stale-session invalidation are covered by regression tests.

- Configurable IANA display zones in General Settings, with daylight saving support and unchanged UTC storage/logging. Audit, dashboard, requests, correspondence, reports, and shared date filters follow the selected zone. Time-zone settings and known previous backup schemas are covered by regression tests.

- Public sign-in navigation and registration applications, with direct authenticated administrator/manager approval or rejection, CSRF, and locked actor revalidation. Completed requests appear only in Activity Log. Pending applicants cannot sign in; approved accounts start as unverified editors. Password submissions use HTTPS; keyed quotas, queue limits, and four translations are covered.
- Organized Users tabs, grouped per-account actions, and quota cards; role-scoped navbar Messages and sidebar counters with 30-second polling and signed-session read markers. Local editable favicons support upload/SSRF-safe import, square PNG conversion, and cache invalidation without erasing old media.
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

- Latest request items 5–7 remain: editor category request workflow/permission changes, editor analytics, and staff statistics. Media quotas are implemented separately; analytics and category applications are not claimed complete.

- Review nuanced Spanish/French phrasing beyond the verified complete catalog-key coverage.
- Remove remaining legacy Turkish code comments and docstrings without changing user-facing behavior.
- Keep all Markdown project documentation in English.

## Verification

The Users/registration/notification/favicon increment passes 432 tests with warnings treated as errors and the optional Web Crypto harness enabled. Coverage includes passwordless staff-only registration decisions and audit retention, CSRF, editor-private publication/reply updates, pending-user counters, quota tabs, favicon upload/replacement/removal, pinned remote import, private-address rejection, square PNG processing, four languages, and strict old-archive adaptation. Tailwind and JavaScript syntax checks pass; Alembic detects no missing operations at `a4f6b8d0e125`. Existing records match the private 2026-10-05 pre-favicon recovery snapshot exactly, with valid SQLite integrity/foreign keys. Read-only real-database ASGI page checks return 200. Live visual inspection remains pending because the local HTTP server was stopped; no real application was reviewed during verification.

The media-quota increment passes all 418 tests with warnings treated as errors and the optional Web Crypto harness enabled. Administrator-only configuration, role defaults/overrides, all four quota-error translations, concurrent publication, replacement rollback, retained bytes after filesystem recovery failure, revoked actors, direct/content/branding/remote/crop paths, hidden staging access/listing, and known pre-quota/time-zone/registration backup compatibility pass. Migration head is `z3e5a7c9d014`; populated-copy and live integrity/foreign-key checks pass. Existing user/content/taxonomy/media/page/application fields match the private pre-migration snapshot exactly. Tailwind build, Alembic schema check, and read-only live home/sign-in/Users/Media HTTP checks pass. No real user account or personal quota was changed during verification.

The registration increment passes 396 tests with warnings treated as errors, including the optional Web Crypto harness. Global `/login`, old-bookmark redirection, native form submission through to both staff review lists, dashboard queue counts, receipt forgery prevention, approval boundaries, pending-access denial, duplicate/conflicting credentials, replay rejection, public CSRF, queue limits, remote HTTPS enforcement, all four languages, pagination, and prior backup-schema compatibility pass. Unavailable usernames produce explicit warnings; successful receipts are emitted only after a commit. A disposable live HTTP application was persisted, verified, and removed without creating an account. Live migration head is `y2d4f6a8b903`; populated-copy upgrade preserves existing row counts with valid integrity/foreign keys. The private recovery snapshot is retained under `Documents/Project Archives/download/migration-snapshots/2026-10-04/`; disposable migration copies are automatically removed.

The maintenance increment passes 338 tests with warnings treated as errors, including the shipped browser Web Crypto recovery/export/import protocol, authenticated encryption tampering rejection, latest-plus-seven-history retention, latest-backup protection, admin boundaries, all trash-retention options, pending-request family safety, public hiding, reviewed import, scheduler catch-up/manual operation, and database/media rollback after a failed restore. Live migration head is `w0b2d4f6a781`; populated-copy upgrade, SQLite integrity and foreign keys pass, and user/content/taxonomy/page/media row counts match the pre-migration recovery copy. Alembic detects no missing operations. New frontend JavaScript syntax checks and live lifespan/home/sign-in smoke checks pass. Actual browser visual review remains pending because a browser executable is unavailable in the local test runtime.

The previous editorial increment passed 313 tests, covering editor isolation, shared default categories, complete category moves, publication review and stale-revision checks, publisher verification, private correspondence, live media/version-history protections, validation recovery, reviewed deletion, and prior security workflows. Its populated-copy upgrade to `t7e9a1c3d458` preserved row counts and passed SQLite integrity/foreign-key checks. The temporary migration copy was removed and the recovery backup retained outside the repository. Existing administrator-authored content remains unchanged on interface-language changes.
