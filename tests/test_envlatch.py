"""Behavioral tests of dotenv grammar, contract rules and safe CLI diagnostics."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from envlatch.core import InputError, check, parse
from envlatch.cli import render_text


class ParserTests(unittest.TestCase):
    def test_supported_dotenv_syntax(self):
        text = '\ufeff# contract\r\n export FIRST = one # comment\r\nSECOND="two # literal"\r\nTHIRD=\'three\'\r\nFOURTH=some#literal\r\nDOLLAR=${LITERAL}\r\n'
        entries, issues = parse(text, "example.env")
        self.assertEqual(issues, [])
        self.assertEqual(list(entries), ["FIRST", "SECOND", "THIRD", "FOURTH", "DOLLAR"])
        self.assertTrue(all(not entry.empty for entry in entries.values()))
        self.assertEqual(entries["FIRST"].line, 2)

    def test_blank_forms(self):
        for value in ["", "   ", "# comment", "''", '""', "'  '", '" \t " # comment']:
            with self.subTest(value=value):
                entries, issues = parse("KEY=" + value, "input")
                self.assertEqual(issues, [])
                self.assertTrue(entries["KEY"].empty)

    def test_hash_inside_quotes_is_a_value(self):
        for value in ['"#"', "'#'", '"x"#comment', "x#literal"]:
            with self.subTest(value=value):
                entries, issues = parse("KEY=" + value, "input")
                self.assertEqual(issues, [])
                self.assertFalse(entries["KEY"].empty)

    def test_escaped_double_quote(self):
        entries, issues = parse(r'KEY="a\"b" # comment', "input")
        self.assertEqual(issues, [])
        self.assertFalse(entries["KEY"].empty)

    def test_double_backslash_before_closing_quote(self):
        entries, issues = parse('KEY="two\\\\"', "input")
        self.assertEqual(issues, [])
        self.assertFalse(entries["KEY"].empty)

    def test_values_are_discarded(self):
        entries, issues = parse("TOKEN=unique-secret-canary", "input")
        self.assertNotIn("unique-secret-canary", repr(entries) + repr(issues))
        self.assertEqual(set(vars(entries["TOKEN"])), {"key", "line", "empty"})

    def test_duplicates_report_both_line_numbers(self):
        entries, issues = parse("KEY=first-secret\nKEY=second-secret", "input")
        self.assertEqual(entries["KEY"].line, 1)
        self.assertEqual(len(issues), 1)
        self.assertEqual((issues[0].code, issues[0].line), ("duplicate_key", 2))
        self.assertIn("line 1", issues[0].message)
        self.assertNotIn("secret", repr(issues))

    def test_invalid_lines_never_echo_source(self):
        cases = ["private-secret", "private-secret-x=value", "KEY='private-secret", 'KEY="private-secret"tail', "KEY=private-secret\x00"]
        for text in cases:
            with self.subTest(text=text):
                _, issues = parse(text, "input")
                self.assertTrue(issues)
                self.assertNotIn("private-secret", repr(issues))
                self.assertEqual(issues[0].line, 1)

    def test_multiline_values_are_rejected(self):
        entries, issues = parse('KEY="first\nsecond"', "input")
        self.assertNotIn("KEY", entries)
        self.assertEqual(issues[0].code, "invalid_value")
        self.assertEqual(issues[0].line, 1)

    def test_multiline_fragments_are_never_reported_as_key_names(self):
        entries, issues = parse('KEY="first\nPRIVATE_CANARY=secret\nlast"', "input")
        self.assertEqual(entries, {})
        self.assertEqual(len(issues), 1)
        self.assertNotIn("PRIVATE_CANARY", repr(issues))

    def test_invalid_keys(self):
        for key in ["1KEY", "BAD-KEY", "BAD.KEY", "BAD KEY", "КЛЮЧ", ""]:
            with self.subTest(key=key):
                entries, issues = parse(key + "=hidden", "input")
                self.assertEqual(entries, {})
                self.assertEqual(issues[0].code, "invalid_key")

    def test_export_prefix_requires_whitespace(self):
        entries, issues = parse("exported=yes\nexport\tVALID=yes", "input")
        self.assertEqual(issues, [])
        self.assertEqual(set(entries), {"exported", "VALID"})

    def test_only_physical_newlines_split_values(self):
        entries, issues = parse("KEY=a\u2028b\nNEXT=yes", "input")
        self.assertEqual(issues, [])
        self.assertEqual(entries["NEXT"].line, 2)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.template = Path(self.directory.name) / "template.env"
        self.environment = Path(self.directory.name) / "actual.env"

    def validate(self, template, environment, **kwargs):
        self.template.write_text(template, encoding="utf-8")
        self.environment.write_text(environment, encoding="utf-8")
        return check(self.template, self.environment, **kwargs)

    def test_all_template_keys_are_required_including_blank_placeholders(self):
        report = self.validate("HOST=example\nTOKEN=", "HOST=localhost\nTOKEN=actual")
        self.assertTrue(report.valid)
        self.assertEqual(report.checked_keys, 2)

    def test_missing_and_empty_keys(self):
        report = self.validate("Z=\nA=\nB=", "B= \nZ=ok")
        self.assertFalse(report.valid)
        self.assertEqual([(issue.code, issue.key, issue.line) for issue in report.issues],
                         [("missing_key", "A", None), ("empty_value", "B", 1)])

    def test_extras_warn_by_default_and_fail_when_strict(self):
        report = self.validate("A=", "A=ok\nEXTRA=secret")
        self.assertTrue(report.valid)
        self.assertEqual((report.errors, report.warnings), (0, 1))
        strict_report = check(self.template, self.environment, strict=True)
        self.assertFalse(strict_report.valid)
        self.assertEqual((strict_report.errors, strict_report.warnings), (1, 0))

    def test_duplicate_template_disables_contract_comparison(self):
        report = self.validate("A=\nA=", "OTHER=ok")
        self.assertEqual([issue.code for issue in report.issues], ["duplicate_key"])

    def test_duplicate_environment_is_an_error(self):
        report = self.validate("A=", "A=one\nA=two")
        self.assertEqual(report.errors, 1)
        self.assertEqual(report.issues[0].code, "duplicate_key")

    def test_missing_file_has_safe_input_error(self):
        with self.assertRaises(InputError):
            check(self.template, self.environment)

    def test_non_utf8_file_has_safe_input_error(self):
        self.template.write_text("A=", encoding="utf-8")
        self.environment.write_bytes(b"A=\xffunique-secret")
        with self.assertRaises(InputError) as caught:
            check(self.template, self.environment)
        self.assertNotIn("unique-secret", str(caught.exception))

    def test_bom_crlf_files(self):
        self.template.write_bytes(b"\xef\xbb\xbfA=\r\nB=\r\n")
        self.environment.write_bytes(b"\xef\xbb\xbfA=one\r\nB=two\r\n")
        self.assertTrue(check(self.template, self.environment).valid)

    def test_no_interpolation_or_process_environment_fallback(self):
        previous = os.environ.get("ENVLATCH_TEST_KEY")
        os.environ["ENVLATCH_TEST_KEY"] = "process-secret"
        try:
            report = self.validate("ENVLATCH_TEST_KEY=", "")
            self.assertEqual(report.issues[0].code, "missing_key")
            literal_report = self.validate("A=", "A=${UNDEFINED}")
            self.assertTrue(literal_report.valid)
        finally:
            if previous is None:
                os.environ.pop("ENVLATCH_TEST_KEY", None)
            else:
                os.environ["ENVLATCH_TEST_KEY"] = previous

    def test_rendering_is_deterministic_and_value_free(self):
        report = self.validate("Z=template-secret\nA=", "Z=actual-secret\nEXTRA=extra-secret")
        rendered = render_text(report)
        self.assertEqual(rendered, render_text(report))
        for secret in ["template-secret", "actual-secret", "extra-secret"]:
            self.assertNotIn(secret, rendered)
        self.assertIn("FAIL: 2 required key(s), 1 error(s), 1 warning(s).", rendered)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.template = Path(self.directory.name) / "template.env"
        self.environment = Path(self.directory.name) / "actual.env"
        self.template.write_text("TOKEN=", encoding="utf-8")
        self.environment.write_text("TOKEN=unique-private-canary", encoding="utf-8")

    def run_cli(self, *arguments):
        return subprocess.run([sys.executable, "-m", "envlatch", *arguments],
                              capture_output=True, text=True, check=False)

    def args(self):
        return ["--template", str(self.template), "--env", str(self.environment)]

    def test_success(self):
        result = self.run_cli(*self.args())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS", result.stdout)
        self.assertEqual(result.stderr, "")
        self.assertNotIn("unique-private-canary", result.stdout + result.stderr)

    def test_validation_failure(self):
        self.environment.write_text("TOKEN=\nEXTRA=unique-private-canary", encoding="utf-8")
        result = self.run_cli(*self.args())
        self.assertEqual(result.returncode, 1)
        self.assertIn("empty_value", result.stdout)
        self.assertNotIn("unique-private-canary", result.stdout + result.stderr)

    def test_warning_and_strict_exit_codes(self):
        self.environment.write_text("TOKEN=ok\nEXTRA=private", encoding="utf-8")
        self.assertEqual(self.run_cli(*self.args()).returncode, 0)
        self.assertEqual(self.run_cli(*self.args(), "--strict").returncode, 1)

    def test_input_error(self):
        self.environment.unlink()
        result = self.run_cli(*self.args())
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("input_error", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_usage_error(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr)

    def json_result(self, *arguments):
        result = self.run_cli(*self.args(), "--format", "json", *arguments)
        self.assertEqual(result.stderr, "")
        document = json.loads(result.stdout)
        self.assertEqual(document["schema_version"], 1)
        self.assertEqual(document["template"], str(self.template))
        self.assertEqual(document["environments"], [str(self.environment)])
        self.assertEqual(set(document), {"schema_version", "status", "template", "environments",
                                         "checked_keys", "errors", "warnings", "issues"})
        self.assertNotIn("unique-private-canary", result.stdout)
        return result, document

    def test_json_success_and_roundtrip(self):
        result, document = self.json_result()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(document["status"], "pass")
        self.assertEqual(document["checked_keys"], 1)
        self.assertEqual(document["issues"], [])
        self.assertEqual(document, json.loads(json.dumps(document)))
        self.assertEqual(result.stdout, self.run_cli(*self.args(), "--format", "json").stdout)

    def test_json_violation_and_safe_issue_fields(self):
        self.environment.write_text("OTHER=unique-private-canary", encoding="utf-8")
        result, document = self.json_result()
        self.assertEqual(result.returncode, 1)
        self.assertEqual((document["status"], document["errors"], document["warnings"]), ("fail", 1, 1))
        issue = document["issues"][0]
        self.assertEqual(set(issue), {"severity", "code", "path", "message", "line", "key"})
        self.assertEqual((issue["code"], issue["key"], issue["line"]), ("missing_key", "TOKEN", None))

    def test_json_warning_and_strict(self):
        self.environment.write_text("TOKEN=ok\nEXTRA=unique-private-canary", encoding="utf-8")
        result, document = self.json_result()
        self.assertEqual(result.returncode, 0)
        self.assertEqual((document["status"], document["warnings"]), ("pass", 1))
        result, document = self.json_result("--strict")
        self.assertEqual(result.returncode, 1)
        self.assertEqual((document["status"], document["errors"], document["warnings"]), ("fail", 1, 0))

    def test_json_input_errors_have_same_schema(self):
        for invalid_utf8 in (False, True):
            with self.subTest(invalid_utf8=invalid_utf8):
                if invalid_utf8:
                    self.environment.write_bytes(b"TOKEN=\xffunique-private-canary")
                else:
                    self.environment.unlink()
                result, document = self.json_result()
                self.assertEqual(result.returncode, 2)
                self.assertEqual((document["status"], document["checked_keys"], document["errors"],
                                  document["warnings"]), ("input_error", 0, 1, 0))
                issue = document["issues"][0]
                self.assertEqual((issue["severity"], issue["code"]), ("error", "input_error"))
                self.assertIsNone(issue["path"])
                self.assertIsNone(issue["line"])
                self.assertIsNone(issue["key"])

    def test_json_invalid_format_is_usage_error(self):
        result = self.run_cli(*self.args(), "--format", "xml")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("invalid choice", result.stderr)

    def test_version(self):
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0)
        self.assertIn("EnvLatch 0.1.0", result.stdout)


if __name__ == "__main__":
    unittest.main()
