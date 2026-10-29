"""Command-line interface for EnvLatch."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys
from collections.abc import Sequence

from . import __version__
from .core import InputError, Issue, Report, check
from .config import Config, load_config


def _summary(report: Report) -> str:
    status = "PASS" if report.valid else "FAIL"
    return (f"{status}: {report.checked_keys} required key(s), "
            f"{report.errors} error(s), {report.warnings} warning(s). Values are never displayed.")


def render_text(report: Report) -> str:
    lines = []
    for issue in report.issues:
        location = issue.path or "<input>"
        if issue.line is not None:
            location += f":{issue.line}"
        lines.append(f"{issue.severity.upper()} [{issue.code}] {location}: {issue.message}")
    lines.append(_summary(report))
    return "\n".join(lines)


def render_json(report: Report, *, status: str | None = None) -> str:
    """Render the versioned automation format without source values."""
    document = {
        "schema_version": 1,
        "status": status or ("pass" if report.valid else "fail"),
        "template": report.template,
        "environments": list(report.environments),
        "checked_keys": report.checked_keys,
        "errors": report.errors,
        "warnings": report.warnings,
        "issues": [asdict(issue) for issue in report.issues],
    }
    return json.dumps(document, ensure_ascii=True, indent=2, sort_keys=True)


def _workflow_data(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _workflow_property(value: str) -> str:
    return _workflow_data(value).replace(":", "%3A").replace(",", "%2C")


def render_github(report: Report) -> str:
    """Emit escaped GitHub Actions annotations, followed by the normal summary."""
    lines = []
    for issue in report.issues:
        properties = [("title", "EnvLatch: " + issue.code)]
        if issue.path is not None:
            properties.append(("file", issue.path))
            if issue.line is not None:
                properties.append(("line", str(issue.line)))
        metadata = ",".join(f"{key}={_workflow_property(value)}" for key, value in properties)
        lines.append(f"::{issue.severity} {metadata}::{_workflow_data(issue.message)}")
    lines.append(_summary(report))
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="envlatch",
        description="Check dotenv keys against a template without displaying values.",
    )
    parser.add_argument("--version", action="version", version=f"EnvLatch {__version__}")
    parser.add_argument("--config", metavar="PATH", help="explicit JSON settings file")
    parser.add_argument("--template", metavar="PATH", help="dotenv contract file")
    parser.add_argument("--env", action="append", metavar="PATH",
                        help="dotenv file; repeat to overlay files in order (later keys win)")
    strictness = parser.add_mutually_exclusive_group()
    strictness.add_argument("--strict", dest="strict", action="store_true", default=None,
                            help="treat extra keys as errors")
    strictness.add_argument("--no-strict", dest="strict", action="store_false", default=None,
                            help="treat extra keys as warnings, overriding config strict mode")
    parser.add_argument("--optional", action="append", metavar="KEY",
                        help="template key allowed to be missing or blank; repeat for more keys")
    parser.add_argument("--allow-extra", action="append", metavar="PATTERN",
                        help="allow extra keys matching a case-sensitive '*'/'?' pattern; repeat for more")
    parser.add_argument("--format", choices=("text", "json", "github"),
                        help="output format (default: config setting or text)")
    arguments = parser.parse_args(argv)
    output_format = arguments.format or "text"
    template = arguments.template
    environments = tuple(arguments.env) if arguments.env is not None else None
    try:
        settings = load_config(arguments.config) if arguments.config is not None else Config()
        output_format = arguments.format or settings.output_format
        template = arguments.template if arguments.template is not None else settings.template
        environments = tuple(arguments.env) if arguments.env is not None else settings.environments
        if template is None or environments is None:
            parser.error("provide --template and --env, directly or through --config")
        strict = arguments.strict if arguments.strict is not None else settings.strict
        optional = arguments.optional if arguments.optional is not None else settings.optional_keys
        allowed = arguments.allow_extra if arguments.allow_extra is not None else settings.allow_extra
        report = check(template, environments, strict=strict, optional_keys=optional, allow_extra=allowed)
    except InputError as error:
        if output_format in ("json", "github"):
            report = Report(template or "", tuple(environments or ()), 0,
                            (Issue("error", "input_error", None, str(error)),))
            print(render_json(report, status="input_error")
                  if output_format == "json" else render_github(report))
        else:
            print(f"ERROR [input_error] {error}", file=sys.stderr)
        return 2
    renderer = {"text": render_text, "json": render_json, "github": render_github}[output_format]
    print(renderer(report))
    return 0 if report.valid else 1
