"""GitHub Actions annotations: locations, command escaping, and CLI policy."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from envlatch.cli import render_github, render_text
from envlatch.core import Issue, Report


class AnnotationTests(unittest.TestCase):
    def report(self, *issues):
        return Report('contract.env', ('actual.env',), 2, tuple(issues))

    def test_error_annotation_has_file_line_and_code(self):
        report = self.report(Issue('error', 'empty_value', '.env', "Required key 'TOKEN' is blank.", 4, 'TOKEN'))
        self.assertEqual(render_github(report).splitlines()[0],
                         "::error title=EnvLatch%3A empty_value,file=.env,line=4::Required key 'TOKEN' is blank.")
        self.assertIn('FAIL: 2 required key(s), 1 error(s), 0 warning(s).', render_github(report))

    def test_warning_preserves_passing_summary(self):
        report = self.report(Issue('warning', 'extra_key', 'local.env', 'Unexpected key.', 2, 'DEBUG'))
        result = render_github(report)
        self.assertTrue(result.startswith('::warning '))
        self.assertIn('PASS:', result)
        self.assertIn('0 error(s), 1 warning(s)', result)

    def test_missing_line_is_not_invented(self):
        result = render_github(self.report(Issue('error', 'missing_key', '.env', 'Missing key.', key='TOKEN')))
        self.assertIn('file=.env::', result)
        self.assertNotIn(',line=', result)

    def test_input_error_without_path_uses_general_annotation(self):
        result = render_github(self.report(Issue('error', 'input_error', None, 'Cannot read input file.')))
        self.assertTrue(result.startswith('::error title=EnvLatch%3A input_error::Cannot read input file.'))
        self.assertNotIn('file=', result)
        self.assertNotIn('None', result)

    def test_properties_escape_command_delimiters_and_newlines(self):
        result = render_github(self.report(Issue('error', 'invalid_value', 'C:/a,b%\r\n.env', 'Invalid value.', 1)))
        self.assertIn('file=C%3A/a%2Cb%25%0D%0A.env,line=1', result)
        self.assertEqual(len(result.splitlines()), 2)

    def test_message_escaping_prevents_a_second_workflow_command(self):
        message = 'Bad input 10%\r\n::error title=injected::injected-message'
        result = render_github(self.report(Issue('error', 'input_error', None, message)))
        self.assertIn('10%25%0D%0A::error title=injected::injected-message', result)
        self.assertEqual(len(result.splitlines()), 2)
        self.assertEqual(sum(line.startswith('::') for line in result.splitlines()), 1)

    def test_existing_percent_escape_is_not_treated_as_a_newline(self):
        result = render_github(self.report(Issue('error', 'input_error', 'file%0A.env', 'Literal %0A marker.')))
        self.assertIn('file=file%250A.env', result)
        self.assertIn('Literal %250A marker.', result)

    def test_success_is_identical_to_default_text_summary(self):
        report = self.report()
        self.assertEqual(render_github(report), render_text(report))
        self.assertNotIn('::', render_github(report))

    def test_unicode_paths_are_preserved(self):
        result = render_github(self.report(Issue('warning', 'extra_key', 'настройки.env', 'Unexpected key.', 1)))
        self.assertIn('file=настройки.env,line=1', result)


class AnnotationCliTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.template = self.root / 'template.env'
        self.environment = self.root / 'actual.env'
        self.template.write_text('TOKEN=\nHOST=\n', encoding='utf-8')
        self.environment.write_text('TOKEN=private-value-canary\nHOST=localhost\n', encoding='utf-8')

    def cli(self, *arguments):
        return subprocess.run([sys.executable, '-m', 'envlatch', '--template', str(self.template),
                               '--env', str(self.environment), '--format', 'github', *arguments],
                              capture_output=True, text=True, check=False)

    def test_cli_success_has_only_summary(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertTrue(result.stdout.startswith('PASS:'))
        self.assertNotIn('::', result.stdout)
        self.assertNotIn('private-value-canary', result.stdout)

    def test_cli_validation_annotations_never_contain_values(self):
        self.environment.write_text('HOST=\nEXTRA=private-value-canary', encoding='utf-8')
        result = self.cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, '')
        self.assertIn('::error title=EnvLatch%3A missing_key', result.stdout)
        self.assertIn('::error title=EnvLatch%3A empty_value', result.stdout)
        self.assertIn('::warning title=EnvLatch%3A extra_key', result.stdout)
        self.assertNotIn('private-value-canary', result.stdout)

    def test_cli_warning_and_strict_exit_codes(self):
        self.environment.write_text('TOKEN=private-value-canary\nHOST=localhost\nEXTRA=yes', encoding='utf-8')
        normal = self.cli()
        strict = self.cli('--strict')
        self.assertEqual(normal.returncode, 0)
        self.assertIn('::warning ', normal.stdout)
        self.assertEqual(strict.returncode, 1)
        self.assertIn('::error title=EnvLatch%3A extra_key', strict.stdout)
        self.assertNotIn('private-value-canary', normal.stdout + strict.stdout)

    def test_cli_read_and_encoding_errors_are_annotations_with_exit_two(self):
        for invalid_utf8 in (False, True):
            with self.subTest(invalid_utf8=invalid_utf8):
                if invalid_utf8:
                    self.environment.write_bytes(b'TOKEN=\xffprivate-value-canary')
                else:
                    self.environment.unlink()
                result = self.cli()
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stderr, '')
                self.assertIn('::error title=EnvLatch%3A input_error::', result.stdout)
                self.assertNotIn('private-value-canary', result.stdout)
                self.assertNotIn('Traceback', result.stdout)

    def test_cli_invalid_optional_name_uses_safe_input_annotation(self):
        result = self.cli('--optional', 'INVALID-private-value-canary')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, '')
        self.assertIn('::error title=EnvLatch%3A input_error::', result.stdout)
        self.assertNotIn('private-value-canary', result.stdout)

    def test_cli_overlay_points_to_effective_definition(self):
        overlay = self.root / 'overlay.env'
        overlay.write_text('# a comment\nTOKEN=', encoding='utf-8')
        failed = self.cli('--env', str(overlay))
        self.assertEqual(failed.returncode, 1)
        escaped = str(overlay).replace('%', '%25').replace(':', '%3A').replace(',', '%2C')
        self.assertIn('file=' + escaped + ',line=2::', failed.stdout)
        optional = self.cli('--env', str(overlay), '--optional', 'TOKEN')
        self.assertEqual(optional.returncode, 0, optional.stderr)
        self.assertNotIn('::error', optional.stdout)

    def test_cli_usage_errors_remain_human_readable(self):
        result = self.cli('--optional')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertIn('expected one argument', result.stderr)

    def test_cli_rejected_multiline_fragments_never_become_annotations(self):
        self.environment.write_text('TOKEN="private-value-canary\nPRIVATE_FRAGMENT=hidden\n"', encoding='utf-8')
        result = self.cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn('::error title=EnvLatch%3A invalid_value', result.stdout)
        self.assertNotIn('PRIVATE_FRAGMENT', result.stdout)
        self.assertNotIn('private-value-canary', result.stdout)


if __name__ == '__main__':
    unittest.main()
