"""Release checks using only the standard library (Python 3.10+)."""

from __future__ import annotations

import argparse
import ast
from configparser import ConfigParser
from email import policy
from email.parser import BytesParser
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = {
    'LICENSE', 'README.md', 'README.ru.md', 'CHANGELOG.md', 'CONTRIBUTING.md',
    'CODE_OF_CONDUCT.md', 'SECURITY.md', 'pyproject.toml', 'MANIFEST.in',
    '.env.example', 'envlatch.json', 'tools/check_distribution.py', 'setup.cfg', 'PUBLISHING.md',
    'examples/allow-extra/development.env', 'examples/config/envlatch.json',
    'examples/optional/.env.example', 'examples/types/template.env.example',
    'examples/types/development.env', 'examples/types/envlatch.json', 'PKG-INFO',
}
EGG_FILES = {'PKG-INFO', 'SOURCES.txt', 'dependency_links.txt', 'entry_points.txt', 'top_level.txt'}
DIST_FILES = {'METADATA', 'WHEEL', 'entry_points.txt', 'top_level.txt', 'RECORD', 'licenses/LICENSE'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def source_version():
    tree = ast.parse((ROOT / 'src/envlatch/__init__.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__version__'
                                               for t in node.targets):
            value = ast.literal_eval(node.value)
            require(isinstance(value, str) and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', value),
                    'A stable three-part package version is required.')
            return value
    raise ValueError('Missing package version.')


def check_tag(version, tag, required=False):
    require(not required or bool(tag), 'Publishing requires a release tag, not a branch.')
    require(not tag or tag == f'v{version}', 'Release tag and package version do not match.')


def safe_path(name):
    path = PurePosixPath(name)
    require(not path.is_absolute() and '..' not in path.parts and '\\' not in name,
            'Unsafe archive member path.')
    return path


def check_metadata(data, version):
    metadata = BytesParser(policy=policy.default).parsebytes(data)
    for field, expected in {'Name': 'envlatch', 'Version': version, 'Requires-Python': '>=3.10',
                            'License-Expression': 'MIT', 'Description-Content-Type': 'text/markdown'}.items():
        require(metadata.get_all(field) == [expected], f'Incorrect or duplicate metadata field: {field}.')
    require(not metadata.get_all('Requires-Dist'), 'Runtime dependencies must remain empty.')
    require(metadata.get_all('License-File') == ['LICENSE'], 'Missing license-file metadata.')
    description = metadata.get_payload()
    require(isinstance(description, str) and '# EnvLatch' in description, 'Missing long description.')
    links = re.findall(r'\]\(([^)]+)\)', description)
    require(all('://' in link or link.startswith('#') for link in links),
            'PyPI description contains repository-relative links.')
    require(any(value.startswith('Repository, https://github.com/sinzbtw/envlatch')
                for value in metadata.get_all('Project-URL', [])), 'Missing repository URL.')
    return metadata


def check_entry_point(data):
    parser = ConfigParser()
    parser.read_string(data.decode('utf-8'))
    require(parser.get('console_scripts', 'envlatch', fallback='') == 'envlatch.cli:main',
            'Missing or incorrect console entry point.')


def check_archives(directory, version):
    wheel = directory / f'envlatch-{version}-py3-none-any.whl'
    sdist = directory / f'envlatch-{version}.tar.gz'
    require(set(directory.iterdir()) == {wheel, sdist},
            'Distribution directory must contain exactly the current wheel and sdist.')
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), 'Duplicate wheel members.')
        prefix = f'envlatch-{version}.dist-info/'
        for name in names:
            path = safe_path(name)
            module = len(path.parts) == 2 and path.parts[0] == 'envlatch' and path.suffix == '.py'
            require(module or (name.startswith(prefix) and name[len(prefix):] in DIST_FILES),
                    'Unexpected wheel content; refusing to publish.')
        check_metadata(archive.read(prefix + 'METADATA'), version)
        check_entry_point(archive.read(prefix + 'entry_points.txt'))
        require(archive.read(prefix + 'licenses/LICENSE').decode('utf-8').splitlines()
                == (ROOT / 'LICENSE').read_text(encoding='utf-8').splitlines(),
                'Wheel license differs from source.')
        require({f'envlatch/{name.name}' for name in (ROOT / 'src/envlatch').glob('*.py')} <= set(names),
                'Wheel is missing a source module.')
    with tarfile.open(sdist, 'r:gz') as archive:
        prefix = f'envlatch-{version}/'
        members = archive.getmembers()
        require(len(members) == len({m.name for m in members}), 'Duplicate sdist members.')
        files = set()
        for member in members:
            safe_path(member.name)
            require(member.name == prefix[:-1] or member.name.startswith(prefix), 'Unexpected sdist root.')
            require(member.isfile() or member.isdir(), 'Links and special files are forbidden in the sdist.')
            if member.isdir():
                continue
            name = member.name[len(prefix):]
            path = PurePosixPath(name)
            code = len(path.parts) == 3 and path.parts[:2] == ('src', 'envlatch') and path.suffix == '.py'
            test = len(path.parts) == 2 and path.parts[0] == 'tests' and path.name.startswith('test_') and path.suffix == '.py'
            egg = len(path.parts) == 3 and path.parts[:2] == ('src', 'envlatch.egg-info') and path.name in EGG_FILES
            require(name in SOURCE_FILES or code or test or egg, 'Unexpected sdist content; refusing to publish.')
            files.add(name)
        require(SOURCE_FILES <= files, 'Source archive is missing documentation, fixtures or release tooling.')
        require({f'src/envlatch/{p.name}' for p in (ROOT / 'src/envlatch').glob('*.py')} <= files,
                'Source archive is missing a module.')
        require({f'tests/{p.name}' for p in (ROOT / 'tests').glob('test_*.py')} <= files,
                'Source archive is missing tests.')
        check_metadata(archive.extractfile(prefix + 'PKG-INFO').read(), version)
    print(f'Validated wheel/sdist content and metadata for EnvLatch {version}.')
    return wheel, sdist


def check_installs(artifacts, version):
    clean_env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')}
    for artifact in artifacts:
        with tempfile.TemporaryDirectory(prefix='envlatch-package-') as temp:
            root = Path(temp)
            environment = root / 'venv'
            venv.EnvBuilder(with_pip=True).create(environment)
            scripts = environment / ('Scripts' if os.name == 'nt' else 'bin')
            python = scripts / ('python.exe' if os.name == 'nt' else 'python')
            cli = scripts / ('envlatch.exe' if os.name == 'nt' else 'envlatch')

            def run(*args):
                subprocess.run([str(arg) for arg in args], cwd=root, env=clean_env, check=True)

            run(python, '-m', 'pip', 'install', '--no-deps', artifact.resolve())
            run(python, '-m', 'pip', 'check')
            run(python, '-c', 'import envlatch, sys; from pathlib import Path; '
                f'assert envlatch.__version__ == {version!r}; '
                'assert Path(envlatch.__file__).is_relative_to(Path(sys.prefix)); '
                'from importlib.metadata import version; assert version("envlatch") == envlatch.__version__')
            run(cli, '--version')
            run(python, '-m', 'envlatch', '--help')
            run(cli, '--config', ROOT / 'examples/types/envlatch.json', '--format', 'json')
            run(python, '-m', 'unittest', 'discover', '-s', ROOT / 'tests', '-q')
            print(f'Installed and tested {artifact.name} outside the checkout.', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--tag', default='')
    parser.add_argument('--install-test', action='store_true')
    args = parser.parse_args(argv)
    version = source_version()
    check_tag(version, args.tag, required=os.environ.get('REQUIRE_RELEASE_TAG') == 'true')
    artifacts = check_archives(args.directory.resolve(), version)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
            output.write(f'version={version}\n')
    if args.install_test:
        check_installs(artifacts, version)


if __name__ == '__main__':
    main()
