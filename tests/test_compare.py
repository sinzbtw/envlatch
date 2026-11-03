"""Independent environments, hidden setting differences and legacy compatibility."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from envlatch import compare
from envlatch.compare import comparison_keys, environment_paths
from envlatch.compare_cli import render_comparison
from envlatch.compare_config import load_comparison_config
from envlatch.core import InputError, check, parse


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.template = self.root / "template.env"
        self.template.write_text("TOKEN=\nPORT=\nDEBUG=\n", encoding="utf-8")
        self.groups = {
            name: self.root / (name + ".env") for name in ("dev", "staging", "production")
        }
        self.config = self.root / "compare.json"
        for index, path in enumerate(self.groups.values()):
            path.write_text(
                f"TOKEN=private-canary-{index}\nPORT=8000\nDEBUG=false\n", encoding="utf-8"
            )

    def write(self, name, text):
        self.groups[name].write_text(text, encoding="utf-8")

    def compare(self, **options):
        return compare(self.template, self.groups, **options)

    def settings(self, **changes):
        return {
            "template": "template.env",
            "environments": {name: [path.name] for name, path in self.groups.items()},
            **changes,
        }

    def config_write(self, **changes):
        self.config.write_text(json.dumps(self.settings(**changes)), encoding="utf-8")

    def cli(self, *args, config=True):
        command = [sys.executable, "-m", "envlatch", "compare"]
        if config:
            command += ["--config", str(self.config)]
        return subprocess.run(
            [*command, *args], cwd=self.root.parent, capture_output=True, text=True, check=False
        )

    def test_same_structure_passes_without_comparing_secret_values(self):
        report = self.compare()
        self.assertTrue(report.valid)
        self.assertEqual((report.errors, report.warnings, len(report.keys)), (0, 0, 3))
        self.assertEqual([row.key for row in report.keys], ["DEBUG", "PORT", "TOKEN"])
        self.assertEqual([env.name for env in report.environments], list(self.groups))
        self.assertEqual(report.environments[0].files, (str(self.groups["dev"]),))

    def test_missing_and_blank_required_values_keep_validation_errors(self):
        self.write("production", "PORT=\nDEBUG=false")
        report = self.compare()
        self.assertFalse(report.valid)
        self.assertEqual(
            [(i.code, i.environment, i.key) for i in report.issues],
            [("empty_value", "production", "PORT"), ("missing_key", "production", "TOKEN")],
        )
        token = next(row for row in report.keys if row.key == "TOKEN").observations[-1]
        self.assertEqual((token.state, token.line, token.types), ("missing", None, ()))

    def test_optional_presence_drift_warns_without_making_key_required(self):
        self.write("production", "TOKEN=t\nPORT=\n")
        report = self.compare(optional_keys=["PORT", "DEBUG"])
        self.assertTrue(report.valid)
        self.assertEqual(report.warnings, 2)
        self.assertEqual({i.code for i in report.issues}, {"presence_mismatch"})
        self.assertEqual({i.key for i in report.issues}, {"PORT", "DEBUG"})

    def test_absent_optional_keys_in_all_environments_do_not_warn(self):
        self.template.write_text("TOKEN=\nPORT=\nDEBUG=\nOPTIONAL=", encoding="utf-8")
        self.assertEqual(self.compare(optional_keys=["OPTIONAL"]).warnings, 0)

    def test_extra_keys_keep_warning_strict_and_allowance_policies(self):
        with self.groups["dev"].open("a", encoding="utf-8") as file:
            file.write("TOOL_DEBUG=yes\n")
        normal = self.compare()
        self.assertTrue(normal.valid)
        self.assertIn("extra_key", [i.code for i in normal.issues])
        self.assertFalse(self.compare(strict=True).valid)
        allowed = self.compare(strict=True, allow_extra=["TOOL_*"])
        self.assertTrue(allowed.valid)
        self.assertNotIn("extra_key", [i.code for i in allowed.issues])

    def test_untyped_boolean_integer_and_url_drift_are_detected(self):
        for value in ("42", "https://host.invalid/path", "ordinary-text"):
            with self.subTest(value=value):
                self.write("production", f"TOKEN=t\nPORT=8000\nDEBUG={value}")
                report = self.compare()
                self.assertEqual(
                    [(i.code, i.key) for i in report.issues], [("type_mismatch", "DEBUG")]
                )

    def test_zero_one_ambiguity_is_resolved_by_shared_type_compatibility(self):
        for value in ("1", "0"):
            self.write("dev", f"TOKEN=t\nPORT=8000\nDEBUG={value}")
            self.assertTrue(self.compare().valid)
        self.write("production", "TOKEN=t\nPORT=8000\nDEBUG=2")
        self.assertFalse(self.compare().valid)

    def test_ports_are_not_guessed_from_untyped_integers(self):
        self.write("production", "TOKEN=t\nPORT=-90000\nDEBUG=false")
        self.assertTrue(self.compare().valid)
        report = self.compare(types={"PORT": "port"})
        self.assertEqual([i.code for i in report.issues], ["invalid_type"])

    def test_declared_string_prevents_spurious_inference(self):
        self.write("production", "TOKEN=42\nPORT=8000\nDEBUG=false")
        self.assertFalse(self.compare().valid)
        self.assertTrue(self.compare(types={"TOKEN": "string"}).valid)

    def test_declared_boolean_errors_are_not_duplicated_as_drift(self):
        self.write("production", "TOKEN=t\nPORT=8000\nDEBUG=2")
        report = self.compare(types={"DEBUG": "boolean"})
        self.assertEqual(
            [(i.code, i.environment) for i in report.issues], [("invalid_type", "production")]
        )

    def test_selected_settings_differences_are_errors_without_values_or_hashes(self):
        report = self.compare(compare_values=["TOKEN"])
        self.assertEqual([i.code for i in report.issues], ["value_mismatch"])
        for render in (
            repr,
            lambda r: json.dumps(asdict(r)),
            lambda r: render_comparison(r, "text"),
            lambda r: render_comparison(r, "json"),
            lambda r: render_comparison(r, "github"),
        ):
            text = render(report)
            self.assertNotIn("private-canary", text)
            self.assertNotIn("digest", text)
            self.assertNotIn("fingerprint", text)
        self.assertFalse(report.valid)

    def test_selected_identical_values_pass_and_iterables_are_materialized_once(self):
        report = self.compare(
            compare_values=iter(["PORT", "PORT"]), optional_keys=iter([]), allow_extra=iter([])
        )
        self.assertTrue(report.valid)

    def test_selected_values_compare_literal_text_without_boolean_coercion(self):
        self.write("production", "TOKEN=t\nPORT=8000\nDEBUG=FALSE")
        self.assertTrue(self.compare(types={"DEBUG": "boolean"}).valid)
        report = self.compare(types={"DEBUG": "boolean"}, compare_values=["DEBUG"])
        self.assertEqual([i.code for i in report.issues], ["value_mismatch"])

    def test_blank_values_are_canonicalized_and_absent_optional_values_are_not_hashed(self):
        for name in self.groups:
            self.write(name, "TOKEN=t\nPORT=\nDEBUG=false")
        self.write("production", 'TOKEN=t\nPORT="  "\nDEBUG=false')
        self.assertTrue(self.compare(optional_keys=["PORT"], compare_values=["PORT"]).valid)
        self.write("production", "TOKEN=t\nDEBUG=false")
        self.assertTrue(self.compare(optional_keys=["PORT"], compare_values=["PORT"]).valid)

    def test_selected_blank_versus_nonblank_is_detected(self):
        self.write("production", "TOKEN=t\nPORT=\nDEBUG=false")
        report = self.compare(optional_keys=["PORT"], compare_values=["PORT"])
        self.assertIn("value_mismatch", [i.code for i in report.issues])

    def test_unknown_compared_setting_is_a_template_error_even_if_allowed_extra(self):
        report = self.compare(compare_values=["TYPO"], allow_extra=["*"])
        self.assertEqual(
            [(i.code, i.key, i.path) for i in report.issues],
            [("unknown_compare_key", "TYPO", str(self.template))],
        )

    def test_hmac_key_is_fresh_for_each_comparison_and_not_returned(self):
        with patch(
            "envlatch.compare.secrets.token_bytes", side_effect=[b"a" * 32, b"b" * 32]
        ) as random_key:
            first = self.compare(compare_values=["TOKEN"])
            second = self.compare(compare_values=["TOKEN"])
        self.assertEqual(random_key.call_count, 2)
        self.assertEqual(first, second)

    def test_overlay_order_and_winning_source_are_kept_separately_per_environment(self):
        local = self.root / "local.env"
        local.write_text("# overlay\nDEBUG=42", encoding="utf-8")
        groups = dict(self.groups)
        groups["dev"] = [self.groups["dev"], local]
        report = compare(self.template, groups)
        debug = report.keys[0].observations[0]
        self.assertEqual(
            (debug.state, debug.types, debug.path, debug.line),
            ("present", ("integer",), str(local), 2),
        )
        self.assertEqual(report.environments[0].files, (str(self.groups["dev"]), str(local)))
        local.write_text("DEBUG=false", encoding="utf-8")
        self.assertTrue(compare(self.template, groups).valid)

    def test_overridden_invalid_type_is_not_retained_as_drift(self):
        self.write("dev", "TOKEN=t\nPORT=oops\nDEBUG=false")
        local = self.root / "local.env"
        local.write_text("PORT=8000", encoding="utf-8")
        groups = {**self.groups, "dev": [self.groups["dev"], local]}
        self.assertTrue(compare(self.template, groups, types={"PORT": "port"}).valid)

    def test_duplicates_and_syntax_errors_survive_an_overlay(self):
        local = self.root / "local.env"
        local.write_text("TOKEN=okay\nPORT=8000\nDEBUG=false", encoding="utf-8")
        for text, code in [
            ("TOKEN=t\nTOKEN=other", "duplicate_key"),
            ('TOKEN="private-canary\nFRAGMENT_CANARY=42', "invalid_value"),
        ]:
            self.write("dev", text)
            report = compare(self.template, {**self.groups, "dev": [self.groups["dev"], local]})
            self.assertIn(code, [i.code for i in report.issues])
            self.assertNotIn("FRAGMENT_CANARY", repr(report))

    def test_broken_template_does_not_generate_comparison_policy_errors(self):
        self.template.write_text('TOKEN="private-canary', encoding="utf-8")
        report = self.compare(compare_values=["UNKNOWN"])
        self.assertEqual([i.code for i in report.issues], ["invalid_value"] * 3)
        self.assertNotIn("private-canary", repr(report))

    def test_input_file_errors_remain_safe(self):
        for contents in (None, b"TOKEN=\xffprivate-canary"):
            if contents is None:
                self.groups["production"].unlink()
            else:
                self.groups["production"].write_bytes(contents)
            with self.assertRaises(InputError) as caught:
                self.compare()
            self.assertNotIn("private-canary", str(caught.exception))

    def test_invalid_template_api_values_are_rejected(self):
        for template in (None, "", " ", "\x00private-canary", 3):
            with self.subTest(template=template), self.assertRaises(InputError):
                compare(template, self.groups)

    def test_invalid_groups_paths_and_labels_are_rejected_without_echo(self):
        cases = [
            None,
            [],
            "private-canary",
            {},
            {"dev": "file"},
            {"private-canary!": "file", "prod": "file"},
            {3: "file", "prod": "file"},
            {"dev": [], "prod": "file"},
            {"dev": None, "prod": "file"},
            {"dev": [3], "prod": "file"},
            {"dev": [""], "prod": "file"},
            {"dev": ["\x00private-canary"], "prod": "file"},
        ]
        for groups in cases:
            with self.subTest(groups=groups), self.assertRaises(InputError) as caught:
                compare(self.template, groups)
            self.assertNotIn("private-canary", str(caught.exception))

    def test_invalid_iterables_and_compared_names_are_safe(self):
        cases = [
            ("compare_values", "TOKEN"),
            ("compare_values", None),
            ("compare_values", [3]),
            ("compare_values", ["BAD-private-canary"]),
            ("optional_keys", "TOKEN"),
            ("optional_keys", None),
            ("allow_extra", "TOKEN"),
            ("allow_extra", None),
            ("types", {"TOKEN": "private-canary"}),
        ]
        for name, value in cases:
            with self.subTest(name=name, value=value), self.assertRaises(InputError) as caught:
                self.compare(**{name: value})
            self.assertNotIn("private-canary", str(caught.exception))

    def test_valid_environment_labels_and_compared_names(self):
        self.assertEqual(comparison_keys(["PORT", "DEBUG", "PORT"]), ("DEBUG", "PORT"))
        self.assertEqual(
            environment_paths({"dev-1": self.groups["dev"], "Prod_2": [self.groups["production"]]}),
            {"dev-1": (str(self.groups["dev"]),), "Prod_2": (str(self.groups["production"]),)},
        )

    def test_existing_check_and_parser_metadata_remain_compatible(self):
        for file in self.groups.values():
            self.assertTrue(check(self.template, file).valid)
        entries, issues = parse("TOKEN=private-canary", "input")
        self.assertEqual(set(vars(entries["TOKEN"])), {"key", "line", "empty"})
        self.assertEqual(issues, [])

    def test_external_process_environment_has_no_effect(self):
        with patch.dict(os.environ, {"DEBUG": "private-canary", "PORT": "oops"}):
            self.assertTrue(self.compare().valid)

    def test_url_credentials_and_malformed_urls_never_reach_reports(self):
        self.template.write_text("URL=", encoding="utf-8")
        for index, name in enumerate(self.groups):
            self.write(name, f"URL=https://user:private-canary-{index}@host.invalid/path")
        report = self.compare(types={"URL": "url"})
        self.assertTrue(report.valid)
        for output in ("text", "json", "github"):
            self.assertNotIn("private-canary", render_comparison(report, output))
        self.write("production", "URL=https://user:private-canary@[invalid]/")
        report = self.compare(types={"URL": "url"}, compare_values=["URL"])
        self.assertEqual(
            {issue.code for issue in report.issues}, {"invalid_type", "value_mismatch"}
        )
        self.assertNotIn("private-canary", repr(report))

    def test_quoted_values_comments_bom_and_crlf_preserve_literal_equality(self):
        self.template.write_text("VALUE=", encoding="utf-8")
        self.write("dev", "VALUE=info # comment")
        self.write("staging", "VALUE='info'")
        self.groups["production"].write_bytes(b'\xef\xbb\xbfexport VALUE="info"\r\n')
        self.assertTrue(self.compare(compare_values=["VALUE"]).valid)

    def test_committed_example_and_deliberate_drift(self):
        example = Path(__file__).resolve().parents[1] / "examples/compare/envlatch.json"
        configuration = load_comparison_config(example)
        groups = configuration.environments
        options = dict(
            types=configuration.settings.types,
            compare_values=configuration.compare_values,
            strict=True,
        )
        self.assertTrue(compare(configuration.settings.template, groups, **options).valid)
        groups = {**groups, "production": (str(example.parent / "drift.env"),)}
        report = compare(configuration.settings.template, groups, **options)
        self.assertEqual(
            {issue.code for issue in report.issues},
            {"missing_key", "invalid_type", "value_mismatch"},
        )

    def test_json_has_an_explicit_comparison_kind_and_only_safe_observations(self):
        data = json.loads(render_comparison(self.compare(), "json"))
        self.assertEqual(
            (data["schema_version"], data["kind"], data["status"]), (1, "comparison", "pass")
        )
        self.assertEqual(
            set(data["keys"][0]["observations"][0]),
            {"environment", "state", "types", "path", "line"},
        )

    def test_text_and_github_add_environment_context_and_escape_paths(self):
        self.write("production", "TOKEN=t\nPORT=8000")
        report = self.compare()
        for output in ("text", "github"):
            rendered = render_comparison(report, output)
            self.assertIn("[production]", rendered)
            self.assertIn("FAIL: 3 environment(s)", rendered)
        self.assertIn("production=missing", render_comparison(report, "text"))
        from dataclasses import replace

        issue = replace(report.issues[0], path="C:/a,b%\r\nfile.env", line=3)
        rendered = render_comparison(replace(report, issues=(issue,)), "github")
        self.assertIn("file=C%3A/a%2Cb%25%0D%0Afile.env,line=3", rendered)
        self.assertEqual(rendered.count("::error "), 1)

    def test_github_success_only_has_comparison_summary(self):
        rendered = render_comparison(self.compare(), "github")
        self.assertTrue(rendered.startswith("PASS: 3 environment(s)"))
        self.assertEqual(len(rendered.splitlines()), 1)

    def test_comparison_config_paths_bom_crlf_and_rules(self):
        self.config_write(types={"PORT": "port"}, compare_values=["PORT", "PORT"], strict=True)
        text = self.config.read_text(encoding="utf-8").replace(",", ",\r\n")
        self.config.write_bytes(b"\xef\xbb\xbf" + text.encode())
        config = load_comparison_config(self.config)
        self.assertEqual(config.settings.template, str(self.template))
        self.assertEqual(config.environments["dev"], (str(self.groups["dev"]),))
        self.assertEqual(config.settings.types, {"PORT": "port"})
        self.assertEqual(config.compare_values, ("PORT",))

    def test_sparse_comparison_config_can_be_completed_by_cli(self):
        self.config.write_text('{"strict": true}', encoding="utf-8")
        result = self.cli(
            "--template",
            str(self.template),
            "--env",
            "dev=" + str(self.groups["dev"]),
            "--env",
            "prod=" + str(self.groups["production"]),
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_bad_comparison_config_shapes_and_shared_rules_are_safe(self):
        for changes in (
            {"env": ["private-canary"]},
            {"unknown-private-canary": True},
            {"environments": []},
            {"environments": {"dev": "private-canary"}},
            {"environments": {"dev": []}},
            {"environments": {"bad!": ["file"]}},
            {"compare_values": None},
            {"compare_values": ["BAD-private-canary"]},
            {"strict": "private-canary"},
            {"types": {"TOKEN": "private-canary"}},
        ):
            with self.subTest(changes=changes):
                self.config_write(**changes)
                result = self.cli("--format", "json")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "input_error")
                self.assertNotIn("private-canary", result.stdout + result.stderr)

    def test_duplicate_json_groups_and_malformed_json_are_rejected(self):
        for text in (
            '{"environments":{"dev":["x"],"dev":["y"]}}',
            '{"compare_values":["private-canary",]}',
            "[]",
            '{"strict":NaN}',
        ):
            self.config.write_text(text, encoding="utf-8")
            result = self.cli("--format", "github")
            self.assertEqual(result.returncode, 2)
            self.assertIn("::error ", result.stdout)
            self.assertNotIn("private-canary", result.stdout + result.stderr)

    def test_cli_comparison_all_formats(self):
        self.config_write(types={"TOKEN": "string", "PORT": "port", "DEBUG": "boolean"})
        for output in ("text", "json", "github"):
            with self.subTest(output=output):
                result = self.cli("--format", output)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("private-canary", result.stdout + result.stderr)
                if output == "json":
                    self.assertEqual(json.loads(result.stdout)["kind"], "comparison")
                else:
                    self.assertIn("PASS:", result.stdout)

    def test_cli_named_files_and_repeated_names_form_independent_overlays(self):
        overlay = self.root / "local=overlay.env"
        overlay.write_text("DEBUG=false", encoding="utf-8")
        result = self.cli(
            "--template",
            str(self.template),
            "--env",
            "dev=" + str(self.groups["dev"]),
            "--env",
            "dev=" + str(overlay),
            "--env",
            "prod=" + str(self.groups["production"]),
            "--format",
            "json",
            config=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["environments"][0]["files"],
            [str(self.groups["dev"]), str(overlay)],
        )

    def test_cli_list_overrides_replace_config_and_paths_are_cwd_relative(self):
        self.config_write(
            environments={"missing": ["missing.env"]},
            optional=["TYPO"],
            compare_values=["TOKEN"],
            allow_extra=["UNKNOWN"],
        )
        result = self.cli(
            "--template",
            str(self.template),
            "--env",
            "dev=" + str(self.groups["dev"]),
            "--env",
            "prod=" + str(self.groups["production"]),
            "--optional",
            "DEBUG",
            "--compare-values",
            "PORT",
            "--allow-extra",
            "TOOL_*",
            "--format",
            "json",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cli_strictness_can_be_overridden_both_directions(self):
        for name in self.groups:
            with self.groups[name].open("a", encoding="utf-8") as file:
                file.write("EXTRA=yes")
        self.config_write(strict=True)
        self.assertEqual(self.cli("--no-strict").returncode, 0)
        self.config_write(strict=False)
        self.assertEqual(self.cli("--strict").returncode, 1)

    def test_cli_bad_labels_specs_and_too_few_groups_are_safe_errors(self):
        for specification in ("private-canary", "bad-private-canary!=path", "dev=", "dev=one.env"):
            result = self.cli(
                "--template",
                str(self.template),
                "--env",
                specification,
                "--format",
                "json",
                config=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("private-canary", result.stdout + result.stderr)

    def test_cli_invalid_loaded_config_falls_back_to_text_stderr(self):
        self.config.write_text('{"strict":"private-canary"}', encoding="utf-8")
        result = self.cli()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("ERROR [input_error]", result.stderr)
        self.assertNotIn("private-canary", result.stderr)

    def test_cli_valid_config_selects_structured_input_errors(self):
        self.config_write(format="github", environments={"one": ["one.env"]})
        result = self.cli()
        self.assertEqual(result.returncode, 2)
        self.assertIn("::error ", result.stdout)

    def test_cli_missing_template_is_an_argparse_usage_error(self):
        result = self.cli("--format", "json", config=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("provide --template", result.stderr)

    def test_cli_missing_config_and_unreadable_environment_are_input_errors(self):
        result = self.cli("--format", "json")
        self.assertEqual(result.returncode, 2)
        self.config_write()
        self.groups["production"].unlink()
        result = self.cli("--format", "json")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_cli_value_diff_fails_safely_and_explicit_format_wins(self):
        self.config_write(format="github", compare_values=["TOKEN"])
        result = self.cli("--format", "json")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["issues"][0]["code"], "value_mismatch")
        self.assertNotIn("private-canary", result.stdout)

    def test_cli_version_and_help_do_not_read_configuration(self):
        for option in ("--version", "--help"):
            self.assertEqual(self.cli(option).returncode, 0)

    def test_old_cli_does_not_implicitly_switch_to_comparison_mode(self):
        self.config_write()
        result = subprocess.run(
            [sys.executable, "-m", "envlatch", "--config", str(self.config), "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("kind", json.loads(result.stdout))


if __name__ == "__main__":
    unittest.main()
