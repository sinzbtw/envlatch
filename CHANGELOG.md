# Changelog

## 0.5.0 — 2026-10-29

- Add explicit `--config PATH` JSON settings for input paths, strict mode, optional keys, allowance patterns and output format.
- Resolve configured paths relative to the settings file, preserving working-directory-relative CLI overrides.
- Replace configured lists when their CLI flags are supplied; add `--no-strict` for explicit policy overrides.
- Reject unknown/duplicate fields, invalid types, non-standard JSON and malformed text without echoing file contents.
- Keep JSON report schema 1 and existing CLI commands compatible; add root and standalone example configurations.

## 0.4.0 — 2026-10-26

- Add repeatable `--allow-extra PATTERN` and Python API `allow_extra` for controlled extra-key allowances.
- Support case-sensitive `*` and `?` patterns and exact names consistently on Windows and Linux.
- Suppress only matching extra-key diagnostics; required, blank, syntax, duplicate and input checks remain active.
- Reject malformed allowance configuration with safe input errors; retain JSON schema 1 and source provenance.
- Add a runnable development example, cross-platform CI coverage and matching English/Russian instructions.

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
