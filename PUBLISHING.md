# Publishing EnvLatch / Публикация EnvLatch

[English](#english) | [Русский](#русский)

## English

### One-time PyPI setup

1. Sign into [PyPI](https://pypi.org/) using an account with a verified email address and two-factor authentication.
2. For the first upload, open [account → Publishing](https://pypi.org/manage/account/publishing/) and add a **pending GitHub publisher** with these exact values:

   | PyPI field | Value |
   | --- | --- |
   | PyPI Project Name | `envlatch` |
   | Owner | `sinzbtw` |
   | Repository name | `envlatch` |
   | Workflow name | `publish.yml` (filename only) |
   | Environment name | `pypi` |

   If the project already exists under your account, use [project → Publishing](https://pypi.org/manage/project/envlatch/settings/publishing/) instead. A pending publisher does not reserve the package name.
3. The repository's `pypi` environment allows only tags matching `v*`. Package validation also requires the exact tag `v<package version>`, a stable three-part version and a commit reachable from `main`. The account owner controls release creation; this setup does not require approval on each upload. Adding environment reviewers later is possible if manual approval is desired.
4. After verifying the publisher exists, enable the repository Actions variable `PYPI_PUBLISHING_ENABLED` with the exact value `true`. Until then, build and installation checks still run, but no upload is attempted. This is a non-secret switch, not a credential.

No PyPI password or API token belongs in GitHub Secrets, `.pypirc`, the repository or this workflow. Only the isolated publish job has `id-token: write`; PyPI issues its temporary project-scoped credentials through OIDC. The action also uploads PEP 740 attestations.

### Automatic releases

1. Update `pyproject.toml`, `src/envlatch/__init__.py` and CHANGELOG for a new stable version; commit and push to `main`.
2. Publish a non-prerelease GitHub Release using a matching tag, for example `v0.6.1`. The `release: published` event starts `.github/workflows/publish.yml`. Merely pushing to `main`, pushing a tag, editing an existing release, or creating a draft does **not** publish to PyPI.
3. The workflow builds the sdist, builds a wheel from that sdist, checks metadata and the archive allowlist, and runs `twine check --strict`. It then installs each artifact into its own fresh environment outside the checkout and runs the full tests on Linux/Python 3.10 and 3.13 and Windows/Python 3.13. A failure prevents upload.
4. Ruff lint/format checks and the branch-coverage threshold must also pass through the reusable Quality workflow. A separate job downloads exactly the validated artifacts and publishes them with the PyPA action through Trusted Publishing. No checkout/build commands execute in that job. Another job verifies installation of that exact version from PyPI, allowing a short index-propagation delay.

Both archives are uploaded to **PyPI**, not GitHub Release assets. GitHub Releases continue to contain only their automatic source archives. PRs and pushes run packaging checks without publishing or OIDC permissions. Third-party Actions are pinned to commit SHAs.

### First upload, dry runs and recovery

The [Package and publish workflow](https://github.com/sinzbtw/envlatch/actions/workflows/publish.yml) also supports **Run workflow**. Select a stable release tag containing the workflow and set `publish=true` for an upload; selecting `main` with `publish=true` fails the tag guard. The default `publish=false` performs checks only. Use this to bootstrap a release whose original event ran before PyPI setup, or to retry a failure before any files were uploaded.

PyPI versions and filenames cannot be overwritten. The workflow deliberately does not skip existing files. If an upload partially succeeded, inspect the files and failure before retrying; if their contents are wrong, fix the problem and publish a new patch version. Do not delete/move old Git tags to reuse a version. A failure in the final installation check means the upload may already be public; inspect PyPI before taking further action.

Local equivalent (use a new, empty output directory; these commands never upload):

```sh
python -m pip install build twine
python -m build --outdir dist/release-check
python -m twine check --strict dist/release-check/*
python tools/check_distribution.py dist/release-check --tag v0.6.1 --install-test
```

Use the version being checked instead of `v0.6.1`. Build tools are development dependencies only. The archive allowlist includes the public invented fixtures, documentation, tests and source modules; local `.env` files, credentials, caches and unrelated files cause validation to fail if they enter a distribution.

References: [PyPI pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/), [PyPA publishing action](https://github.com/pypa/gh-action-pypi-publish).

## Русский

### Однократная настройка

1. Войдите в [PyPI](https://pypi.org/) с подтверждённой почтой и включённой 2FA.
2. На странице [аккаунт → Publishing](https://pypi.org/manage/account/publishing/) добавьте **pending GitHub publisher**: проект `envlatch`, владелец `sinzbtw`, репозиторий `envlatch`, файл workflow `publish.yml`, среда `pypi`. Если проект уже принадлежит вашему аккаунту, добавляйте издателя в настройках этого проекта. Pending Publisher ещё не резервирует имя пакета.
3. В GitHub настроена среда `pypi`, допускающая только теги `v*`. Дополнительная проверка требует точного совпадения тега `v<версия пакета>`, стабильной версии из трёх чисел и коммита, присутствующего в истории `main`. Публикация выполняется автоматически после создания релиза владельцем репозитория; отдельного подтверждения каждой загрузки нет.
4. После проверки издателя включите переменную репозитория `PYPI_PUBLISHING_ENABLED=true`. Это обычный переключатель, не секрет. До включения сборка и тесты работают, но загрузка в PyPI не запускается.

Постоянные API-токены не используются. Пароли и токены не добавляются в GitHub Secrets, `.pypirc` или проект. Только отдельное задание публикации получает `id-token: write` и обменивает удостоверение GitHub на краткоживущие права PyPI. Также публикуются подтверждения происхождения PEP 740.

### Как выпускать версии

Перед загрузкой в PyPI также должны пройти Ruff, проверка оформления и порог покрытия из повторно используемого workflow Quality.

Обновите версии в `pyproject.toml` и `src/envlatch/__init__.py`, дополните CHANGELOG и отправьте изменения в `main`. Опубликуйте обычный GitHub Release с соответствующим тегом, например `v0.6.1`. Это запустит сборку wheel/sdist, проверку метаданных и состава архивов, установку обоих пакетов в отдельные окружения и все тесты в Linux/Python 3.10 и 3.13 и Windows/Python 3.13. Ошибка на любом этапе блокирует загрузку. После успешной загрузки отдельно проверяется установка точной версии из PyPI.

Обычный push, сам по себе push тега, редактирование существующего релиза, черновик и prerelease пакет не публикуют. Wheel и sdist загружаются **в PyPI**; вложения GitHub Releases по-прежнему содержат только автоматические архивы исходников. Проверки для PR и push не имеют прав OIDC и не загружают пакет.

Для первой загрузки после настройки PyPI либо для повторного запуска до успешной загрузки откройте [Package and publish](https://github.com/sinzbtw/envlatch/actions/workflows/publish.yml) → **Run workflow**, выберите нужный тег с этим workflow и включите `publish`. По умолчанию `publish=false`: выполняются только проверки. Попытка загрузки с ветки `main` блокируется.

Версию в PyPI перезаписать нельзя; существующие файлы намеренно не пропускаются. При частичной загрузке сначала проверьте опубликованные файлы и ошибку. Если содержимое неверное, исправьте его и выпустите новую patch-версию; не перемещайте старый тег. При сбое финальной проверки установки пакет уже мог стать публичным. Команды локальной проверки приведены в английской части выше; они ничего не загружают.
