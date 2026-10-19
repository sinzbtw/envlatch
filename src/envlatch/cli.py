"""Command-line interface for EnvLatch."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import __version__
from .core import InputError, Report, check


def render_text(report: Report) -> str:
    lines = []
    for issue in report.issues:
        location = issue.path
        if issue.line is not None:
            location += f":{issue.line}"
        lines.append(f"{issue.severity.upper()} [{issue.code}] {location}: {issue.message}")
    status = "PASS" if report.valid else "FAIL"
    lines.append(f"{status}: {report.checked_keys} required key(s), "
                 f"{report.errors} error(s), {report.warnings} warning(s). Values are never displayed.")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="envlatch",
        description="Check dotenv keys against a template without displaying values.",
    )
    parser.add_argument("--version", action="version", version=f"EnvLatch {__version__}")
    parser.add_argument("--template", required=True, metavar="PATH", help="dotenv contract file")
    parser.add_argument("--env", required=True, metavar="PATH", help="dotenv file to validate")
    parser.add_argument("--strict", action="store_true", help="treat extra keys as errors")
    arguments = parser.parse_args(argv)
    try:
        report = check(arguments.template, arguments.env, strict=arguments.strict)
    except InputError as error:
        print(f"ERROR [input_error] {error}", file=sys.stderr)
        return 2
    print(render_text(report))
    return 0 if report.valid else 1
