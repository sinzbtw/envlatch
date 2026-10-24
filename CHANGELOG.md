# Changelog

## 0.3.0 — 2026-10-24

- Add `--format github` for native GitHub Actions error and warning annotations with source locations.
- Escape workflow-command properties and messages, preserving value-free diagnostics and existing exit codes.
- Render input/configuration errors as general error annotations; invalid CLI usage stays on standard error.
- Keep text output, JSON schema version 1, optional keys, strict checks and overlays compatible.
- Add English/Russian workflow examples and document source-only GitHub releases.

## 0.2.0 — 2026-10-22

- Add repeatable `--optional KEY` and Python API `optional_keys` for template keys allowed to be missing or blank.
- Detect unknown optional names as configuration errors instead of silently accepting typos.
- Preserve strict extra-key, syntax, duplicate, overlay and secret-safe reporting behavior.
- Keep JSON schema version 1; `checked_keys` counts required keys only.
- Add a runnable optional-key example and full English/Russian instructions.

## 0.1.0 — 2026-10-19

Initial release with dotenv contract validation, ordered overlays, text/JSON reports, and CI on Linux and Windows.
