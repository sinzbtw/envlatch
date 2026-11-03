"""Compare named environments while retaining only safe metadata."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ._types import matches_type
from .core import InputError, Issue, _check, _valid_key, validate_types

_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,31}\Z")


@dataclass(frozen=True)
class Environment:
    name: str
    files: tuple[str, ...]


@dataclass(frozen=True)
class ComparisonIssue(Issue):
    environment: str | None = None


@dataclass(frozen=True)
class Observation:
    environment: str
    state: str
    types: tuple[str, ...]
    path: str
    line: int | None


@dataclass(frozen=True)
class ComparedKey:
    key: str
    observations: tuple[Observation, ...]


@dataclass(frozen=True)
class ComparisonReport:
    template: str
    environments: tuple[Environment, ...]
    keys: tuple[ComparedKey, ...]
    issues: tuple[ComparisonIssue, ...]

    @property
    def errors(self) -> int:
        return sum(issue.severity == "error" for issue in self.issues)

    @property
    def warnings(self) -> int:
        return sum(issue.severity == "warning" for issue in self.issues)

    @property
    def valid(self) -> bool:
        return self.errors == 0


def environment_paths(environments: Mapping) -> dict[str, tuple[str, ...]]:
    """Validate labels/paths without ever echoing rejected input."""
    if not isinstance(environments, Mapping):
        raise InputError("Environments must be an object mapping names to files.")
    result = {}
    for name, paths in environments.items():
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise InputError(
                "Environment names must start with an ASCII letter and use at most 32 letters, digits, '_' or '-'."
            )
        if isinstance(paths, (str, Path)):
            paths = (paths,)
        if not isinstance(paths, Sequence) or not paths:
            raise InputError("Each environment requires a nonempty sequence of file paths.")
        if any(
            not isinstance(path, (str, Path)) or not str(path).strip() or "\x00" in str(path)
            for path in paths
        ):
            raise InputError("Environment files must use nonempty paths without NUL characters.")
        result[name] = tuple(str(path) for path in paths)
    return result


def _sequence(values, description):
    if isinstance(values, (str, bytes)):
        raise InputError(f"{description} must be an iterable, not a single string.")
    try:
        return tuple(values)
    except TypeError:
        raise InputError(f"{description} must be an iterable.") from None


def comparison_keys(values: Iterable[str]) -> tuple[str, ...]:
    keys = _sequence(values, "Compared setting names")
    if any(not _valid_key(key) for key in keys):
        raise InputError("Compared settings must use ASCII environment variable names.")
    return tuple(sorted(set(keys)))


def _observed_types(value: str, declared: str | None) -> tuple[str, ...]:
    if not value.strip():
        return ()
    if declared is not None and matches_type(value, declared):
        return (declared,)
    candidates = tuple(kind for kind in ("boolean", "integer", "url") if matches_type(value, kind))
    return candidates or ("string",)


def compare(
    template: str | Path,
    environments: Mapping[str, str | Path | Sequence[str | Path]],
    *,
    strict: bool = False,
    optional_keys: Iterable[str] = (),
    allow_extra: Iterable[str] = (),
    types: Mapping[str, str] | None = None,
    compare_values: Iterable[str] = (),
) -> ComparisonReport:
    """Validate each environment, compare structure/types and explicitly selected settings."""
    if (
        not isinstance(template, (str, Path))
        or not str(template).strip()
        or "\x00" in str(template)
    ):
        raise InputError("Comparison requires a nonempty template path without NUL characters.")
    groups = environment_paths(environments)
    if len(groups) < 2:
        raise InputError("Comparison requires at least two named environments.")
    rules = validate_types(types)
    selected = comparison_keys(compare_values)
    optional = _sequence(optional_keys, "Optional keys")
    allowed = _sequence(allow_extra, "Allow-extra patterns")
    # A fresh per-call HMAC key prevents reusable fingerprints or dictionary lookup.
    # Neither the key nor the digests are included in returned metadata or diagnostics.
    secret = secrets.token_bytes(32)
    results = {}
    metadata = {}
    digests = {}
    issues = []
    for name, files in groups.items():
        observed = {}
        fingerprints = {}

        def observe(key, literal):
            observed[key] = _observed_types(literal, rules.get(key))
            if key in selected:
                value = literal if literal.strip() else ""
                fingerprints[key] = hmac.digest(secret, value.encode("utf-8"), hashlib.sha256)

        result = _check(
            template,
            files,
            strict=strict,
            optional_keys=optional,
            allow_extra=allowed,
            types=rules,
            observe=observe,
        )
        results[name] = result
        metadata[name] = observed
        digests[name] = fingerprints
        issues.extend(
            ComparisonIssue(
                issue.severity, issue.code, issue.path, issue.message, issue.line, issue.key, name
            )
            for issue in result.report.issues
        )

    first = next(iter(results.values()))
    template_valid = first.template_valid
    if template_valid:
        for key in sorted(set(selected) - first.expected.keys()):
            issues.append(
                ComparisonIssue(
                    "error",
                    "unknown_compare_key",
                    str(template),
                    f"Compared setting '{key}' is absent from the template.",
                    key=key,
                )
            )
    all_keys = sorted(
        set(first.expected).union(*(result.entries.keys() for result in results.values()))
    )
    rows = []
    for key in all_keys:
        observations = []
        for name, result in results.items():
            entry = result.entries.get(key)
            state = "missing" if entry is None else "blank" if entry.empty else "present"
            observations.append(
                Observation(
                    name,
                    state,
                    metadata[name].get(key, ()),
                    result.sources.get(key, groups[name][-1]),
                    entry.line if entry else None,
                )
            )
            # Required missing/blank keys already have precise validation errors.
            has_validation = any(
                issue.environment == name
                and issue.key == key
                and issue.code in ("missing_key", "empty_value")
                for issue in issues
            )
            if template_valid and not has_validation and state in ("missing", "blank"):
                if any(
                    key in other.entries and (state == "missing" or not other.entries[key].empty)
                    for other in results.values()
                ):
                    issues.append(
                        ComparisonIssue(
                            "warning",
                            "presence_mismatch",
                            observations[-1].path,
                            f"Key '{key}' is {state} here but differs in presence or blankness in another environment.",
                            observations[-1].line,
                            key,
                            name,
                        )
                    )
        rows.append(ComparedKey(key, tuple(observations)))
        if not template_valid:
            continue
        nonblank = [
            set(observation.types) for observation in observations if observation.state == "present"
        ]
        invalid_type = any(issue.key == key and issue.code == "invalid_type" for issue in issues)
        if nonblank and not set.intersection(*nonblank) and not invalid_type:
            issues.append(
                ComparisonIssue(
                    "error",
                    "type_mismatch",
                    None,
                    f"Key '{key}' has different value types across environments.",
                    key=key,
                )
            )
        values = {group[key] for group in digests.values() if key in group}
        if key in selected and key in first.expected and len(values) > 1:
            issues.append(
                ComparisonIssue(
                    "error",
                    "value_mismatch",
                    None,
                    f"Setting '{key}' differs across environments; values are hidden.",
                    key=key,
                )
            )
    return ComparisonReport(
        str(template),
        tuple(Environment(name, files) for name, files in groups.items()),
        tuple(rows),
        tuple(issues),
    )
