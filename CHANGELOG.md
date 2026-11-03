# Changelog

## 0.7.0 — 2026-11-03

Compare configuration across dev, staging and production without displaying variable values.

- Add `envlatch compare` and the Python `compare()` API for independent named environments.
- Find missing or blank variables, type differences and changes to explicitly selected settings.
- Support separate file overlays for each environment and shared validation rules in JSON configuration.
- Provide text, JSON and GitHub Actions reports, with file locations and environment names.
- Keep previous commands and configuration files compatible; add complete examples and English/Russian documentation.

## 0.6.1 — 2026-11-03

Install EnvLatch directly from PyPI.

- Add PyPI installation and upgrade instructions.
- Include documentation and runnable examples in source distributions.
- Fix documentation links on the PyPI project page.

## 0.6.0 — 2026-11-02

Optionally validate environment variable types.

- Add `types` rules for string, integer, boolean, URL and port values in JSON configuration and the Python API.
- Report invalid types with variable names and source locations, keeping values hidden.
- Preserve existing behavior when type rules are omitted.

## 0.5.0 — 2026-10-29

Save project settings instead of repeating command-line options.

- Add `--config PATH` for JSON settings, including files, validation rules and output format.
- Resolve configured paths relative to the configuration file; allow explicit CLI overrides.
- Add `--no-strict` to override strict mode from the configuration.

## 0.4.0 — 2026-10-26

Allow selected variables outside the template.

- Add `--allow-extra PATTERN` and the Python API `allow_extra` option.
- Support exact names and case-sensitive `*` and `?` patterns.

## 0.3.0 — 2026-10-24

Show validation errors directly in GitHub Actions.

- Add `--format github` for error and warning annotations with source locations.
- Keep variable values out of annotations and preserve existing text/JSON output.

## 0.2.0 — 2026-10-22

Make selected template variables optional.

- Add `--optional KEY` and the Python API `optional_keys` option.
- Allow optional variables to be absent or blank while preserving other validation rules.

## 0.1.0 — 2026-10-19

Initial release.

- Check dotenv files against a template for missing, blank, duplicate and malformed variables.
- Support ordered file overlays and strict checking of extra variables.
- Provide text/JSON reports and script-friendly exit codes without displaying values.
