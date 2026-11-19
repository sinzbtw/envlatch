"""The parser keeps only names, line numbers and whether a value is blank."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from fnmatch import fnmatchcase
from pathlib import Path

from ._types import TYPE_NAMES, matches_type

_EXPORT = re.compile(r"export[ \t]+")
_EXTRA_CHARACTERS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_*?")
_ConstraintSettings = Mapping[str, Mapping[str, int | Sequence[str]]]


def _valid_key(value) -> bool:
    return isinstance(value, str) and value.isascii() and value.isidentifier()


def _valid_extra_pattern(value) -> bool:
    return (
        isinstance(value, str) and bool(value) and all(char in _EXTRA_CHARACTERS for char in value)
    )


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
    environments: tuple[str, ...]
    checked_keys: int
    issues: tuple[Issue, ...]

    @property
    def environment(self) -> str:
        """The final input file, retained for single-file API compatibility."""
        return self.environments[-1]

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
    """Invalid input or configuration; messages never contain dotenv values."""


@dataclass(frozen=True)
class _ValueConstraint:
    one_of: frozenset[str] | None = field(repr=False)
    minimum: int | None = field(repr=False)
    maximum: int | None = field(repr=False)

    def matches(self, value: str) -> bool:
        if self.one_of is not None and value not in self.one_of:
            return False
        if self.minimum is None and self.maximum is None:
            return True
        if not matches_type(value, "integer"):
            return False
        # Decimal compares exactly without Python's int(string) digit limit.
        number = Decimal(value)
        return (self.minimum is None or number >= self.minimum) and (
            self.maximum is None or number <= self.maximum
        )


def validate_constraints(constraints: _ConstraintSettings | None) -> dict[str, _ValueConstraint]:
    """Validate and snapshot rules without exposing configured values."""
    if constraints is None:
        return {}
    if not isinstance(constraints, Mapping):
        raise InputError("Constraints must be an object mapping variable names to rules.")
    rules = {}
    for key, rule in constraints.items():
        if not _valid_key(key):
            raise InputError("Constraints must use ASCII environment variable names.")
        if not isinstance(rule, Mapping) or not rule or rule.keys() - {"one_of", "min", "max"}:
            raise InputError("Each constraint must contain one or more of one_of, min and max.")
        choices = None
        if "one_of" in rule:
            choices = rule["one_of"]
            if (
                not isinstance(choices, Sequence)
                or isinstance(choices, (str, bytes))
                or not choices
                or any(
                    not isinstance(item, str)
                    or not item.strip()
                    or any(char in item for char in ("\r", "\n", "\x00"))
                    for item in choices
                )
            ):
                raise InputError(
                    "Constraint 'one_of' requires a nonempty array of nonblank, single-line strings."
                )
            try:
                for item in choices:
                    item.encode("utf-8")
            except UnicodeError:
                raise InputError("Constraint 'one_of' contains invalid Unicode.") from None
            choices = frozenset(choices)
        for bound in ("min", "max"):
            if bound in rule and type(rule[bound]) is not int:
                raise InputError("Constraint bounds must be integers.")
        minimum, maximum = rule.get("min"), rule.get("max")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise InputError("Constraint 'min' must be less than or equal to 'max'.")
        rules[key] = _ValueConstraint(choices, minimum, maximum)
    return rules


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


def _literal_value(value: str) -> str | None:
    """Extract a literal transient value; None means invalid quoted syntax."""
    value = value.strip()
    if not value or value.startswith("#"):
        return ""
    if value[0] not in ("'", '"'):
        for index, character in enumerate(value):
            if character == "#" and index and value[index - 1].isspace():
                value = value[:index]
                break
        return value.strip()

    end = _closing_quote(value)
    if end is None:
        return None
    tail = value[end + 1 :].strip()
    if tail and not tail.startswith("#"):
        return None
    return value[1:end]


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeError:
        raise InputError(f"Cannot read UTF-8 input: {path}") from None
    except OSError:
        raise InputError(f"Cannot read input file: {path}") from None


def parse(text: str, path: str) -> tuple[dict[str, Entry], list[Issue]]:
    """Parse a single-line dotenv dialect and discard all actual values."""
    entries, issues, _ = _parse(text, path, {})
    return entries, issues


def _parse(
    text: str,
    path: str,
    types: Mapping[str, str],
    observe: Callable[[str, str], None] | None = None,
    *,
    constraints: Mapping[str, _ValueConstraint] | None = None,
) -> tuple[dict[str, Entry], list[Issue], dict[str, str]]:
    entries: dict[str, Entry] = {}
    issues: list[Issue] = []
    invalid_values: dict[str, str] = {}
    # Stop on malformed syntax so rejected multiline fragments cannot become keys.
    # Only LF/CRLF are physical line boundaries; Unicode in values stays literal.
    for line_number, raw in enumerate(text.removeprefix("\ufeff").split("\n"), 1):
        line = raw.rstrip("\r").strip()
        if not line or line.startswith("#"):
            continue
        if "\x00" in line:
            issues.append(
                Issue(
                    "error",
                    "invalid_syntax",
                    path,
                    "NUL characters are not supported.",
                    line_number,
                )
            )
            break
        line = _EXPORT.sub("", line, count=1)
        if "=" not in line:
            issues.append(
                Issue("error", "invalid_syntax", path, "Expected KEY=VALUE.", line_number)
            )
            break
        key, value = line.split("=", 1)
        key = key.strip()
        if not _valid_key(key):
            issues.append(
                Issue(
                    "error",
                    "invalid_key",
                    path,
                    "Expected an ASCII environment variable name.",
                    line_number,
                )
            )
            break
        literal = _literal_value(value)
        if literal is None:
            issues.append(
                Issue(
                    "error",
                    "invalid_value",
                    path,
                    "Expected a single-line value with balanced quotes and no trailing text.",
                    line_number,
                    key,
                )
            )
            break
        if key in entries:
            issues.append(
                Issue(
                    "error",
                    "duplicate_key",
                    path,
                    f"Duplicate key '{key}'; first defined on line {entries[key].line}.",
                    line_number,
                    key,
                )
            )
            continue
        empty = not literal.strip()
        if observe is not None:
            observe(key, literal)
        if not empty:
            if key in types and not matches_type(literal, types[key]):
                invalid_values[key] = "invalid_type"
            elif (
                constraints is not None
                and key in constraints
                and not constraints[key].matches(literal)
            ):
                invalid_values[key] = "invalid_constraint"
        entries[key] = Entry(key, line_number, empty)
    return entries, issues, invalid_values


def validate_types(types: Mapping[str, str] | None) -> dict[str, str]:
    """Copy rules, rejecting malformed settings without echoing their contents."""
    if types is None:
        return {}
    if not isinstance(types, Mapping):
        raise InputError("Type rules must be an object mapping variable names to type names.")
    rules = dict(types)
    if any(not _valid_key(key) for key in rules):
        raise InputError("Type rules must use ASCII environment variable names.")
    if any(not isinstance(kind, str) or kind not in TYPE_NAMES for kind in rules.values()):
        raise InputError("Type rules must use string, integer, boolean, url or port.")
    return rules


@dataclass(frozen=True)
class _CheckResult:
    report: Report
    entries: dict[str, Entry]
    sources: dict[str, str]
    expected: dict[str, Entry]
    template_valid: bool


def check(
    template: str | Path,
    environment: str | Path | Sequence[str | Path],
    *,
    strict: bool = False,
    optional_keys: Iterable[str] = (),
    allow_extra: Iterable[str] = (),
    types: Mapping[str, str] | None = None,
    constraints: _ConstraintSettings | None = None,
) -> Report:
    """Validate a contract against files merged in order, with later keys winning."""
    return _check(
        template,
        environment,
        strict=strict,
        optional_keys=optional_keys,
        allow_extra=allow_extra,
        types=types,
        constraints=validate_constraints(constraints),
    ).report


def _check(
    template: str | Path,
    environment: str | Path | Sequence[str | Path],
    *,
    strict: bool = False,
    optional_keys: Iterable[str] = (),
    allow_extra: Iterable[str] = (),
    types: Mapping[str, str] | None = None,
    constraints: Mapping[str, _ValueConstraint],
    observe: Callable[[str, str], None] | None = None,
) -> _CheckResult:
    """Validate a contract against files merged in order, with later keys winning."""
    type_rules = validate_types(types)
    if isinstance(optional_keys, (str, bytes)):
        raise InputError("Optional keys must be a sequence of names, not a single string.")
    try:
        optional_names = tuple(optional_keys)
    except TypeError:
        raise InputError("Optional keys must be an iterable of names.") from None
    if any(not _valid_key(key) for key in optional_names):
        raise InputError("Optional keys must use ASCII environment variable names.")
    optional = frozenset(optional_names)
    if isinstance(allow_extra, (str, bytes)):
        raise InputError(
            "Allow-extra patterns must be an iterable of patterns, not a single string."
        )
    try:
        extra_patterns = tuple(allow_extra)
    except TypeError:
        raise InputError("Allow-extra patterns must be an iterable of patterns.") from None
    if any(not _valid_extra_pattern(pattern) for pattern in extra_patterns):
        raise InputError(
            "Allow-extra patterns must contain only ASCII letters, digits, underscores, '*' or '?'."
        )
    template_path = Path(template)
    if isinstance(environment, (str, Path)):
        environment_paths = (Path(environment),)
    else:
        environment_paths = tuple(Path(path) for path in environment)
    if not environment_paths:
        raise InputError("At least one environment file is required.")

    expected, template_issues = parse(_read(template_path), str(template_path))
    issues = list(template_issues)
    actual: dict[str, Entry] = {}
    sources: dict[str, str] = {}
    invalid_values: dict[str, str] = {}
    for environment_path in environment_paths:
        entries, file_issues, file_invalid_values = _parse(
            _read(environment_path),
            str(environment_path),
            type_rules,
            observe,
            constraints=constraints,
        )
        issues.extend(file_issues)
        actual.update(entries)
        sources.update((key, str(environment_path)) for key in entries)
        for key in invalid_values.keys() & entries.keys():
            del invalid_values[key]
        invalid_values.update(file_invalid_values)

    # A broken contract cannot reliably define required keys.
    if not template_issues:
        for key in sorted(type_rules.keys() - expected.keys()):
            issues.append(
                Issue(
                    "error",
                    "unknown_type_key",
                    str(template_path),
                    f"Typed key '{key}' is absent from the template.",
                    key=key,
                )
            )
        for key in sorted(constraints.keys() - expected.keys()):
            issues.append(
                Issue(
                    "error",
                    "unknown_constraint_key",
                    str(template_path),
                    f"Constrained key '{key}' is absent from the template.",
                    key=key,
                )
            )
        for key in sorted(optional - expected.keys()):
            issues.append(
                Issue(
                    "error",
                    "unknown_optional_key",
                    str(template_path),
                    f"Optional key '{key}' is absent from the template.",
                    key=key,
                )
            )
        for key in sorted(expected.keys() - optional):
            if key not in actual:
                issues.append(
                    Issue(
                        "error",
                        "missing_key",
                        str(environment_paths[-1]),
                        f"Required key '{key}' is missing.",
                        key=key,
                    )
                )
            elif actual[key].empty:
                issues.append(
                    Issue(
                        "error",
                        "empty_value",
                        sources[key],
                        f"Required key '{key}' is blank.",
                        actual[key].line,
                        key,
                    )
                )
        for key in sorted(actual.keys() - expected.keys()):
            if any(fnmatchcase(key, pattern) for pattern in extra_patterns):
                continue
            issues.append(
                Issue(
                    "error" if strict else "warning",
                    "extra_key",
                    sources[key],
                    f"Key '{key}' is absent from the template.",
                    actual[key].line,
                    key,
                )
            )
        for key in sorted(invalid_values.keys() & expected.keys()):
            code = invalid_values[key]
            message = (
                f"Key '{key}' must have type '{type_rules[key]}'."
                if code == "invalid_type"
                else f"Key '{key}' does not meet its configured value constraints."
            )
            issues.append(Issue("error", code, sources[key], message, actual[key].line, key))
    report = Report(
        str(template_path),
        tuple(str(path) for path in environment_paths),
        len(expected.keys() - optional),
        tuple(issues),
    )
    return _CheckResult(report, actual, sources, expected, not template_issues)
