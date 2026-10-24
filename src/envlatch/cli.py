"""Command-line interface for EnvLatch."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys
from collections.abc import Sequence

from . import __version__
from .core import InputError, Issue, Report, check


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
    parser.add_argument("--template", required=True, metavar="PATH", help="dotenv contract file")
    parser.add_argument("--env", required=True, action="append", metavar="PATH",
                        help="dotenv file; repeat to overlay files in order (later keys win)")
    parser.add_argument("--strict", action="store_true", help="treat extra keys as errors")
    parser.add_argument("--optional", action="append", default=[], metavar="KEY",
                        help="template key allowed to be missing or blank; repeat for more keys")
    parser.add_argument("--format", choices=("text", "json", "github"), default="text",
                        help="output format (default: text)")
    arguments = parser.parse_args(argv)
    try:
        report = check(arguments.template, arguments.env, strict=arguments.strict,
                       optional_keys=arguments.optional)
    except InputError as error:
        if arguments.format in ("json", "github"):
            report = Report(arguments.template, tuple(arguments.env), 0,
                            (Issue("error", "input_error", None, str(error)),))
            print(render_json(report, status="input_error")
                  if arguments.format == "json" else render_github(report))
        else:
            print(f"ERROR [input_error] {error}", file=sys.stderr)
        return 2
    renderer = {"text": render_text, "json": render_json, "github": render_github}[arguments.format]
    print(renderer(report))
    return 0 if report.valid else 1
