"""Command-line interface for EnvLatch."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys
from collections.abc import Sequence

from . import __version__
from .core import InputError, Issue, Report, check


def render_text(report: Report) -> str:
    lines = []
    for issue in report.issues:
        location = issue.path or "<input>"
        if issue.line is not None:
            location += f":{issue.line}"
        lines.append(f"{issue.severity.upper()} [{issue.code}] {location}: {issue.message}")
    status = "PASS" if report.valid else "FAIL"
    lines.append(f"{status}: {report.checked_keys} required key(s), "
                 f"{report.errors} error(s), {report.warnings} warning(s). Values are never displayed.")
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
    parser.add_argument("--format", choices=("text", "json"), default="text",
                        help="output format (default: text)")
    arguments = parser.parse_args(argv)
    try:
        report = check(arguments.template, arguments.env, strict=arguments.strict)
    except InputError as error:
        if arguments.format == "json":
            report = Report(arguments.template, tuple(arguments.env), 0,
                            (Issue("error", "input_error", None, str(error)),))
            print(render_json(report, status="input_error"))
        else:
            print(f"ERROR [input_error] {error}", file=sys.stderr)
        return 2
    print(render_json(report) if arguments.format == "json" else render_text(report))
    return 0 if report.valid else 1
