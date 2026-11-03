"""Text, JSON and GitHub Actions output for comparison mode."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace

from . import __version__
from .cli import render_github
from .compare_config import ComparisonConfig, load_comparison_config
from .comparison import ComparisonIssue, ComparisonReport, Environment, compare, environment_paths
from .config import Config
from .core import InputError, Report


def _summary(report):
    return (
        f"{'PASS' if report.valid else 'FAIL'}: {len(report.environments)} environment(s), "
        f"{len(report.keys)} compared key(s), {report.errors} error(s), "
        f"{report.warnings} warning(s). Values are never displayed."
    )


def render_comparison(report: ComparisonReport, output_format: str, *, status=None) -> str:
    if output_format == "json":
        data = asdict(report)
        data.update(
            schema_version=1,
            kind="comparison",
            status=status or ("pass" if report.valid else "fail"),
            errors=report.errors,
            warnings=report.warnings,
        )
        return json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True)
    contextual = tuple(
        replace(issue, message=f"[{issue.environment}] {issue.message}")
        if issue.environment
        else issue
        for issue in report.issues
    )
    if output_format == "github":
        proxy = Report(report.template, (), 0, contextual)
        return "\n".join([*render_github(proxy).splitlines()[:-1], _summary(report)])
    lines = []
    for row in report.keys:
        states = ", ".join(
            f"{item.environment}={item.state}"
            + (f" ({'/'.join(item.types)})" if item.types else "")
            for item in row.observations
        )
        lines.append(f"{row.key}: {states}")
    for issue in contextual:
        location = issue.path or "<comparison>"
        if issue.line is not None:
            location += f":{issue.line}"
        lines.append(f"{issue.severity.upper()} [{issue.code}] {location}: {issue.message}")
    return "\n".join([*lines, _summary(report)])


def _groups(specifications):
    groups = {}
    for specification in specifications:
        if "=" not in specification:
            raise InputError("Comparison --env requires NAME=PATH.")
        name, path = specification.split("=", 1)
        groups.setdefault(name, []).append(path)
    return environment_paths(groups)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="envlatch compare",
        description="Compare independent environments without displaying values.",
    )
    parser.add_argument("--version", action="version", version=f"EnvLatch {__version__}")
    parser.add_argument("--config", metavar="PATH", help="explicit comparison JSON settings")
    parser.add_argument("--template", metavar="PATH")
    parser.add_argument(
        "--env",
        action="append",
        metavar="NAME=PATH",
        help="repeat a name to overlay that environment's files",
    )
    strictness = parser.add_mutually_exclusive_group()
    strictness.add_argument("--strict", dest="strict", action="store_true", default=None)
    strictness.add_argument("--no-strict", dest="strict", action="store_false", default=None)
    parser.add_argument("--optional", action="append", metavar="KEY")
    parser.add_argument("--allow-extra", action="append", metavar="PATTERN")
    parser.add_argument(
        "--compare-values",
        action="append",
        metavar="KEY",
        help="compare selected settings for equality; values stay hidden",
    )
    parser.add_argument("--format", choices=("text", "json", "github"))
    args = parser.parse_args(argv)
    output_format = args.format or "text"
    template = args.template
    groups = {}
    try:
        loaded = (
            load_comparison_config(args.config)
            if args.config is not None
            else ComparisonConfig(Config(), {}, ())
        )
        settings = loaded.settings
        output_format = args.format or settings.output_format
        template = args.template if args.template is not None else settings.template
        groups = _groups(args.env) if args.env is not None else loaded.environments
        if template is None:
            parser.error("provide --template, directly or through --config")
        report = compare(
            template,
            groups,
            strict=args.strict if args.strict is not None else settings.strict,
            optional_keys=args.optional if args.optional is not None else settings.optional_keys,
            allow_extra=args.allow_extra if args.allow_extra is not None else settings.allow_extra,
            types=settings.types,
            compare_values=args.compare_values
            if args.compare_values is not None
            else loaded.compare_values,
        )
    except InputError as error:
        if output_format == "text":
            print(f"ERROR [input_error] {error}", file=sys.stderr)
        else:
            report = ComparisonReport(
                template or "",
                tuple(Environment(name, files) for name, files in groups.items()),
                (),
                (ComparisonIssue("error", "input_error", None, str(error)),),
            )
            print(render_comparison(report, output_format, status="input_error"))
        return 2
    print(render_comparison(report, output_format))
    return 0 if report.valid else 1
