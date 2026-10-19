"""The parser keeps only names, line numbers and whether a value is blank."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_EXPORT = re.compile(r"export[ \t]+")


@dataclass(frozen=True)
class Issue:
    """A safe diagnostic: no raw source lines or environment values."""

    severity: str
    code: str
    path: str | None
    message: str
    line: int | None = None
    key: str | None = None


@dataclass(frozen=True)
class Entry:
    key: str
    line: int
    empty: bool


@dataclass(frozen=True)
class Report:
    template: str
    environment: str
    checked_keys: int
    issues: tuple[Issue, ...]

    @property
    def errors(self) -> int:
        return sum(issue.severity == "error" for issue in self.issues)

    @property
    def warnings(self) -> int:
        return sum(issue.severity == "warning" for issue in self.issues)

    @property
    def valid(self) -> bool:
        return self.errors == 0


class InputError(Exception):
    """A file could not be read as UTF-8; messages never contain its contents."""


def _closing_quote(value: str) -> int | None:
    quote = value[0]
    escaped = False
    for index in range(1, len(value)):
        character = value[index]
        if quote == '"' and escaped:
            escaped = False
            continue
        if quote == '"' and character == "\\":
            escaped = True
            continue
        if character == quote:
            return index
    return None


def _value_is_empty(value: str) -> bool | None:
    """Return blankness, or None for invalid or multiline quoted values."""
    value = value.strip()
    if not value or value.startswith("#"):
        return True
    if value[0] not in ("'", '"'):
        for index, character in enumerate(value):
            if character == "#" and index and value[index - 1].isspace():
                value = value[:index]
                break
        return not value.strip()

    end = _closing_quote(value)
    if end is None:
        return None
    tail = value[end + 1 :].strip()
    if tail and not tail.startswith("#"):
        return None
    return not value[1:end].strip()


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeError:
        raise InputError(f"Cannot read UTF-8 input: {path}") from None
    except OSError:
        raise InputError(f"Cannot read input file: {path}") from None


def parse(text: str, path: str) -> tuple[dict[str, Entry], list[Issue]]:
    """Parse a single-line dotenv dialect and discard all actual values."""
    entries: dict[str, Entry] = {}
    issues: list[Issue] = []
    # Only LF/CRLF are physical line boundaries; Unicode in values stays literal.
    for line_number, raw in enumerate(text.removeprefix("\ufeff").split("\n"), 1):
        line = raw.rstrip("\r").strip()
        if not line or line.startswith("#"):
            continue
        if "\x00" in line:
            issues.append(Issue("error", "invalid_syntax", path,
                                "NUL characters are not supported.", line_number))
            continue
        line = _EXPORT.sub("", line, count=1)
        if "=" not in line:
            issues.append(Issue("error", "invalid_syntax", path,
                                "Expected KEY=VALUE.", line_number))
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not _KEY.fullmatch(key):
            issues.append(Issue("error", "invalid_key", path,
                                "Expected an ASCII environment variable name.", line_number))
            continue
        empty = _value_is_empty(value)
        if empty is None:
            issues.append(Issue("error", "invalid_value", path,
                                "Expected a single-line value with balanced quotes and no trailing text.",
                                line_number, key))
            stripped_value = value.strip()
            if stripped_value and stripped_value[0] in ("'", '"') and _closing_quote(stripped_value) is None:
                # Stop instead of mistaking later multiline secret fragments for keys.
                break
            continue
        if key in entries:
            issues.append(Issue("error", "duplicate_key", path,
                                f"Duplicate key '{key}'; first defined on line {entries[key].line}.",
                                line_number, key))
            continue
        entries[key] = Entry(key, line_number, empty)
    return entries, issues


def check(template: str | Path, environment: str | Path, *, strict: bool = False) -> Report:
    """Check required nonblank keys; extra keys warn unless strict is enabled."""
    template_path = Path(template)
    environment_path = Path(environment)
    expected, template_issues = parse(_read(template_path), str(template_path))
    actual, environment_issues = parse(_read(environment_path), str(environment_path))
    issues = template_issues + environment_issues
    # A broken contract cannot reliably define required keys.
    if not template_issues:
        for key in sorted(expected):
            if key not in actual:
                issues.append(Issue("error", "missing_key", str(environment_path),
                                    f"Required key '{key}' is missing.", key=key))
            elif actual[key].empty:
                issues.append(Issue("error", "empty_value", str(environment_path),
                                    f"Required key '{key}' is blank.", actual[key].line, key))
        for key in sorted(actual.keys() - expected.keys()):
            issues.append(Issue("error" if strict else "warning", "extra_key", str(environment_path),
                                f"Key '{key}' is absent from the template.", actual[key].line, key))
    return Report(str(template_path), str(environment_path), len(expected), tuple(issues))
