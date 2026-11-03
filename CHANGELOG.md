# Changelog

## 0.7.0 — 2026-11-03

- Add `envlatch compare` and the Python `compare()` API for independent named environments such as dev, staging and production, with ordered overlays inside each environment.
- Reuse existing contract validation and type rules; report missing/blank variables, inferred type drift and explicitly selected setting differences with safe source locations.
- Compare selected settings using fresh, per-call keyed fingerprints; retain no values or fingerprints in reports. Values are never printed, and unselected secrets are not compared for equality.
- Add explicit comparison JSON configuration with named file arrays, shared validation policy and `compare_values`; preserve legacy CLI/config behavior and the existing validation JSON schema.
- Provide text, comparison-specific JSON and escaped GitHub Actions output, matching English/Russian documentation, runnable examples and regression coverage.

## 0.6.1 — 2026-11-03

- Prepare PyPI metadata with an SPDX MIT license, explicit Markdown description, project links and Python classifiers; retain zero runtime dependencies.
- Include public examples, bilingual documentation, configuration, tests and release tooling in the sdist, while restricting wheel contents to package code and metadata.
- Build a wheel from the sdist, reject unexpected/stale artifacts and unsafe archive paths, check metadata with Twine, and test both installed distributions outside the checkout on Linux/Windows.
- Add release-triggered GitHub Actions Trusted Publishing with a tag-restricted `pypi` environment, isolated OIDC upload permissions, pinned Actions and provenance attestations; require matching versions and successful package checks before upload.
- Keep uploads disabled until the one-time PyPI publisher setup is complete, verify installation from PyPI after publication, and document setup/recovery in English and Russian.
- Preserve source-only GitHub Release assets and all v0.6.0 validation behavior.

## 0.6.0 — 2026-11-02

- Add opt-in `types` rules in JSON configuration and the Python `check(..., types=...)` API: string, integer, boolean, URL (`url`) and port.
- Check only effective, nonblank values after overlays; optional missing/blank keys keep their existing behavior, and template values remain illustrative.
- Report `invalid_type` with the expected type and winning file/line, never dotenv values or raw validation exceptions; retain only key metadata and failed-key names after parsing.
- Reject malformed rules as safe input errors (exit 2) and unknown template keys as `unknown_type_key` validation errors (exit 1).
- Preserve v0.5.0 configurations, CLI behavior, parser metadata, exit codes and JSON report schema 1 when no types are configured; add no runtime dependencies.
- Document exact type rules in English/Russian and add a runnable example, regression tests and a CI smoke check.

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
