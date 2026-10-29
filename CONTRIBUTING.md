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

The parser and contract checks are in `src/envlatch/core.py`; output formats and CLI handling are in `src/envlatch/cli.py`; behavioral tests are in `tests/`. There are no runtime dependencies.

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

Парсер и проверки контракта находятся в `src/envlatch/core.py`, обработка CLI и форматы вывода — в `src/envlatch/cli.py`, поведенческие тесты — в `tests/`. Зависимостей для запуска нет.

### Предложить изменение

- Делайте отдельное изменение по одной задаче. В шаблоне PR опишите проблему и итоговое поведение, приложите ссылку на связанный Issue, если он есть.
- При изменении поведения добавляйте регрессионный тест пользовательского сценария, в том числе безопасной обработки секретов, если это относится к задаче. Перед отправкой запускайте связанные тесты и полный набор. Для изменений только документации проверьте ссылки и примеры и поясните, почему тесты программы неприменимы.
- Поддерживайте одинаковую информацию в `README.md` и `README.ru.md`. Изменения поведения для пользователей отражайте в `CHANGELOG.md`.
- Сохраняйте коды завершения, воспроизводимость вывода, совместимость схемы JSON, поддержку Python 3.10 и отсутствие значений dotenv в диагностике. Изменения совместимости обсуждайте явно.
- Держите инструменты сборки в окружении проекта и добавляйте зависимости для запуска только при необходимости, поясняя причину. Не коммитьте `.env`, виртуальные окружения, результаты сборки и реальные секреты.

GitHub Actions проверяет Linux и Windows. Версиями и выпусками управляет владелец проекта; в GitHub Releases публикуются только архивы исходников по тегу, без wheel и файлов контрольных сумм. Вклады в проект предоставляются по [лицензии MIT](LICENSE).
