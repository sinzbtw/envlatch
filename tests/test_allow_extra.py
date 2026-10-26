"""Controlled extra-key allowances must never bypass the dotenv contract."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from envlatch.core import InputError, check


class ExtraKeyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.template = self.root / 'contract.env'
        self.environment = self.root / 'actual.env'
        self.template.write_text('HOST=\nTOKEN=\n', encoding='utf-8')
        self.environment.write_text('HOST=localhost\nTOKEN=secret-canary\nCI_JOB=42\nDEBUG=yes', encoding='utf-8')

    def validate(self, patterns=(), **kwargs):
        return check(self.template, self.environment, allow_extra=patterns, **kwargs)

    def cli(self, *arguments):
        return subprocess.run([sys.executable, '-m', 'envlatch', '--template', str(self.template),
                               '--env', str(self.environment), *arguments],
                              capture_output=True, text=True, check=False)

    def test_default_still_rejects_extras_in_strict_mode(self):
        report = self.validate(strict=True)
        self.assertEqual(report.errors, 2)
        self.assertEqual([issue.key for issue in report.issues], ['CI_JOB', 'DEBUG'])

    def test_exact_and_wildcard_allowances_pass_strict_mode(self):
        report = self.validate(['CI_*', 'DEBUG'], strict=True)
        self.assertTrue(report.valid)
        self.assertEqual(report.issues, ())
        self.assertEqual(report.checked_keys, 2)
        self.assertNotIn('secret-canary', repr(report))

    def test_allowed_extras_do_not_produce_default_warnings(self):
        report = self.validate(['CI_*'])
        self.assertTrue(report.valid)
        self.assertEqual(report.warnings, 1)
        self.assertEqual(report.issues[0].key, 'DEBUG')

    def test_pattern_matching_is_case_sensitive_on_every_platform(self):
        report = self.validate(['ci_*', 'DEBUG'], strict=True)
        self.assertEqual(report.errors, 1)
        self.assertEqual(report.issues[0].key, 'CI_JOB')

    def test_question_mark_matches_one_character_only(self):
        self.environment.write_text('HOST=h\nTOKEN=t\nX_1=a\nX_12=b', encoding='utf-8')
        report = self.validate(['X_?'], strict=True)
        self.assertEqual([issue.key for issue in report.issues], ['X_12'])

    def test_star_does_not_disable_required_keys(self):
        self.environment.write_text('CI_JOB=secret-canary', encoding='utf-8')
        report = self.validate(['*'], strict=True)
        self.assertFalse(report.valid)
        self.assertEqual([(i.code, i.key) for i in report.issues],
                         [('missing_key', 'HOST'), ('missing_key', 'TOKEN')])
        self.assertEqual(report.checked_keys, 2)

    def test_exact_allowance_does_not_make_declared_key_optional(self):
        self.environment.write_text('HOST=h', encoding='utf-8')
        report = self.validate(['TOKEN'], strict=True)
        self.assertEqual([(i.code, i.key) for i in report.issues], [('missing_key', 'TOKEN')])

    def test_blank_required_value_still_fails(self):
        self.environment.write_text('HOST=h\nTOKEN=\nCI_JOB=42', encoding='utf-8')
        report = self.validate(['*'], strict=True)
        self.assertEqual([(i.code, i.key) for i in report.issues], [('empty_value', 'TOKEN')])

    def test_duplicate_allowed_key_is_still_an_error(self):
        self.environment.write_text('HOST=h\nTOKEN=t\nCI_JOB=one\nCI_JOB=two', encoding='utf-8')
        report = self.validate(['CI_*'], strict=True)
        self.assertEqual([i.code for i in report.issues], ['duplicate_key'])

    def test_malformed_allowed_value_is_still_an_error(self):
        self.environment.write_text('HOST=h\nTOKEN=t\nCI_JOB="secret-canary', encoding='utf-8')
        report = self.validate(['CI_*'], strict=True)
        self.assertEqual([i.code for i in report.issues], ['invalid_value'])
        self.assertNotIn('secret-canary', repr(report))

    def test_unknown_optional_configuration_is_not_bypassed(self):
        report = self.validate(['*'], optional_keys=['TYPO'], strict=True)
        self.assertEqual([i.code for i in report.issues], ['unknown_optional_key'])

    def test_overlay_provenance_for_remaining_extras_is_preserved(self):
        overlay = self.root / 'local.env'
        overlay.write_text('CI_JOB=other\nDEBUG=changed', encoding='utf-8')
        report = check(self.template, [self.environment, overlay], allow_extra=['CI_*'], strict=True)
        self.assertEqual(report.errors, 1)
        self.assertEqual((report.issues[0].key, report.issues[0].path, report.issues[0].line),
                         ('DEBUG', str(overlay), 2))

    def test_optional_keys_and_allowances_combine(self):
        self.environment.write_text('HOST=h\nCI_JOB=42', encoding='utf-8')
        report = self.validate(['CI_*'], optional_keys=['TOKEN'], strict=True)
        self.assertTrue(report.valid)
        self.assertEqual(report.checked_keys, 1)

    def test_api_accepts_iterator_without_losing_patterns(self):
        self.assertTrue(self.validate(iter(['CI_*', 'DEBUG']), strict=True).valid)

    def test_repeated_and_unmatched_patterns_are_harmless(self):
        report = self.validate(['CI_*', 'CI_*', 'DEBUG', 'UNUSED_*'], strict=True)
        self.assertTrue(report.valid)
        self.assertEqual(report.checked_keys, 2)

    def test_invalid_patterns_have_safe_input_errors(self):
        for patterns in ([''], ['BAD-secret-canary'], ['[ABC]'], ['КЛЮЧ'], [123], ['CI_*', 'BAD KEY']):
            with self.subTest(patterns=patterns):
                with self.assertRaises(InputError) as caught:
                    self.validate(patterns)
                self.assertNotIn('secret-canary', str(caught.exception))

    def test_single_string_and_noniterable_configuration_are_rejected(self):
        for patterns in ('CI_*', b'CI_*', None):
            with self.subTest(patterns=patterns):
                with self.assertRaises(InputError):
                    self.validate(patterns)

    def test_cli_supports_repeated_patterns_in_all_formats(self):
        for output in ('text', 'json', 'github'):
            with self.subTest(output=output):
                result = self.cli('--strict', '--allow-extra', 'CI_*', '--allow-extra', 'DEBUG', '--format', output)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, '')
                self.assertNotIn('secret-canary', result.stdout)
                if output == 'json':
                    document = json.loads(result.stdout)
                    self.assertEqual((document['schema_version'], document['checked_keys'], document['status']), (1, 2, 'pass'))
                    self.assertEqual(document['issues'], [])
                else:
                    self.assertTrue(result.stdout.startswith('PASS:'))

    def test_cli_unallowed_key_keeps_failure_and_annotation(self):
        result = self.cli('--strict', '--allow-extra', 'CI_*', '--format', 'github')
        self.assertEqual(result.returncode, 1)
        self.assertIn('::error title=EnvLatch%3A extra_key', result.stdout)
        self.assertIn("Key 'DEBUG'", result.stdout)
        self.assertNotIn("Key 'CI_JOB'", result.stdout)

    def test_cli_invalid_pattern_uses_input_error_in_json_and_github(self):
        for output in ('json', 'github'):
            with self.subTest(output=output):
                result = self.cli('--allow-extra', 'BAD-secret-canary', '--format', output)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stderr, '')
                self.assertNotIn('secret-canary', result.stdout)
                if output == 'json':
                    self.assertEqual(json.loads(result.stdout)['status'], 'input_error')
                else:
                    self.assertIn('::error title=EnvLatch%3A input_error::', result.stdout)

    def test_cli_missing_pattern_is_usage_error(self):
        result = self.cli('--allow-extra')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertIn('expected one argument', result.stderr)


if __name__ == '__main__':
    unittest.main()
