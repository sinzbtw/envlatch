"""Load explicit JSON settings without executing configuration code."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path

from .core import InputError

_FIELDS = frozenset(('template', 'env', 'strict', 'optional', 'allow_extra', 'format'))
_FORMATS = ('text', 'json', 'github')


@dataclass(frozen=True)
class Config:
    template: str | None = None
    environments: tuple[str, ...] | None = None
    strict: bool = False
    optional_keys: tuple[str, ...] = ()
    allow_extra: tuple[str, ...] = ()
    output_format: str = 'text'


class _InvalidJSON(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _InvalidJSON('Duplicate JSON configuration fields are not allowed.')
        result[key] = value
    return result


def _reject_constant(_value):
    raise _InvalidJSON('Non-standard JSON numeric constants are not allowed.')


def _string(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise InputError(f"Configuration field '{field}' requires nonempty strings without NUL characters.")
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise InputError(f"Configuration field '{field}' contains invalid Unicode.") from None
    return value


def _strings(value, field: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (nonempty and not value):
        qualifier = 'a nonempty array' if nonempty else 'an array'
        raise InputError(f"Configuration field '{field}' requires {qualifier} of strings.")
    return tuple(_string(item, field) for item in value)


def load_config(path: str | Path) -> Config:
    """Read settings; configured paths are relative to the config directory."""
    config_path = Path(path)
    try:
        text = config_path.read_text(encoding='utf-8-sig')
    except (OSError, UnicodeError, ValueError):
        raise InputError(f'Cannot read UTF-8 configuration file: {config_path}') from None
    try:
        data = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except json.JSONDecodeError as error:
        raise InputError(f'Invalid JSON configuration: {config_path} (line {error.lineno}, column {error.colno}).') from None
    except _InvalidJSON as error:
        raise InputError(f'{error} File: {config_path}') from None
    except (ValueError, RecursionError):
        raise InputError(f'Invalid JSON configuration: {config_path}') from None
    if not isinstance(data, dict):
        raise InputError('Configuration must be a JSON object.')
    if data.keys() - _FIELDS:
        raise InputError('Unknown configuration option. Allowed options: template, env, strict, optional, allow_extra, format.')
    if 'strict' in data and not isinstance(data['strict'], bool):
        raise InputError("Configuration field 'strict' requires a boolean.")
    if 'format' in data and data['format'] not in _FORMATS:
        raise InputError("Configuration field 'format' must be text, json or github.")
    base = config_path.absolute().parent
    template = None
    environments = None
    if 'template' in data:
        template = os.path.abspath(base / _string(data['template'], 'template'))
    if 'env' in data:
        environments = tuple(os.path.abspath(base / value)
                             for value in _strings(data['env'], 'env', nonempty=True))
    optional = _strings(data['optional'], 'optional') if 'optional' in data else ()
    allowed = _strings(data['allow_extra'], 'allow_extra') if 'allow_extra' in data else ()
    return Config(template, environments, data.get('strict', False), optional, allowed, data.get('format', 'text'))
