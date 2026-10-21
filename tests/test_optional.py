"""Optional-key policy across the Python API, overlays, and installed CLI."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from envlatch.core import InputError, check


class OptionalKeyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.template = self.root / 'contract.env'
        self.environment = self.root / 'actual.env'
        self.template.write_text('HOST=\nSENTRY_DSN=\nLOG_LEVEL=\n', encoding='utf-8')
        self.environment.write_text('HOST=localhost\n', encoding='utf-8')
        self.optional = ['SENTRY_DSN', 'LOG_LEVEL']

    def validate(self, **kwargs):
        return check(self.template, self.environment, optional_keys=self.optional, **kwargs)

    def cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'envlatch', '--template', str(self.template),
                               '--env', str(self.environment), *args],
                              capture_output=True, text=True, check=False)

    def test_missing_optional_keys_pass_and_only_required_keys_are_counted(self):
        report = self.validate(strict=True)
        self.assertTrue(report.valid)
        self.assertEqual(report.checked_keys, 1)
        self.assertEqual(report.issues, ())

    def test_blank_optional_values_are_allowed(self):
        for value in ('', '   ', "''", '"  "', '# comment'):
            with self.subTest(value=value):
                self.environment.write_text('HOST=localhost\nSENTRY_DSN=' + value, encoding='utf-8')
                self.assertTrue(self.validate(strict=True).valid)

    def test_present_optional_value_is_not_reported(self):
        self.environment.write_text('HOST=localhost\nSENTRY_DSN=secret-canary', encoding='utf-8')
        report = self.validate()
        self.assertTrue(report.valid)
        self.assertNotIn('secret-canary', repr(report))

    def test_remaining_required_keys_still_fail(self):
        for value, code in (('', 'missing_key'), ('HOST= ', 'empty_value')):
            with self.subTest(value=value):
                self.environment.write_text(value, encoding='utf-8')
                report = self.validate()
                self.assertFalse(report.valid)
                self.assertEqual([(i.code, i.key) for i in report.issues], [(code, 'HOST')])

    def test_unknown_optional_name_is_an_error_at_template(self):
        report = check(self.template, self.environment, optional_keys=['TYPO', *self.optional])
        self.assertFalse(report.valid)
        self.assertEqual(report.errors, 1)
        issue = report.issues[0]
        self.assertEqual((issue.code, issue.key, issue.path),
                         ('unknown_optional_key', 'TYPO', str(self.template)))

    def test_unknown_optional_name_does_not_whitelist_extra_key(self):
        self.environment.write_text('HOST=localhost\nTYPO=secret-canary', encoding='utf-8')
        report = check(self.template, self.environment, optional_keys=['TYPO', *self.optional], strict=True)
        self.assertEqual([i.code for i in report.issues], ['unknown_optional_key', 'extra_key'])
        self.assertNotIn('secret-canary', repr(report))

    def test_optional_policy_is_case_sensitive(self):
        report = check(self.template, self.environment, optional_keys=['sentry_dsn', 'LOG_LEVEL'])
        self.assertEqual([i.code for i in report.issues], ['unknown_optional_key', 'missing_key'])

    def test_repeated_optional_names_are_idempotent(self):
        report = check(self.template, self.environment, optional_keys=self.optional * 2)
        self.assertTrue(report.valid)
        self.assertEqual(report.checked_keys, 1)

    def test_all_template_keys_may_be_optional(self):
        self.environment.write_text('', encoding='utf-8')
        report = check(self.template, self.environment, optional_keys=['HOST', *self.optional])
        self.assertTrue(report.valid)
        self.assertEqual(report.checked_keys, 0)

    def test_duplicates_and_bad_values_on_optional_keys_still_fail(self):
        for text, code in [('SENTRY_DSN=one\nSENTRY_DSN=two', 'duplicate_key'),
                           ('SENTRY_DSN="secret-canary', 'invalid_value')]:
            with self.subTest(code=code):
                self.environment.write_text('HOST=localhost\n' + text, encoding='utf-8')
                report = self.validate()
                self.assertFalse(report.valid)
                self.assertEqual(report.issues[0].code, code)
                self.assertNotIn('secret-canary', repr(report))

    def test_optional_policy_applies_after_overlay(self):
        overlay = self.root / 'local.env'
        overlay.write_text('SENTRY_DSN=\nLOG_LEVEL=', encoding='utf-8')
        self.environment.write_text('HOST=localhost\nSENTRY_DSN=secret-canary', encoding='utf-8')
        report = check(self.template, [self.environment, overlay], optional_keys=self.optional, strict=True)
        self.assertTrue(report.valid)
        self.assertEqual(report.checked_keys, 1)
        self.assertEqual(report.environments, (str(self.environment), str(overlay)))

    def test_invalid_api_names_are_safe_input_errors(self):
        for names in (['INVALID-secret-canary'], [''], [123], ['HOST', 'BAD KEY']):
            with self.subTest(names=names):
                with self.assertRaises(InputError) as caught:
                    check(self.template, self.environment, optional_keys=names)
                self.assertNotIn('secret-canary', str(caught.exception))

    def test_api_rejects_accidental_string_sequence(self):
        with self.assertRaises(InputError):
            check(self.template, self.environment, optional_keys='HOST')

    def test_api_accepts_an_iterable_without_losing_optional_names(self):
        report = check(self.template, self.environment, optional_keys=iter(self.optional))
        self.assertTrue(report.valid)
        self.assertEqual(report.checked_keys, 1)

    def test_api_rejects_noniterable_configuration(self):
        with self.assertRaises(InputError):
            check(self.template, self.environment, optional_keys=None)

    def test_cli_repeated_flags_in_text_and_json(self):
        args = ['--optional', 'SENTRY_DSN', '--optional', 'LOG_LEVEL', '--strict']
        text = self.cli(*args)
        self.assertEqual(text.returncode, 0, text.stderr)
        self.assertIn('PASS: 1 required key(s)', text.stdout)
        result = self.cli(*args, '--format', 'json')
        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads(result.stdout)
        self.assertEqual((document['schema_version'], document['checked_keys'], document['status']), (1, 1, 'pass'))
        self.assertEqual(document['issues'], [])

    def test_cli_typo_fails_with_json_diagnostic(self):
        result = self.cli('--optional', 'TYPO', '--format', 'json')
        self.assertEqual(result.returncode, 1)
        document = json.loads(result.stdout)
        self.assertEqual(document['status'], 'fail')
        self.assertEqual(document['issues'][0]['code'], 'unknown_optional_key')

    def test_cli_invalid_name_is_safe_json_input_error(self):
        result = self.cli('--optional', 'INVALID-secret-canary', '--format', 'json')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, '')
        self.assertEqual(json.loads(result.stdout)['status'], 'input_error')
        self.assertNotIn('secret-canary', result.stdout)

    def test_cli_missing_optional_argument_is_usage_error(self):
        result = self.cli('--optional')
        self.assertEqual(result.returncode, 2)
        self.assertIn('expected one argument', result.stderr)

    def test_default_still_requires_every_template_key(self):
        result = self.cli('--format', 'json')
        self.assertEqual(result.returncode, 1)
        document = json.loads(result.stdout)
        self.assertEqual(document['checked_keys'], 3)
        self.assertEqual(document['errors'], 2)


if __name__ == '__main__':
    unittest.main()
