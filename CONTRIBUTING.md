# Contributing to EnvLatch / Участие в разработке

[English](#english) | [Русский](#русский)

## English

Bug reports, documentation improvements, focused fixes, and useful features are welcome. Follow the [Code of Conduct](CODE_OF_CONDUCT.md).

### Report a problem or propose a feature

Use the [issue forms](https://github.com/sinzbtw/envlatch/issues/new/choose) after checking existing issues. Reports can be written in English or Russian.

For a bug, include `envlatch --version`, Python version, operating system, the command, expected and actual behavior, and a minimal template/environment example with invented values. Replace private paths or sensitive names when necessary. Never attach real `.env` files, credentials, access tokens, or unredacted private logs.

For a feature, describe the real problem, a proposed command or API, and relevant alternatives. Suspected vulnerabilities belong in the [private security reporting process](SECURITY.md), not public issues.

### Local development

Python 3.10 or newer and Git are required. Clone the repository and create a project-local virtual environment:

```sh
git clone https://github.com/sinzbtw/envlatch.git
cd envlatch
python -m venv .venv
```

Activate it with `.\.venv\Scripts\Activate.ps1` in Windows PowerShell, or `source .venv/bin/activate` on Linux/macOS. Then run:

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
python -m pip check
```

The parser and contract checks are in `src/envlatch/core.py`; literal type predicates are in `src/envlatch/_types.py`; standard CLI handling is in `src/envlatch/cli.py`. Independent-environment comparison, its configuration and output live in `compare.py`, `compare_config.py` and `compare_cli.py` under `src/envlatch/`. Shared JSON settings are loaded by `src/envlatch/config.py`; behavioral tests are in `tests/`. There are no runtime dependencies.

### Quality checks

Development tools require Python **3.11+** (CI uses 3.13); EnvLatch and its ordinary tests still support Python 3.10. Install the pinned tools and check formatting/lint:

```sh
python -m pip install -r requirements/requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
```

`python -m ruff format .` applies formatting locally. Before measuring coverage, set absolute paths so CLI processes running in temporary directories contribute to the same report:

```powershell
# Windows PowerShell
$env:COVERAGE_FILE = "$PWD/.coverage"
$env:COVERAGE_RCFILE = "$PWD/pyproject.toml"
```

```sh
# Linux / macOS
export COVERAGE_FILE="$PWD/.coverage"
export COVERAGE_RCFILE="$PWD/pyproject.toml"
```

Then run:

```sh
python -m coverage erase
python -m coverage run -m unittest discover -s tests -q
python -m coverage combine
python -m coverage report -m
python -m coverage html
```

Quality checks require at least **98%** coverage, including branches and CLI subprocesses. CI provides a summary and a downloadable HTML/XML `coverage-report` artifact. The same checks gate PyPI uploads. Development tools are not runtime dependencies.

Dependabot proposes weekly updates to Actions and development tools, grouping minor/patch releases. Major updates remain separate; a maintainer merges bot PRs after checks. GitHub-managed CodeQL scans Python/Actions on pushes, PRs and weekly.

### Submit a change

- Keep the change focused and explain the problem and resulting behavior in the PR template. Link a related issue when one exists.
- For behavior changes, add a regression test covering the user-visible case, including safe handling of secrets where relevant. Run the relevant tests and the full suite before submission. For documentation-only changes, check links and examples and explain why runtime tests are not applicable.
- Keep `README.md` and `README.ru.md` consistent. Update `CHANGELOG.md` for user-visible behavior changes.
- Preserve exit-code behavior, deterministic output, JSON schema compatibility, Python 3.10 support, and the rule that dotenv values never appear in diagnostics. Discuss compatibility changes explicitly.
- Keep build tools inside the project's environment and avoid new runtime dependencies unless necessary and explained. Do not commit `.env`, virtual environments, build output, or real secrets.

GitHub Actions checks Linux and Windows. The maintainer manages versions and releases; GitHub Releases contain tagged source archives only, without wheel or checksum attachments. Contributions are provided under the repository's [MIT license](LICENSE).

## Русский

Сообщения об ошибках, улучшения документации, точечные исправления и полезные функции приветствуются. Соблюдайте [правила общения](CODE_OF_CONDUCT.md#русский).

### Сообщить о проблеме или предложить функцию

Сначала проверьте существующие Issues, затем используйте [формы обращений](https://github.com/sinzbtw/envlatch/issues/new/choose). Можно писать по-русски или по-английски.

Для ошибки укажите `envlatch --version`, версию Python, ОС, команду, ожидаемый и фактический результат и минимальный пример шаблона/окружения с вымышленными значениями. При необходимости замените приватные пути и чувствительные имена. Не прикладывайте реальные `.env`, учётные данные, токены доступа и неочищенные приватные логи.

Для новой функции опишите реальную задачу, предлагаемые команду или API и подходящие альтернативы. О возможных уязвимостях сообщайте [приватно по политике безопасности](SECURITY.md#русский), а не через открытый Issue.

### Локальная разработка

Нужны Python 3.10 или новее и Git. Клонируйте репозиторий и создайте виртуальное окружение внутри проекта:

```sh
git clone https://github.com/sinzbtw/envlatch.git
cd envlatch
python -m venv .venv
```

Активируйте его командой `.\.venv\Scripts\Activate.ps1` в Windows PowerShell или `source .venv/bin/activate` в Linux/macOS. Затем выполните:

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
python -m pip check
```

Парсер и проверки контракта находятся в `src/envlatch/core.py`, проверки буквальных типов — в `src/envlatch/_types.py`, обычный CLI — в `src/envlatch/cli.py`. Сравнение независимых окружений, его конфиг и вывод находятся в `compare.py`, `compare_config.py` и `compare_cli.py` внутри `src/envlatch/`. Общие JSON-настройки загружаются в `src/envlatch/config.py`, поведенческие тесты — в `tests/`. Зависимостей для запуска нет.

### Проверки качества

Для инструментов разработки нужен Python **3.11+** (в CI — 3.13); EnvLatch и обычные тесты сохраняют поддержку Python 3.10. Установите инструменты из `requirements/requirements-dev.txt`, затем запустите `python -m ruff check .` и `python -m ruff format --check .`. Применить оформление можно командой `python -m ruff format .`.

Команды измерения покрытия и настройки путей для PowerShell/Linux приведены в [Quality checks](#quality-checks). Покрытие учитывает ветвления и отдельные процессы CLI; порог — **98%**. В CI доступны сводка и архив `coverage-report` с HTML/XML. Те же проверки выполняются перед загрузкой в PyPI. Инструменты разработки не становятся зависимостями пакета для пользователей.

Dependabot раз в неделю предлагает обновления Actions и инструментов разработки, объединяя небольшие обновления. Major-обновления предлагаются отдельно; PR бота сливает сопровождающий после проверок. CodeQL проверяет Python и GitHub Actions при push/PR и еженедельно через стандартную настройку GitHub.

### Предложить изменение

- Делайте отдельное изменение по одной задаче. В шаблоне PR опишите проблему и итоговое поведение, приложите ссылку на связанный Issue, если он есть.
- При изменении поведения добавляйте регрессионный тест пользовательского сценария, в том числе безопасной обработки секретов, если это относится к задаче. Перед отправкой запускайте связанные тесты и полный набор. Для изменений только документации проверьте ссылки и примеры и поясните, почему тесты программы неприменимы.
- Поддерживайте одинаковую информацию в `README.md` и `README.ru.md`. Изменения поведения для пользователей отражайте в `CHANGELOG.md`.
- Сохраняйте коды завершения, воспроизводимость вывода, совместимость схемы JSON, поддержку Python 3.10 и отсутствие значений dotenv в диагностике. Изменения совместимости обсуждайте явно.
- Держите инструменты сборки в окружении проекта и добавляйте зависимости для запуска только при необходимости, поясняя причину. Не коммитьте `.env`, виртуальные окружения, результаты сборки и реальные секреты.

GitHub Actions проверяет Linux и Windows. Версиями и выпусками управляет владелец проекта; в GitHub Releases публикуются только архивы исходников по тегу, без wheel и файлов контрольных сумм. Вклады в проект предоставляются по [лицензии MIT](LICENSE).
