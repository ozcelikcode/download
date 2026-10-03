# Active Context

## Current focus

Maintain isolated editor workspaces, shared protected categories, editorial approval, verified publishers, and private staff correspondence. Preserve existing site data during migrations.

Current increment adds a right-corner category-move dialog, opt-in trash retention, administrator-only client-key encrypted backups, and single/bulk publication hiding.

## Current decisions

- Manual recovery snapshots are consolidated by date under `Documents/Project Archives/download/migration-snapshots`, outside the repository. Seven snapshots were verified and relocated; eight unused sidecars with empty WALs were removed. The active site database and its sidecars were not touched. Future snapshots must use this single private archive rather than sibling/root files.

- Category moves use a compact source-folder → destination-folder dialog; the source category remains and all its content is moved, not copied.
- Publication controls are ordered Featured → Active → Hide. Hidden items remain editable but are unavailable through public listings, sitemap, version relationships, and direct routes.
- Trash retention defaults off. Administrators select 15/30/60/90/120/240/360 days; visible timers update automatically. Pending editorial deletion requests and their version families never expire automatically.
- Backup recovery keys are generated in the browser. The server stores only the public key; the password-encrypted recovery file is downloaded and must be stored offline. There is no server-side private-key recovery.
- Backups retain a protected latest archive plus up to seven historical archives, and prune only after successful creation. Optional automatic intervals are 1/3/5/7/14 days, with startup catch-up and manual creation.
- Import decrypts locally and uses a private, expiring review stage. Password plus exact current site name and explicit acknowledgment are required. A safety backup precedes transactional restore; media swaps have crash recovery. Current administrator credentials/public backup key survive; staff sessions are invalidated.

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
- Content and page editors share a rich-text policy: clipboard colors, backgrounds, font families, and sizes are discarded; semantic formatting is retained. Deliberate toolbar sizes survive editing. Server-side sanitization removes inline styles on save and render, including legacy records, so text follows the current theme without rewriting existing data.
- Editors can list, read, modify, and reference only their own downloads, categories, tags, and media. Ownership is tied to immutable user IDs, not usernames. Request-scoped ORM criteria cover relationships and bulk operations; aggregates and filesystem media routes have explicit scope checks. Personal dashboards exclude site health and global activity.
- Editor content removal hides the content and creates a pending deletion in personal and staff Trash. Editors can withdraw; administrators/managers can reject or approve permanent deletion. Review and withdrawal are serialized under a database write lock with session/role revalidation. This review workflow applies only to downloads, not taxonomy or media removal.
- Migration `s6d8f0b2c347` leaves legacy content/taxonomy owners unset rather than guessing authorship; these records remain staff-only. Media ownership is backfilled only for known uploader usernames. Different users can use the same category/tag names with distinct public slugs.
- The single required category is shared across workspaces and read-only for editors. Staff configure its name/description. Category moves transfer all records, including drafts and trash, without copying or deleting the source category; foreign content prevents editor moves.
- Unverified editor publishing and subsequent public content/version-history changes require administrator/manager review. Verification is password-confirmed; editor writes revalidate verification, credentials, and session generation under the database write lock. Reviews require the exact displayed revision. Verified editors publish directly; revocation does not unpublish existing records and verification does not automatically approve pending submissions.
- Publisher names use known owner usernames, with blue verified-editor, yellow administrator, and purple manager badges. Semantic badge colors do not inherit theme accent overrides. Legacy unattributed content displays the site name without an invented author badge.
- Private correspondence is readable only by the sending editor and administrators/managers, with staff replies, escaped plain text, CSRF, pagination, bounded bodies, and a five-message-per-hour quota. Message/reply bodies and review feedback are excluded from audit records. No end-to-end encryption is claimed.
- Migration `t7e9a1c3d458` preserves categories/content, canonicalizes the oldest required category, and demotes duplicate required flags without deleting records. It adds publisher verification, editorial review state, and correspondence storage.

## Recent verification

- The full suite passes 338 tests, including the optional shipped-browser Web Crypto harness, with warnings treated as errors. Maintenance coverage includes retention, public hiding, encrypted backup history, reviewed import, scheduler catch-up/manual operation, and restore rollback. Existing editorial/security coverage still passes. Browser-level visual verification remains pending because no compatible automation browser is installed.
- A requirements audit found no known dependency vulnerabilities. Live startup/shutdown and home/sign-in HTTP smoke checks passed with the shared logging configuration.
- Alembic revision `w0b2d4f6a781` is applied. Populated-copy upgrade, unchanged live content/taxonomy/media/user counts, SQLite integrity, foreign keys, schema checks, Tailwind build, and startup/home/sign-in smoke checks pass. Temporary migration copies were removed automatically; the pre-migration recovery backup remains outside the repository.

## Next step

Review remaining legacy Turkish comments and docstrings for the repository-wide English-language convention without changing user-facing behavior. Continue copy review for nuanced Spanish/French phrasing and browser-level layout verification.
