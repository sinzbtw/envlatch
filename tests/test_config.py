"""JSON configuration paths, strict validation, and CLI precedence."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from envlatch.config import Config, load_config
from envlatch.core import InputError


class ConfigFixture(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.project = self.root / 'project'
        self.outside = self.root / 'elsewhere'
        self.project.mkdir()
        self.outside.mkdir()
        self.template = self.project / 'template.env'
        self.environment = self.project / 'actual.env'
        self.path = self.project / 'envlatch.json'
        self.template.write_text('HOST=\nTOKEN=\n', encoding='utf-8')
        self.environment.write_text('HOST=localhost\nTOKEN=private-value-canary\n', encoding='utf-8')
        self.write(self.settings())

    def settings(self, **changes):
        return {'template': 'template.env', 'env': ['actual.env'], 'strict': True,
                'format': 'json', **changes}

    def write(self, value):
        self.path.write_text(value if isinstance(value, str) else json.dumps(value), encoding='utf-8')

    def cli(self, *arguments, cwd=None):
        return subprocess.run([sys.executable, '-m', 'envlatch', '--config', str(self.path), *arguments],
                              cwd=cwd or self.outside, capture_output=True, text=True, check=False)


class ConfigLoaderTests(ConfigFixture):
    def test_relative_paths_are_based_on_config_directory(self):
        settings = load_config(self.path)
        self.assertEqual(settings.template, str(self.template))
        self.assertEqual(settings.environments, (str(self.environment),))
        self.assertTrue(settings.strict)
        self.assertEqual(settings.output_format, 'json')

    def test_bom_and_crlf_are_supported(self):
        text = json.dumps(self.settings(), indent=2).replace('\n', '\r\n')
        self.path.write_bytes(b'\xef\xbb\xbf' + text.encode('utf-8'))
        self.assertEqual(load_config(self.path).environments, (str(self.environment),))

    def test_absolute_paths_are_preserved(self):
        self.write(self.settings(template=str(self.template), env=[str(self.environment)]))
        self.assertEqual(load_config(self.path).template, str(self.template))

    def test_sparse_config_keeps_documented_defaults(self):
        self.write({})
        self.assertEqual(load_config(self.path), Config())

    def test_all_settings_and_overlay_order_are_preserved(self):
        self.write(self.settings(env=['actual.env', 'local.env'], optional=['TOKEN'],
                                 allow_extra=['CI_*', 'DEBUG'], format='github'))
        settings = load_config(self.path)
        self.assertEqual(settings.environments, (str(self.environment), str(self.project / 'local.env')))
        self.assertEqual(settings.optional_keys, ('TOKEN',))
        self.assertEqual(settings.allow_extra, ('CI_*', 'DEBUG'))
        self.assertEqual(settings.output_format, 'github')

    def test_top_level_must_be_an_object(self):
        for text in ('null', '[]', '"private-value-canary"', 'false', '42'):
            with self.subTest(text=text):
                self.write(text)
                with self.assertRaises(InputError) as caught:
                    load_config(self.path)
                self.assertNotIn('private-value-canary', str(caught.exception))

    def test_unknown_fields_never_echo_values_or_unknown_names(self):
        self.write({'private-value-canary': 'another-private-value'})
        with self.assertRaises(InputError) as caught:
            load_config(self.path)
        self.assertIn('Unknown configuration option', str(caught.exception))
        self.assertNotIn('private-value', str(caught.exception))

    def test_duplicate_fields_are_rejected_without_echoing_input(self):
        self.write('{"template":"private-value-canary","template":"another"}')
        with self.assertRaises(InputError) as caught:
            load_config(self.path)
        self.assertIn('Duplicate', str(caught.exception))
        self.assertNotIn('private-value-canary', str(caught.exception))

    def test_malformed_json_reports_location_without_contents(self):
        self.write('{"env": ["private-value-canary", ]}')
        with self.assertRaises(InputError) as caught:
            load_config(self.path)
        self.assertIn('line 1', str(caught.exception))
        self.assertNotIn('private-value-canary', str(caught.exception))

    def test_nonstandard_numeric_constants_are_rejected(self):
        for constant in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(constant=constant):
                self.write('{"strict":' + constant + '}')
                with self.assertRaises(InputError):
                    load_config(self.path)

    def test_missing_directory_and_non_utf8_inputs_are_safe(self):
        for path in (self.project / 'missing.json', self.project):
            with self.subTest(path=path):
                with self.assertRaises(InputError):
                    load_config(path)
        self.path.write_bytes(b'{"template":"\xffprivate-value-canary"}')
        with self.assertRaises(InputError) as caught:
            load_config(self.path)
        self.assertNotIn('private-value-canary', str(caught.exception))

    def test_setting_types_are_checked_before_use(self):
        cases = [('strict', 1), ('strict', 'false'), ('strict', None), ('template', 3),
                 ('env', 'actual.env'), ('env', []), ('env', [3]), ('optional', 'TOKEN'),
                 ('optional', [False]), ('allow_extra', None), ('allow_extra', [3]),
                 ('format', 'private-value-canary'), ('format', []), ('format', {})]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                self.write(self.settings(**{field: value}))
                with self.assertRaises(InputError) as caught:
                    load_config(self.path)
                self.assertNotIn('private-value-canary', str(caught.exception))

    def test_empty_and_nul_strings_are_rejected(self):
        for field, value in [('template', ''), ('template', '   '), ('template', '\x00'),
                             ('env', ['']), ('optional', ['']), ('allow_extra', ['\x00'])]:
            with self.subTest(field=field, value=value):
                self.write(self.settings(**{field: value}))
                with self.assertRaises(InputError):
                    load_config(self.path)

    def test_unpaired_unicode_surrogates_are_rejected(self):
        self.write(self.settings(template='\ud800'))
        with self.assertRaises(InputError):
            load_config(self.path)

    def test_paths_do_not_expand_variables_or_home(self):
        self.write(self.settings(template='$HOME/template.env', env=['~/.env']))
        settings = load_config(self.path)
        self.assertEqual(settings.template, os.path.abspath(self.project / '$HOME/template.env'))
        self.assertEqual(settings.environments, (os.path.abspath(self.project / '~/.env'),))


class ConfigCliTests(ConfigFixture):
    def test_config_only_runs_from_another_directory(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        document = json.loads(result.stdout)
        self.assertEqual(document['status'], 'pass')
        self.assertEqual(document['template'], str(self.template))
        self.assertEqual(document['environments'], [str(self.environment)])
        self.assertNotIn('private-value-canary', result.stdout)

    def test_cli_paths_override_config_and_remain_cwd_relative(self):
        alternate = self.outside / 'alternate.env'
        alternate.write_text('ALT=example', encoding='utf-8')
        self.write(self.settings(template='missing.env', env=['missing.env']))
        result = self.cli('--template', 'alternate.env', '--env', 'alternate.env')
        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads(result.stdout)
        self.assertEqual(document['checked_keys'], 1)
        self.assertEqual(document['template'], 'alternate.env')
        self.assertEqual(document['environments'], ['alternate.env'])

    def test_cli_env_list_replaces_config_and_keeps_overlay_order(self):
        base = self.outside / 'base.env'
        local = self.outside / 'local.env'
        base.write_text('HOST=localhost', encoding='utf-8')
        local.write_text('TOKEN=private-value-canary', encoding='utf-8')
        self.write(self.settings(env=['missing.env']))
        result = self.cli('--env', 'base.env', '--env', 'local.env')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['environments'], ['base.env', 'local.env'])

    def test_cli_optional_list_replaces_instead_of_appending(self):
        self.environment.write_text('', encoding='utf-8')
        self.write(self.settings(optional=['HOST']))
        result = self.cli('--optional', 'TOKEN')
        self.assertEqual(result.returncode, 1)
        document = json.loads(result.stdout)
        self.assertEqual(document['checked_keys'], 1)
        self.assertEqual([i['key'] for i in document['issues']], ['HOST'])

    def test_cli_allowance_list_replaces_instead_of_appending(self):
        self.environment.write_text('HOST=h\nTOKEN=t\nCI_JOB=42\nDEBUG=yes', encoding='utf-8')
        self.write(self.settings(allow_extra=['CI_*']))
        result = self.cli('--allow-extra', 'DEBUG')
        self.assertEqual(result.returncode, 1)
        self.assertEqual([i['key'] for i in json.loads(result.stdout)['issues']], ['CI_JOB'])

    def test_no_strict_overrides_enabled_config_policy(self):
        self.environment.write_text('HOST=h\nTOKEN=t\nEXTRA=yes', encoding='utf-8')
        result = self.cli('--no-strict')
        self.assertEqual(result.returncode, 0)
        document = json.loads(result.stdout)
        self.assertEqual((document['errors'], document['warnings']), (0, 1))

    def test_strict_overrides_disabled_config_policy(self):
        self.environment.write_text('HOST=h\nTOKEN=t\nEXTRA=yes', encoding='utf-8')
        self.write(self.settings(strict=False))
        result = self.cli('--strict')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['errors'], 1)

    def test_conflicting_strict_flags_are_usage_errors(self):
        result = self.cli('--strict', '--no-strict')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertIn('not allowed', result.stderr)

    def test_explicit_format_overrides_config_output(self):
        for output in ('text', 'github'):
            with self.subTest(output=output):
                result = self.cli('--format', output)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.startswith('PASS:'))

    def test_valid_config_can_select_github_error_annotations(self):
        self.environment.write_text('HOST=h', encoding='utf-8')
        self.write(self.settings(format='github'))
        result = self.cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn('::error title=EnvLatch%3A missing_key', result.stdout)
        explicit = self.cli('--format', 'json')
        self.assertEqual(json.loads(explicit.stdout)['status'], 'fail')

    def test_missing_paths_are_usage_errors(self):
        self.write({'strict': True})
        result = self.cli('--format', 'json')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertIn('provide --template and --env', result.stderr)

    def test_cli_paths_can_complete_a_sparse_configuration(self):
        self.write({'strict': True})
        result = self.cli('--template', str(self.template), '--env', str(self.environment), '--format', 'json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['schema_version'], 1)

    def test_malformed_config_uses_explicit_structured_output_safely(self):
        self.write('{"env": ["private-value-canary", ]}')
        for output in ('json', 'github'):
            with self.subTest(output=output):
                result = self.cli('--format', output)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stderr, '')
                self.assertNotIn('private-value-canary', result.stdout)
                if output == 'json':
                    document = json.loads(result.stdout)
                    self.assertEqual(document['status'], 'input_error')
                    self.assertEqual(document['template'], '')
                    self.assertEqual(document['environments'], [])
                else:
                    self.assertIn('::error title=EnvLatch%3A input_error', result.stdout)

    def test_invalid_config_does_not_control_fallback_output(self):
        self.write(self.settings(strict='private-value-canary'))
        result = self.cli()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertIn('ERROR [input_error]', result.stderr)
        self.assertNotIn('private-value-canary', result.stderr)

    def test_missing_config_is_a_structured_input_error(self):
        self.path.unlink()
        result = self.cli('--format', 'json')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['status'], 'input_error')
        self.assertNotIn('Traceback', result.stderr)

    def test_policy_errors_remain_safe_after_successful_config_load(self):
        for field, value in [('optional', ['INVALID-private-value-canary']),
                             ('allow_extra', ['INVALID-private-value-canary'])]:
            with self.subTest(field=field):
                self.write(self.settings(**{field: value}))
                result = self.cli()
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)['status'], 'input_error')
                self.assertNotIn('private-value-canary', result.stdout + result.stderr)

    def test_configuration_is_never_discovered_implicitly(self):
        self.write('invalid-private-value-canary')
        result = subprocess.run([sys.executable, '-m', 'envlatch', '--template', str(self.template),
                                 '--env', str(self.environment)], cwd=self.project,
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith('PASS:'))

    def test_cli_does_not_silently_ignore_a_malformed_config_field(self):
        self.write(self.settings(strict='private-value-canary'))
        result = self.cli('--strict', '--format', 'json')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['status'], 'input_error')
        self.assertNotIn('private-value-canary', result.stdout)

    def test_version_does_not_require_reading_a_config(self):
        self.path.unlink()
        result = self.cli('--version')
        self.assertEqual(result.returncode, 0)
        self.assertIn('EnvLatch 0.5.0', result.stdout)


if __name__ == '__main__':
    unittest.main()
