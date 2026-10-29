# Security Policy / Политика безопасности

[English](#english) | [Русский](#русский)

## English

### Supported versions

Security fixes target the latest published EnvLatch release. Older releases are not maintained separately; upgrade to the latest release when reporting or applying a fix. `main` is the development branch, not a stable release. This is a volunteer-maintained project, and reports are handled on a best-effort basis.

### Report a vulnerability privately

Use [Report a vulnerability](https://github.com/sinzbtw/envlatch/security/advisories/new) under **Security → Advisories**. Private vulnerability reporting is enabled for this repository. Reports go to repository maintainers through GitHub; sign-in is required.

Include the affected version/commit, Python version and OS, the impact, reproduction steps, and a minimal proof of concept using invented values. Relevant examples include unintended exposure of dotenv values, unsafe execution of input, or injection of additional GitHub Actions commands.

Do not publish a suspected vulnerability in a public issue or PR, attach real `.env` files, include active credentials, or test against systems you do not have permission to use. If a credential was exposed, revoke or rotate it through the service that issued it; EnvLatch cannot invalidate credentials.

The maintainer will assess the report, discuss a correction and any advisory with the reporter, and coordinate disclosure. Ordinary bugs without security impact and feature requests should use the [public issue forms](https://github.com/sinzbtw/envlatch/issues/new/choose). Community conduct concerns follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Русский

### Поддерживаемые версии

Исправления безопасности предназначены для последнего опубликованного выпуска EnvLatch. Старые выпуски отдельно не поддерживаются; при сообщении об ошибке или установке исправления обновитесь до последней версии. `main` — ветка разработки, а не стабильный выпуск. Проект поддерживается на добровольной основе; обращения обрабатываются по мере возможностей.

### Приватно сообщить об уязвимости

Используйте [Report a vulnerability](https://github.com/sinzbtw/envlatch/security/advisories/new) в разделе **Security → Advisories**. Приватные сообщения об уязвимостях включены для этого репозитория. Обращения поступают владельцам репозитория через GitHub; требуется вход в аккаунт.

Укажите затронутую версию/коммит, версию Python и ОС, последствия, шаги воспроизведения и минимальный пример с вымышленными значениями. Например: непреднамеренный вывод значений dotenv, небезопасное выполнение входных данных или внедрение дополнительных команд GitHub Actions.

Не публикуйте возможную уязвимость в открытом Issue или PR, не прикладывайте реальные `.env` и действующие учётные данные и не проверяйте чужие системы без разрешения. Если секрет раскрыт, отзовите или замените его в сервисе, который его выдал: EnvLatch не может аннулировать учётные данные.

Владелец проекта оценит обращение, обсудит с автором исправление и возможный advisory и согласует раскрытие информации. Обычные ошибки без последствий для безопасности и предложения функций отправляйте через [открытые формы Issues](https://github.com/sinzbtw/envlatch/issues/new/choose). Вопросы поведения участников регулируются [правилами общения](CODE_OF_CONDUCT.md#русский).
