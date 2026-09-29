# Active Context

## Current focus

Maintain four complete interface catalogs, English-first setup, and immutable installation-language defaults. Preserve existing site data during migrations and subsequent interface-language changes.

## Current decisions

- Setup and Settings list languages in the order English, Spanish, French, Turkish. The first setup screen defaults to English.
- `site_language` controls the interface; `content_language` records the installation language. Later interface changes do not rename categories or rewrite hero/editorial content.
- Setup creates a protected category named `General`, `General`, `Général`, or `Genel` and matching default hero text. Full reset recreates both in `content_language`, including after interrupted cleanup. Uninstall returns to English-first setup.
- Existing installed sites inherit their current language as `content_language` through an Alembic migration; existing records are preserved.
- Spanish and French have full catalog-key coverage across public, admin, setup, and system messages. Report labels and locale metadata are localized separately.

## Recent verification

- The full suite passes 246 tests, including catalog/placeholder parity and ES/FR setup and page flows.
- Isolated Alembic upgrades verified both existing-site preservation and English defaults for an uninstalled database.

## Next step

Review remaining legacy Turkish comments, docstrings, and developer-only log strings for the repository-wide English-language convention without changing user-facing behavior. Continue copy review for nuanced Spanish/French phrasing.
