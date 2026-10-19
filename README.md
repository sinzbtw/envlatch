**[English](README.md)** | [Русский](README.ru.md)

# EnvLatch

**Catch missing environment variables before your application starts.**

[![Tests](https://github.com/sinzbtw/envlatch/actions/workflows/ci.yml/badge.svg)](https://github.com/sinzbtw/envlatch/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

EnvLatch is a small, dependency-free Python command-line tool that checks one or more local `.env` files against the keys in a committed `.env.example`. Use it after onboarding, before running a service, or in a deployment check to find configuration drift early.

## What it checks

- Every key in the template must exist in the effective environment configuration and have a nonblank value.
- Unexpected keys produce warnings; `--strict` makes them errors.
- Duplicate keys and malformed assignments produce errors with line numbers.
- Reports include variable names and locations, never their values or source lines.
- Results are deterministic and use exit codes suitable for scripts and CI.

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

The template path and at least one environment file path are required. Template values are illustrative and are **not** defaults: even a key with an empty template value requires a nonblank value in `.env`. A value such as `replace-me` passes the presence check; replace placeholders with usable configuration yourself.

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
| `2` | Invalid CLI usage, unreadable files, or non-UTF-8 input. |

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

JSON is deterministic and written to standard output for completed checks and file input errors. `status` is `pass`, `fail`, or `input_error`. Each issue contains `severity`, `code`, `path`, `message`, `line`, and `key`; `line` and `key` may be `null` when unavailable. Reports never contain environment values.

Exit codes remain `0`, `1`, and `2` as listed above. Invalid CLI arguments still produce human-readable usage errors on standard error, even when `--format json` is requested.

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

The same parser checks the template and every environment file. Use a dedicated dotenv template, not a shell script.

## Development

Install an editable checkout in your virtual environment:

~~~sh
python -m pip install -e .
python -m unittest discover -s tests -v
~~~

The package lives in `src/envlatch/`; tests live in `tests/`. The runtime uses only the Python standard library. GitHub Actions runs the test suite on Linux with Python 3.10 and 3.13, and on Windows with Python 3.13.

For a bug report, include your command, Python version, and a minimal example using invented values. Keep both README language versions in sync when changing behavior.

## License

[MIT](LICENSE) © 2026 EnvLatch contributors.
