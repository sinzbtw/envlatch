import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from envlatch import check, compare
from envlatch.config import load_config
from envlatch.core import InputError


class ConstraintTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.template = self.write("template.env", "SETTING=ignored-template-value\n")

    def write(self, name, text):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def validate(self, literal, rule, **kwargs):
        environment = self.write("input.env", f"SETTING={literal}\n")
        return check(self.template, environment, constraints={"SETTING": rule}, **kwargs)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "envlatch", *map(str, args)],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def test_choices_match_the_literal_and_keep_case(self):
        rule = {"one_of": ["info", "λ", " with spaces ", "$SETTING", "x#y"]}
        for literal in ("'info' # comment", "λ", '" with spaces "', "$SETTING", "x#y"):
            with self.subTest(literal=literal):
                self.assertTrue(self.validate(literal, rule).valid)
        self.assertEqual(self.validate("INFO", rule).issues[0].code, "invalid_constraint")

    def test_integer_syntax_and_inclusive_one_or_two_sided_bounds(self):
        cases = (
            ("-002", {"min": -2, "max": 0}, True),
            ("-000", {"min": 0, "max": 0}, True),
            ("+001", {"max": 1}, True),
            ("-3", {"min": -2}, False),
            ("2", {"max": 1}, False),
            ("1.0", {"min": 0}, False),
            ("1e2", {"min": 0}, False),
            ("١", {"min": 0}, False),
            ("' 1 '", {"min": 0}, False),
            ("0" * 6000 + "7", {"min": 7, "max": 7}, True),
            ("9" * 6000, {"min": 0, "max": 9}, False),
            ("-" + "9" * 6000, {"max": 0}, True),
        )
        for index, (literal, rule, valid) in enumerate(cases):
            with self.subTest(case=index):
                report = self.validate(literal, rule)
                self.assertEqual(report.valid, valid)

    def test_combined_rules_and_existing_type_diagnostic(self):
        rule = {"one_of": ["80", "8080"], "min": 1024}
        types = {"SETTING": "port"}
        self.assertTrue(self.validate("8080", rule, types=types).valid)
        for literal, code in (
            ("80", "invalid_constraint"),
            ("9090", "invalid_constraint"),
            ("not-a-port", "invalid_type"),
        ):
            with self.subTest(literal=literal):
                report = self.validate(literal, rule, types=types)
                self.assertEqual([issue.code for issue in report.issues], [code])

    def test_overlay_replaces_failures_and_reports_the_winning_file(self):
        invalid = self.write("invalid.env", "# comment\nSETTING=private-input\n")
        valid = self.write("valid.env", "SETTING=info\n")
        unrelated = self.write("unrelated.env", "EXTRA=permitted\n")
        rules = {"SETTING": {"one_of": ["info", "private-config-choice"]}}
        self.assertTrue(check(self.template, [invalid, valid], constraints=rules).valid)
        report = check(
            self.template, [valid, invalid, unrelated], constraints=rules, allow_extra=["EXTRA"]
        )
        issue = report.issues[0]
        self.assertEqual(
            (issue.code, issue.key, issue.path, issue.line),
            ("invalid_constraint", "SETTING", str(invalid), 2),
        )
        self.assertNotIn("private-input", repr(report))
        self.assertNotIn("private-config-choice", repr(report))

    def test_missing_and_blank_values_use_existing_required_rules(self):
        invalid = self.write("invalid.env", "SETTING=no\n")
        blank = self.write("blank.env", "SETTING=' '\n")
        missing = self.write("missing.env", "# No setting.\n")
        rules = {"SETTING": {"one_of": ["yes"]}}
        for files, code in (([invalid, blank], "empty_value"), ([missing], "missing_key")):
            with self.subTest(code=code):
                report = check(self.template, files, constraints=rules)
                self.assertEqual([issue.code for issue in report.issues], [code])
                optional = check(self.template, files, constraints=rules, optional_keys=["SETTING"])
                self.assertTrue(optional.valid)

    def test_rules_only_apply_to_keys_in_a_valid_template(self):
        env = self.write("input.env", "SETTING=info\nEXTRA=no\n")
        rules = {"EXTRA": {"one_of": ["yes"]}}
        report = check(self.template, env, constraints=rules, allow_extra=["EXTRA"])
        self.assertEqual([issue.code for issue in report.issues], ["unknown_constraint_key"])
        self.assertEqual(report.issues[0].path, str(self.template))
        broken = self.write("broken.env", "missing-equals\n")
        report = check(broken, env, constraints=rules)
        self.assertEqual([issue.code for issue in report.issues], ["invalid_syntax"])

    def test_invalid_rules_never_echo_config_contents(self):
        for constraints in (
            "private-rule",
            {"private-name!": {"min": 0}},
            {"SETTING": []},
            {"SETTING": {}},
            {"SETTING": {"private-option": "private-choice"}},
            {"SETTING": {"one_of": "private-choice"}},
            {"SETTING": {"one_of": b"private-choice"}},
            {"SETTING": {"one_of": []}},
            {"SETTING": {"one_of": [42]}},
            {"SETTING": {"one_of": ["  "]}},
            {"SETTING": {"one_of": ["private-choice\nnext"]}},
            {"SETTING": {"one_of": ["private-choice\rnext"]}},
            {"SETTING": {"one_of": ["private-choice\x00"]}},
            {"SETTING": {"one_of": ["private-choice\ud800"]}},
            {"SETTING": {"min": True}},
            {"SETTING": {"max": 1.5}},
            {"SETTING": {"min": None}},
            {"SETTING": {"min": 2, "max": 1}},
        ):
            with self.subTest(constraints=constraints):
                with self.assertRaises(InputError) as caught:
                    check(self.template, self.root / "nonexistent.env", constraints=constraints)
                self.assertNotIn("private-", str(caught.exception))
                self.assertNotIn("Cannot read", str(caught.exception))

    def test_comparison_applies_rules_per_group_with_overlay(self):
        base = self.write("base.env", "SETTING=private-input\n")
        local = self.write("local.env", "SETTING=info\n")
        report = compare(
            self.template,
            {"dev": [base, local], "production": base},
            constraints={"SETTING": {"one_of": ("info", "private-config-choice")}},
        )
        self.assertEqual(
            [(issue.environment, issue.code, issue.path, issue.line) for issue in report.issues],
            [("production", "invalid_constraint", str(base), 1)],
        )
        self.assertNotIn("private-", repr(report))

    def test_config_and_both_cli_modes_keep_values_and_rules_out_of_output(self):
        self.write("production.env", "SETTING=62091735\n")
        self.write("dev.env", "SETTING=5\n")
        settings = {
            "template": self.template.name,
            "constraints": {"SETTING": {"one_of": ["5", "private-config-choice"], "max": 739105}},
        }
        for compare_mode, files in (
            (False, {"env": ["production.env"]}),
            (True, {"environments": {"dev": ["dev.env"], "production": ["production.env"]}}),
        ):
            config = self.write("config.json", json.dumps({**settings, **files}))
            command = ("compare",) if compare_mode else ()
            for output_format in ("text", "json", "github"):
                with self.subTest(compare_mode=compare_mode, output_format=output_format):
                    result = self.cli(*command, "--config", config, "--format", output_format)
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertIn("invalid_constraint", result.stdout)
                    self.assertIn("production.env", result.stdout)
                    for private in ("62091735", "private-config-choice", "739105"):
                        self.assertNotIn(private, result.stdout + result.stderr)
                    if output_format == "json":
                        data = json.loads(result.stdout)
                        self.assertEqual(data["schema_version"], 1)
                        if compare_mode:
                            self.assertEqual(data["issues"][0]["environment"], "production")
            if not compare_mode:
                self.assertNotIn("private-config-choice", repr(load_config(config)))
                override = self.cli("--config", config, "--env", "dev.env")
                self.assertEqual(override.returncode, 0, override.stdout + override.stderr)

    def test_null_constraints_in_json_are_an_input_error(self):
        config = self.write("config.json", '{"constraints": null}')
        for command in ((), ("compare",)):
            result = self.cli(*command, "--config", config, "--format", "json")
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "input_error")
