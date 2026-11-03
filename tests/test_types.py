"""Opt-in types, effective overlay values, configuration and secret-safe output."""

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from envlatch.cli import render_github, render_json, render_text
from envlatch.config import Config, load_config
from envlatch.core import InputError, _parse, check


class TypeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.template = self.root / "template.env"
        self.environment = self.root / "actual.env"
        self.config = self.root / "envlatch.json"
        self.template.write_text("VALUE=illustrative-only\n", encoding="utf-8")
        self.environment.write_text("VALUE=literal", encoding="utf-8")

    def validate(self, kind, value, **kwargs):
        self.environment.write_text("VALUE=" + value + "\n", encoding="utf-8")
        return check(self.template, self.environment, types={"VALUE": kind}, **kwargs)

    def write_config(self, **changes):
        data = {
            "template": "template.env",
            "env": ["actual.env"],
            "types": {"VALUE": "integer"},
            **changes,
        }
        self.config.write_text(json.dumps(data), encoding="utf-8")

    def cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "envlatch", "--config", str(self.config), *arguments],
            cwd=self.root.parent,
            capture_output=True,
            text=True,
            check=False,
        )

    def assert_invalid(self, kind, values):
        for value in values:
            with self.subTest(kind=kind, value=value):
                report = self.validate(kind, value)
                self.assertEqual(
                    [(i.code, i.key) for i in report.issues], [("invalid_type", "VALUE")]
                )
                self.assertEqual((report.errors, report.checked_keys), (1, 1))

    def assert_valid(self, kind, values):
        for value in values:
            with self.subTest(kind=kind, value=value):
                self.assertTrue(self.validate(kind, value).valid)

    def test_string_accepts_any_nonblank_literal(self):
        self.assert_valid(
            "string",
            [
                "literal",
                "12",
                "false",
                "a b",
                '"  text  "',
                "$OTHER",
                "$(command)",
                "значение",
                "a\u2028b",
            ],
        )

    def test_integer_is_ascii_signed_decimal_without_range_limit(self):
        self.assert_valid("integer", ["0", "-0", "+1", "-42", "001", "9" * 6000])
        self.assert_invalid(
            "integer",
            ["1.0", "1e3", "0x10", "1_000", "１２", "١٢", "+", "--1", '" 42 "', "$VALUE", "true"],
        )

    def test_boolean_uses_true_false_or_one_zero(self):
        self.assert_valid("boolean", ["true", "false", "TRUE", "False", "tRuE", "1", "0"])
        self.assert_invalid(
            "boolean", ["yes", "no", "on", "off", "2", "-1", "01", '" true "', "ＴＲＵＥ"]
        )

    def test_port_boundaries_and_leading_zeroes(self):
        self.assert_valid("port", ["1", "65535", "080", "0" * 6000 + "80"])
        self.assert_invalid(
            "port", ["0", "000", "65536", "-1", "+80", "1.0", "1e3", "８０", '" 80 "', "9" * 6000]
        )

    def test_url_supports_network_schemes_hosts_and_credentials(self):
        self.assert_valid(
            "url",
            [
                "https://example.invalid/path?q=1#section",
                "HTTP://localhost",
                "postgresql://user:password@localhost:5432/db",
                "redis://127.0.0.1:6379/0",
                "ws://[::1]:8000/socket",
                "https://example.invalid./",
                "custom+v1://service-name/path",
                "https://пример.рф/path",
                "https://host/a%20b",
                "https://user:p%40ss@host",
                "https://[2001:db8::1]/",
            ],
        )

    def test_url_rejects_missing_authority_bad_hosts_and_ports(self):
        self.assert_invalid(
            "url",
            [
                "example.invalid",
                "//host/path",
                "/path",
                "https:///path",
                "mailto:user@example.invalid",
                "file:///tmp/file",
                "https://",
                "https://user@",
                "1bad://host",
                "https://host:",
                "https://host:0",
                "https://host:65536",
                "https://host:+80",
                "https://host:abc",
                "https://[::1",
                "https://[::1]suffix",
                "https://[v1.host]",
                "https://::1",
                "https://[bad]",
                "https://[::1]:",
                "https://a@b@host",
                "https://bad_host",
                "https://-host",
                "https://host..invalid",
                "https://999.1.2.3",
                "https://host/" + "%zz",
                "https://host/%",
                "https://host/" + chr(127),
                "https://host/with space",
                '"https://host/with\ttab"',
                "https://host\\path",
                "https://host/<tag>",
                "https://host:999999999999999999999999",
                "https://host/" + chr(128),
                "https://[bad]@host",
                "https://host/" + chr(1),
            ],
        )

    def test_quotes_comments_bom_crlf_and_export_precede_type_checking(self):
        self.environment.write_bytes(b'\xef\xbb\xbfexport VALUE = "42" # comment\r\n')
        self.assertTrue(check(self.template, self.environment, types={"VALUE": "integer"}).valid)
        self.assert_valid("integer", ["'42'", " 42 # comment", '"42"#comment'])
        self.assert_invalid("integer", ["42#not-a-comment", '"42 # literal"'])

    def test_escaped_and_referenced_values_are_not_expanded(self):
        self.assert_invalid("integer", [r'"\x34\x32"', "${VALUE}", "$(echo 42)"])

    def test_required_blanks_have_only_the_existing_empty_diagnostic(self):
        for kind in ("string", "integer", "boolean", "url", "port"):
            for value in ("", "   ", "''", '"  "', "# comment"):
                with self.subTest(kind=kind, value=value):
                    report = self.validate(kind, value)
                    self.assertEqual([i.code for i in report.issues], ["empty_value"])

    def test_missing_required_value_has_no_duplicate_type_error(self):
        self.environment.write_text("", encoding="utf-8")
        report = check(self.template, self.environment, types={"VALUE": "port"})
        self.assertEqual([i.code for i in report.issues], ["missing_key"])

    def test_optional_missing_or_blank_pass_but_nonblank_is_checked(self):
        for value in ("", "''", '"  "'):
            self.assertTrue(self.validate("port", value, optional_keys=["VALUE"]).valid)
        self.environment.write_text("", encoding="utf-8")
        self.assertTrue(
            check(
                self.template, self.environment, types={"VALUE": "port"}, optional_keys=["VALUE"]
            ).valid
        )
        report = self.validate("port", "bad", optional_keys=["VALUE"])
        self.assertEqual((report.errors, report.checked_keys), (1, 0))
        self.assertEqual(report.issues[0].code, "invalid_type")

    def test_type_checks_only_effective_overlay_value_with_winning_location(self):
        overlay = self.root / "overlay.env"
        for base, local, valid in [("bad", "80", True), ("80", "bad", False)]:
            with self.subTest(base=base):
                self.environment.write_text("VALUE=" + base, encoding="utf-8")
                overlay.write_text("# overlay\nVALUE=" + local, encoding="utf-8")
                report = check(self.template, [self.environment, overlay], types={"VALUE": "port"})
                self.assertEqual(report.valid, valid)
                if not valid:
                    self.assertEqual(
                        (report.issues[0].path, report.issues[0].line), (str(overlay), 2)
                    )

    def test_empty_overlay_preserves_required_and_optional_behavior(self):
        overlay = self.root / "overlay.env"
        overlay.write_text("VALUE=", encoding="utf-8")
        self.environment.write_text("VALUE=80", encoding="utf-8")
        args = (self.template, [self.environment, overlay])
        report = check(*args, types={"VALUE": "port"})
        self.assertEqual([i.code for i in report.issues], ["empty_value"])
        self.assertTrue(check(*args, types={"VALUE": "port"}, optional_keys=["VALUE"]).valid)

    def test_template_values_are_not_type_checked_or_used_as_defaults(self):
        self.assertTrue(self.validate("port", "80").valid)

    def test_untyped_values_and_v050_settings_keep_original_behavior(self):
        self.environment.write_text("VALUE=not-a-port", encoding="utf-8")
        baseline = check(self.template, self.environment)
        self.assertTrue(baseline.valid)
        self.assertEqual(baseline, check(self.template, self.environment, types={}))
        self.assertEqual(baseline, check(self.template, self.environment, types=None))
        self.write_config(types={})
        self.assertEqual(self.cli().returncode, 0)
        data = json.loads(self.config.read_text(encoding="utf-8"))
        del data["types"]
        self.config.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.cli().returncode, 0)

    def test_unknown_typed_key_is_case_sensitive_template_error(self):
        for name in ("TYPO", "value"):
            with self.subTest(name=name):
                report = check(self.template, self.environment, types={name: "integer"})
                self.assertEqual([i.code for i in report.issues], ["unknown_type_key"])
                self.assertEqual(
                    (report.issues[0].path, report.issues[0].key), (str(self.template), name)
                )

    def test_extra_allowance_does_not_declare_typed_keys_or_skip_types(self):
        self.environment.write_text("VALUE=bad\nEXTRA=bad", encoding="utf-8")
        report = check(
            self.template,
            self.environment,
            strict=True,
            allow_extra=["*"],
            types={"VALUE": "port", "EXTRA": "port"},
        )
        self.assertEqual([i.code for i in report.issues], ["unknown_type_key", "invalid_type"])

    def test_duplicate_and_syntax_errors_survive_overlay(self):
        overlay = self.root / "overlay.env"
        overlay.write_text("VALUE=80", encoding="utf-8")
        for text, code in [
            ("VALUE=bad\nVALUE=80", "duplicate_key"),
            ('VALUE="private-canary\nFRAGMENT_CANARY=80', "invalid_value"),
        ]:
            with self.subTest(code=code):
                self.environment.write_text(text, encoding="utf-8")
                report = check(self.template, [self.environment, overlay], types={"VALUE": "port"})
                self.assertEqual([i.code for i in report.issues], [code])
                self.assertNotIn("FRAGMENT_CANARY", repr(report))

    def test_broken_template_suppresses_contract_and_type_diagnostics(self):
        self.template.write_text('VALUE="unterminated', encoding="utf-8")
        report = check(self.template, self.environment, types={"VALUE": "port", "TYPO": "integer"})
        self.assertEqual([i.code for i in report.issues], ["invalid_value"])

    def test_invalid_api_rules_are_safe_input_errors_before_file_reads(self):
        bad = [
            "private-canary",
            [],
            [("VALUE", "port")],
            1,
            True,
            {"BAD-private-canary": "integer"},
            {"": "port"},
            {1: "port"},
            {"VALUE": "private-canary"},
            {"VALUE": "URL"},
            {"VALUE": None},
            {"VALUE": []},
            {"VALUE": {}},
        ]
        for rules in bad:
            with self.subTest(rules=rules):
                with self.assertRaises(InputError) as caught:
                    check("missing.env", "missing.env", types=rules)
                self.assertNotIn("private-canary", str(caught.exception))

    def test_parsed_entries_store_only_safe_metadata(self):
        for kind, value in [
            ("string", "private-canary"),
            ("integer", "private-canary"),
            ("url", "https://user:private-canary@host/db"),
        ]:
            with self.subTest(kind=kind):
                entries, issues, invalid = _parse("VALUE=" + value, "input.env", {"VALUE": kind})
                self.assertNotIn("private-canary", repr(entries) + repr(issues) + repr(invalid))
                self.assertEqual(set(asdict(entries["VALUE"])), {"key", "line", "empty"})

    def test_all_renderers_hide_values_and_raw_url_exception_messages(self):
        for kind, value in [
            ("integer", "private-canary"),
            ("boolean", "private-canary"),
            ("port", "private-canary"),
            ("url", "https://user:private-canary@[broken]:oops/path"),
        ]:
            with self.subTest(kind=kind):
                report = self.validate(kind, value)
                for render in (repr, render_text, render_json, render_github):
                    output = render(report)
                    self.assertNotIn("private-canary", output)
                    self.assertNotIn("[broken]", output)
                    self.assertIn("invalid_type", output)
                self.assertEqual(json.loads(render_json(report))["schema_version"], 1)

    def test_valid_type_config_is_loaded_without_mutating_input(self):
        self.write_config()
        self.assertEqual(load_config(self.config).types, {"VALUE": "integer"})
        self.assertEqual(Config().types, {})
        original = {"VALUE": "string"}
        self.assertTrue(check(self.template, self.environment, types=original).valid)
        self.assertEqual(original, {"VALUE": "string"})

    def test_invalid_json_type_rules_are_rejected_without_echo(self):
        for rules in (
            None,
            [],
            "private-canary",
            True,
            1,
            {"VALUE": "private-canary"},
            {"BAD-private-canary": "port"},
            {"VALUE": ["port"]},
            {"VALUE": {}},
        ):
            with self.subTest(rules=rules):
                self.write_config(types=rules)
                with self.assertRaises(InputError) as caught:
                    load_config(self.config)
                self.assertNotIn("private-canary", str(caught.exception))
                result = self.cli("--format", "json")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "input_error")
                self.assertNotIn("private-canary", result.stdout + result.stderr)

    def test_duplicate_nested_type_rules_are_rejected(self):
        self.config.write_text('{"types":{"VALUE":"port","VALUE":"integer"}}', encoding="utf-8")
        with self.assertRaises(InputError):
            load_config(self.config)

    def test_cli_type_failures_and_success_in_all_formats(self):
        self.write_config()
        for output in ("text", "json", "github"):
            with self.subTest(output=output):
                self.environment.write_text("VALUE=private-canary", encoding="utf-8")
                result = self.cli("--format", output)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertIn("invalid_type", result.stdout)
                self.assertNotIn("private-canary", result.stdout)
                if output == "json":
                    issue = json.loads(result.stdout)["issues"][0]
                    self.assertEqual(
                        (issue["key"], issue["line"], issue["path"]),
                        ("VALUE", 1, str(self.environment)),
                    )
                self.environment.write_text("VALUE=42", encoding="utf-8")
                self.assertEqual(self.cli("--format", output).returncode, 0)

    def test_cli_path_overrides_keep_type_policy(self):
        self.write_config(template="missing.env", env=["missing.env"])
        result = self.cli(
            "--template", str(self.template), "--env", str(self.environment), "--format", "json"
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["issues"][0]["code"], "invalid_type")

    def test_cli_unknown_typed_key_is_validation_error(self):
        self.write_config(types={"TYPO": "string"})
        result = self.cli("--format", "json")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["issues"][0]["code"], "unknown_type_key")

    def test_unlisted_overlay_keys_do_not_clear_type_failures(self):
        self.environment.write_text("VALUE=bad", encoding="utf-8")
        overlay = self.root / "overlay.env"
        overlay.write_text("EXTRA=ok", encoding="utf-8")
        report = check(
            self.template,
            [self.environment, overlay],
            types={"VALUE": "port"},
            allow_extra=["EXTRA"],
        )
        self.assertEqual(
            [(i.code, i.path) for i in report.issues], [("invalid_type", str(self.environment))]
        )

    def test_multiple_rules_have_deterministic_order_and_required_count(self):
        self.template.write_text("PORT=\nDEBUG=\nLABEL=\n", encoding="utf-8")
        self.environment.write_text("PORT=bad\nDEBUG=bad\nLABEL=text", encoding="utf-8")
        report = check(
            self.template,
            self.environment,
            types={"PORT": "port", "LABEL": "string", "DEBUG": "boolean"},
        )
        self.assertEqual([(i.key, i.line) for i in report.issues], [("DEBUG", 2), ("PORT", 1)])
        self.assertEqual((report.checked_keys, report.errors), (3, 2))


if __name__ == "__main__":
    unittest.main()
