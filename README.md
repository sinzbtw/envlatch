**[English](README.md)** | [Русский](README.ru.md)

# EnvLatch

**Catch missing environment variables before your application starts.**

[![Tests](https://github.com/sinzbtw/envlatch/actions/workflows/ci.yml/badge.svg)](https://github.com/sinzbtw/envlatch/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

EnvLatch is a small, dependency-free Python command-line tool that checks one or more local `.env` files against the keys in a committed `.env.example`. Use it after onboarding, before running a service, or in a deployment check to find configuration drift early.

## What it checks

- Every template key is required and nonblank by default; `--optional KEY` allows selected keys to be missing or blank.
- Unexpected keys produce warnings; `--strict` makes them errors. Use `--allow-extra PATTERN` for explicit exceptions.
- Duplicate keys and malformed assignments produce errors with line numbers.
- Reports include variable names and locations, never their values or source lines.
- Save paths and validation policy in an explicit JSON project config, with CLI overrides.
- Deterministic text, JSON, and GitHub Actions reports use exit codes suitable for scripts and CI.

EnvLatch reads files only. It does not load variables into your process, evaluate shell commands, expand references, or read values from the current process environment. It validates presence and nonblank values; it does not validate credentials, URL formats, or application-specific types.

## Requirements

- Python **3.10 or newer**.
- Windows, Linux, or macOS.
- UTF-8 input files; a UTF-8 BOM and CRLF line endings are supported.

There are no runtime dependencies. Installation uses pip and setuptools as build tooling.

## Install from source

~~~sh
git clone https://github.com/sinzbtw/envlatch.git
cd envlatch
python -m venv .venv
~~~

Activate the virtual environment:

~~~powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
~~~

~~~sh
# Linux / macOS
source .venv/bin/activate
~~~

Then install the checked-out project:

~~~sh
python -m pip install .
envlatch --version
~~~

If your system uses `python3` instead of `python`, substitute it when creating the virtual environment. EnvLatch is installed from this repository; these instructions do not require a PyPI release.

## Quick start

The repository includes this `.env.example`:

~~~dotenv
DATABASE_URL=postgresql://localhost/app
API_TOKEN=replace-me
PORT=8000
~~~

Create your local configuration and replace the example values as needed:

~~~powershell
# Windows PowerShell
Copy-Item .env.example .env
~~~

~~~sh
# Linux / macOS
cp .env.example .env
~~~

Validate it:

~~~sh
envlatch --template .env.example --env .env
~~~

The module entry point works too:

~~~sh
python -m envlatch --template .env.example --env .env
~~~

A template path and at least one environment file path are required, supplied directly or through `--config`. Template values are illustrative and are **not** defaults: even a key with an empty template value requires a nonblank value in `.env`, unless it is explicitly marked optional. A value such as `replace-me` passes the presence check; replace placeholders with usable configuration yourself.

Commit `.env.example`, but keep real environment files local. The included `.gitignore` excludes `.env` and local environment variants.

## Examples

Require an exact set of keys, useful in automated checks:

~~~sh
envlatch --template .env.example --env .env --strict
~~~

Check files outside the current directory:

~~~sh
envlatch --template config/service.env.example --env config/service.env
~~~

If `.env` omits `API_TOKEN`, leaves `DATABASE_URL` blank, and adds `DEBUG`, EnvLatch reports two errors and one warning. The exit code is `1`. With `--strict`, the unexpected `DEBUG` key becomes a third error. Reports identify the keys without displaying their values.

See all CLI options:

~~~sh
envlatch --help
~~~

| Exit code | Meaning |
| --- | --- |
| `0` | No errors; warnings may be present. |
| `1` | Validation errors or invalid dotenv syntax. |
| `2` | Invalid CLI usage or check settings; unreadable files, invalid JSON config, or non-UTF-8 input. |

## Project configuration

Store paths and validation policy once, then run:

~~~sh
envlatch --config envlatch.json
~~~

The committed [envlatch.json](envlatch.json) checks your local `.env` against `.env.example` in strict mode. Create your local `.env` as described in Quick start. A configuration can use these fields:

~~~json
{
  "template": ".env.example",
  "env": [".env", ".env.local"],
  "strict": true,
  "optional": ["PORT"],
  "allow_extra": ["CI_*"],
  "format": "text"
}
~~~

The second environment file in this example must exist; omit it if you do not use an overlay. Configuration stores paths, key names and patterns, not dotenv values. Keep real secrets in local environment files.

| Field | Type | Default |
| --- | --- | --- |
| `template` | Nonempty path string | Required through config or CLI |
| `env` | Nonempty array of path strings, in overlay order | Required through config or CLI |
| `strict` | Boolean | `false` |
| `optional` | Array of key names | `[]` |
| `allow_extra` | Array of allowance patterns | `[]` |
| `format` | `text`, `json`, or `github` | `text` |

Settings are loaded only when `--config` is supplied. UTF-8, BOM and CRLF are supported; use standard JSON without comments. Unknown fields, duplicate fields, invalid types, blank entries and invalid Unicode are rejected. Paths and strings are literal: shell commands, home shortcuts and environment references are not expanded or executed.

### Paths and overrides

- Paths inside JSON are resolved relative to the configuration file's directory, so the same configuration works from another working directory. These resolved paths appear as absolute paths in reports.
- Explicit CLI options override the corresponding configuration setting. CLI `--template` and `--env` paths stay relative to the current working directory.
- Supplying `--env` replaces the entire configured `env` array. Repeated CLI entries form the new overlay list in their given order.
- Supplying `--optional` or `--allow-extra` replaces that configured list; repeated flags form the replacement list. An empty array in JSON clears that setting.
- `--strict` enables strict mode; `--no-strict` disables it even if JSON enables it. These flags are mutually exclusive.
- `--format` overrides the configured output format. Existing commands without a config continue to work.

~~~sh
envlatch --config envlatch.json --env .env.production --format json
envlatch --config envlatch.json --no-strict
~~~

For a self-contained example using committed, invented environment values:

~~~sh
envlatch --config examples/config/envlatch.json --format json
~~~

An unreadable or invalid configuration produces exit code `2` without echoing its contents. If the configuration cannot be loaded, output defaults to a text error on standard error; pass `--format json` or `--format github` explicitly to choose structured errors before loading. Missing required paths and invalid CLI arguments remain normal usage errors. JSON structure and types are checked even for fields overridden by CLI. The report's JSON schema remains version `1`.

## Optional keys

Some settings enable integrations that are deliberately absent in local development. Repeat `--optional KEY` to allow a declared template key to be missing or blank while keeping other keys required:

~~~sh
envlatch --template examples/optional/.env.example --env .env --optional SENTRY_DSN --optional LOG_LEVEL --strict
~~~

The committed [optional-key example](examples/optional/.env.example) declares the usual `DATABASE_URL`, `API_TOKEN`, and `PORT`, plus `SENTRY_DSN` and `LOG_LEVEL`. This self-contained command checks the example without creating local configuration:

~~~sh
envlatch --template examples/optional/.env.example --env .env.example --optional SENTRY_DSN --optional LOG_LEVEL --strict --format json
~~~

- Optional names must exist in the template, with matching case. A typo produces `unknown_optional_key` and exit code `1`, even if that key exists in the environment file.
- Invalid optional names produce exit code `2`; names use the same ASCII grammar as dotenv keys.
- Optional keys may be absent, blank, or nonblank. Syntax and duplicate-key checks still apply.
- `--strict` rejects keys outside the template unless explicitly permitted by `--allow-extra`. Optional keys remain declared settings and do not automatically allow unrelated extra keys.
- The policy applies to the final merged configuration, so a blank overlay is allowed for an optional key.
- `checked_keys` in JSON and the text summary count required keys only. JSON schema version remains `1`.

Without `--optional`, every template key remains required. Python callers can pass `optional_keys=["SENTRY_DSN", "LOG_LEVEL"]` to `check()`.

## Allowed extra keys

Shared environment files sometimes contain tool settings that are intentionally outside an application's contract. Repeat `--allow-extra PATTERN` to allow exact names or simple wildcard patterns without weakening other checks:

~~~sh
envlatch --template .env.example --env .env --strict --allow-extra DEBUG --allow-extra 'CI_*'
~~~

The committed [development environment example](examples/allow-extra/development.env) contains the three usual application keys plus `DEBUG` and `TOOL_CACHE_DIR`. Try it directly:

~~~sh
envlatch --template .env.example --env examples/allow-extra/development.env --strict --allow-extra DEBUG --allow-extra 'TOOL_*' --format json
~~~

- Patterns are case-sensitive on every OS. `*` matches zero or more characters; `?` matches one character. Quote wildcard patterns so your shell passes them unchanged.
- Patterns accept ASCII letters, digits, underscores, `*`, and `?` only. Empty patterns and unsupported syntax such as character classes produce an input error (exit code `2`).
- Matching extra keys produce neither warnings nor errors, with or without `--strict`. Unmatched extra keys keep their normal warning/error behavior. An unused pattern is allowed.
- An allowance applies only to keys absent from the template. It never makes a required key optional or permits its value to be blank. Even `--allow-extra '*'` preserves required-key checks.
- Syntax, duplicate-key, file-reading, and optional-key configuration errors remain errors. Overlay order and source locations are preserved.
- The option works with text, JSON, and GitHub Actions output. JSON schema version `1` and `checked_keys` remain unchanged.

Python callers can use `check(template, environment, strict=True, allow_extra=["DEBUG", "CI_*"])`. To make a declared key optional instead, use `--optional KEY`.

## Layered environment files

Repeat `--env` to validate a shared base configuration with local or deployment overrides:

~~~sh
envlatch --template .env.example --env .env --env .env.local --strict
~~~

Files are applied in command-line order: a later file overrides the same key from an earlier file. Required keys may be spread across files; EnvLatch checks the combined effective configuration. A blank value in a later file overrides an earlier nonblank value and fails validation when the key is required.

For example, if `.env` defines `DATABASE_URL` and `API_TOKEN`, and `.env.local` defines `PORT`, the combined configuration satisfies the three-key template. If `.env.local` also contains `API_TOKEN=`, the required token is reported as blank.

Duplicate keys within a single file and syntax errors in any input file remain errors, even when a later file overrides the affected key. Diagnostics for effective keys point to the winning definition; missing-key diagnostics refer to the last environment file. JSON reports list `environments` in the exact input order, including on file input errors.

The single-file commands above continue to work. These layers are used only for validation; EnvLatch does not modify your process environment.

## JSON reports

Request a machine-readable report for scripts or CI:

~~~sh
envlatch --template .env.example --env .env --format json
~~~

A successful check of the three-key example produces this JSON structure:

~~~json
{
  "schema_version": 1,
  "status": "pass",
  "template": ".env.example",
  "environments": [".env"],
  "checked_keys": 3,
  "errors": 0,
  "warnings": 0,
  "issues": []
}
~~~

JSON is deterministic and written to standard output for completed checks and file or configuration input errors. `status` is `pass`, `fail`, or `input_error`. Each issue contains `severity`, `code`, `path`, `message`, `line`, and `key`; `line` and `key` may be `null` when unavailable. Reports never contain environment values.

Exit codes remain `0`, `1`, and `2` as listed above. Invalid CLI arguments still produce human-readable usage errors on standard error, even when `--format json` is requested.

## GitHub Actions annotations

Use `--format github` to turn errors and warnings into native [GitHub Actions annotations](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#setting-an-error-message). After installing EnvLatch and preparing the environment file, add a workflow step:

~~~yaml
- name: Validate environment configuration
  run: envlatch --template .env.example --env .env --strict --format github
~~~

An empty required value produces a workflow command such as:

~~~text
::error title=EnvLatch%3A empty_value,file=.env,line=2::Required key 'TOKEN' is blank.
~~~

- Each diagnostic becomes an `error` or `warning` annotation, with its code in the title and its file/line when available. Missing-key diagnostics have no known line; input errors become general error annotations.
- A normal PASS/FAIL summary follows the annotations. Successful checks without diagnostics print only that summary.
- Exit codes stay `0` for success or warnings, `1` for validation errors, and `2` for input/configuration errors. Invalid CLI usage still prints a normal message to standard error.
- Values and raw dotenv lines remain absent. Command delimiters and line breaks in filenames/messages are escaped so a diagnostic cannot inject another workflow command.
- Use repository-relative paths for source navigation. GitHub can link to a file present in the repository; local or generated `.env` files still get annotations but may have no source link. Keep real secrets out of Git.
- The format works with `--optional`, `--allow-extra`, repeated `--env`, and `--strict`. Outside Actions, the workflow commands appear as ordinary text. The default text and JSON formats are unchanged.

## Supported dotenv syntax

EnvLatch deliberately supports a constrained, single-line dotenv format:

~~~dotenv
# A comment
APP_NAME = envlatch
export PORT=8000
EMPTY=
MESSAGE="A value containing # a hash"
LABEL='A literal value'
HOST=localhost # An inline comment
FRAGMENT=https://example.invalid/#section
REFERENCE=$OTHER_VARIABLE
~~~

- Keys match `[A-Za-z_][A-Za-z0-9_]*`; matching is case-sensitive.
- Spaces around a key, `=`, and an unquoted value are allowed.
- Blank lines, comments, and the optional `export` prefix are accepted.
- In unquoted values, `#` starts a comment at the beginning of the value or after whitespace. Otherwise it is part of the value.
- Single- and double-quoted values can contain `#`. Double-quoted values support escaped double quotes.
- After a closing quote, only whitespace and a comment are allowed.
- Dollar references are literal text, with no expansion or shell execution.
- Quoted multiline values, NUL characters, invalid keys, missing `=`, and duplicate keys are rejected.
- Required keys with empty or whitespace-only environment values fail the nonblank check.

Parsing stops at the first malformed statement in each file, so rejected multiline content cannot become a reported key. Duplicate assignments are reported separately, and later files are still checked.

The same parser checks the template and every environment file. Use a dedicated dotenv template, not a shell script.

## Development

Install an editable checkout in your virtual environment:

~~~sh
python -m pip install -e .
python -m unittest discover -s tests -v
~~~

The package lives in `src/envlatch/`; tests live in `tests/`. The runtime uses only the Python standard library. GitHub Actions runs the test suite on Linux with Python 3.10 and 3.13, and on Windows with Python 3.13.

For a bug report, include your command, Python version, and a minimal example using invented values. Keep both README language versions in sync when changing behavior.

GitHub Releases distribute tagged source archives only. Wheel builds are used for local installation checks and are not uploaded as release assets.

## Community

Contributions in English or Russian are welcome. See [Contributing](CONTRIBUTING.md), the [Code of Conduct](CODE_OF_CONDUCT.md), and the [Security Policy](SECURITY.md). Use the [issue forms](https://github.com/sinzbtw/envlatch/issues/new/choose) for ordinary bugs and feature requests; report suspected vulnerabilities privately through the security policy.

## License

[MIT](LICENSE) © 2026 EnvLatch contributors.
