# Changelog

## 0.2.0 — 2026-10-22

- Add repeatable `--optional KEY` and Python API `optional_keys` for template keys allowed to be missing or blank.
- Detect unknown optional names as configuration errors instead of silently accepting typos.
- Preserve strict extra-key, syntax, duplicate, overlay and secret-safe reporting behavior.
- Keep JSON schema version 1; `checked_keys` counts required keys only.
- Add a runnable optional-key example and full English/Russian instructions.

## 0.1.0 — 2026-10-19

Initial release with dotenv contract validation, ordered overlays, text/JSON reports, and CI on Linux and Windows.
