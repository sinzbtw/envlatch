"""Explicit JSON settings for independent named environments."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .comparison import comparison_keys, environment_paths
from .config import _FIELDS, Config, _load_object, _settings, _strings
from .core import InputError


@dataclass(frozen=True)
class ComparisonConfig:
    settings: Config
    environments: dict[str, tuple[str, ...]]
    compare_values: tuple[str, ...]


def load_comparison_config(path: str | Path) -> ComparisonConfig:
    data = _load_object(path)
    fields = (_FIELDS - {"env"}) | {"environments", "compare_values"}
    if data.keys() - fields:
        raise InputError(
            "Unknown comparison option. Use template, environments, strict, optional, allow_extra, types, compare_values or format."
        )
    groups = data.pop("environments", {})
    if not isinstance(groups, dict):
        raise InputError("Configuration field 'environments' requires an object of file arrays.")
    groups = {
        name: _strings(files, "environments", nonempty=True) for name, files in groups.items()
    }
    groups = environment_paths(groups)
    base = Path(path).absolute().parent
    resolved = {
        name: tuple(os.path.abspath(base / file) for file in files)
        for name, files in groups.items()
    }
    selected = (
        comparison_keys(_strings(data.pop("compare_values"), "compare_values"))
        if "compare_values" in data
        else ()
    )
    return ComparisonConfig(_settings(data, base), resolved, selected)
