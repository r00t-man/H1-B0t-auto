# H1-B0t-auto

Telegram-бот для управления парком серверов [h1cloud](https://h1cloud.net) прямо из чата — список серверов, живые метрики, питание, продление аренды, обновление ядра Xray, перевыпуск REALITY-ключей, headless-клик «Создать новый конфиг» — плюс опциональная синхронизация CDN-гейтвея с панелью [Remnawave](https://remna.st) при его ротации на стороне провайдера.

Работает и без Remnawave (только управление h1cloud-серверами), и на голом сервере, и рядом с уже настроенной Remnawave-панелью.

## Что умеет

- **📋 Мои серверы** — список, живые метрики (CPU/RAM/аптайм), питание (старт/стоп/рестарт), баланс аккаунта, продление аренды.
- **🧬 Обновление ядра Xray** — программный эквивалент кнопки «Обновить ядро» в панели h1cloud.
- **🌐 Синхронизация CDN-гейтвея с Remnawave** *(опционально)* — при смене домена гейтвея на стороне провайдера бот сам подставляет новый адрес в Host-запись Remnawave, с TLS-проверкой перед применением.
- **🔑 Перевыпуск REALITY-ключей** *(опционально)* — скачивает новый ключ, точечно применяет только его (не весь ответ провайдера) в нужный inbound.
- **🌐 «Создать новый конфиг» одной кнопкой** *(опционально)* — у h1cloud нет API для этого действия, бот жмёт кнопку в панели сам через headless-браузер (Playwright).
- **🤖 Автоклик при восстановлении** *(опционально)* — следит за публичным каналом провайдера [t.me/h1cloud_status](https://t.me/h1cloud_status) и сам жмёт «Создать новый конфиг», когда провайдер объявляет о восстановлении доступа.
- **🗄 Legacy Pelican API** *(опционально)* — старый API прямого управления контейнером, для аккаунтов без доступа к новому Client API.

Всё опциональное — просто не появляется в меню, пока не настроено. Ничего не падает из-за нехватки одного из ключей.

## Требования

- Ubuntu/Debian (apt) или RHEL/Fedora (dnf/yum) сервер, root-доступ.
- Telegram-бот — создать через [@BotFather](https://t.me/BotFather).
- Аккаунт h1cloud (для основного функционала).
- Remnawave-панель — только если нужна синхронизация CDN-гейтвея.

## Установка

```bash
git clone git@github.com:r00t-man/H1-B0t-auto.git
cd H1-B0t-auto
sudo bash install.sh
```

Скрипт сам:
1. Ставит `python3`, `python3-venv`, `python3-pip`.
2. Создаёт venv и ставит зависимости (`requests`, `playwright`).
3. Запускает интерактивный мастер настройки (`h1bot/setup_wizard.py`) — по каждому пункту объясняет, зачем он нужен, `Enter` = пропустить.
4. Если указан логин панели h1cloud — ставит Chromium для Playwright (`playwright install --with-deps chromium`, ~300 МБ, один раз).
5. Генерирует и включает systemd-сервис `h1-b0t-auto`.

Повторный запуск `install.sh` безопасен — существующие `.env`/`bindings.json` не затираются молча, мастер предложит текущие значения по умолчанию.

## Конфигурация

Два файла в корне проекта (ни один не коммитится в git — см. `.gitignore`):

- **`.env`** — секреты и простые настройки. Полный образец со всеми переменными и объяснением, зачем нужна каждая — `.env.example`. Можно редактировать вручную в любой момент, затем `systemctl restart h1-b0t-auto`.
- **`bindings.json`** — список привязок «какой h1cloud-сервер → какой Remnawave-хост» (для синхронизации CDN-гейтвея). Формат и пример — `bindings.example.json`. Может быть пустым списком `[]`, если синхронизация с Remnawave не нужна.

### Таблица переменных `.env`

| Переменная | Обязательна | Зачем |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | да | Токен бота от @BotFather. |
| `ADMIN_IDS` | да | Telegram id через запятую — кому разрешено пользоваться ботом. |
| `H1CLOUD_CLIENT_API_KEY` | нет | Bearer-ключ (`h1_...`) из `my.h1cloud.net/api-docs` — основной API: список серверов, метрики, питание, баланс, продление, обновление ядра, перевыпуск ключей. |
| `H1CLOUD_PANEL_LOGIN` / `H1CLOUD_PANEL_PASSWORD` | нет | Логин/пароль сайта `my.h1cloud.net` (НЕ API-ключ) — нужны только для headless-клика «Создать новый конфиг», у h1cloud нет API для этого действия. |
| `H1CLOUD_PELICAN_API_TOKEN` | нет | Токен старой панели `panel.h1cloud.net` — фолбэк для аккаунтов без доступа к Client API. |
| `REMNAWAVE_API_URL` / `REMNAWAVE_API_TOKEN` | нет | URL и токен твоей панели Remnawave — включает синхронизацию CDN-гейтвея/REALITY-ключей. |
| `GATEWAY_CHECK_INTERVAL` | нет (900) | Как часто (сек) проверять смену CDN-домена у привязанных серверов. |
| `CHANNEL_CHECK_INTERVAL` | нет (300) | Как часто (сек) проверять новые посты в `t.me/h1cloud_status`. |

### Формат `bindings.json`

```json
[
  {
    "h1cloud_server_id": 1234,
    "label": "Например: EU-Gateway-1",
    "remnawave_host_uuid": "...",
    "remnawave_profile_uuid": "",
    "remnawave_node_uuid": "",
    "reality_inbound_tag": ""
  }
]
```

`remnawave_host_uuid` — обязателен для синхронизации CDN-домена. `remnawave_profile_uuid`/`remnawave_node_uuid`/`reality_inbound_tag` — опциональны, нужны только для кнопки применения перевыпущенных REALITY-ключей. Мастер установки может собрать этот файл интерактивно (подтягивает списки серверов/хостов через API и даёт выбрать пары), либо заполни вручную по этому образцу.

## Архитектура

Один процесс, сырые HTTP-запросы к Telegram Bot API через `requests` (без `python-telegram-bot`/`aiogram`) — long-polling `getUpdates` + периодические фоновые проверки в том же цикле. Стейт (курсоры каналов, флаги автоклика, бэкапы перевыпущенных ключей) — плоские файлы в `state/`, без базы данных.

```
bot.py               — точка входа
h1bot/
  config.py          — .env + bindings.json → Config с feature-флагами
  state.py           — файловый key-value стейт
  telegram.py        — обёртка над Bot API
  h1cloud_client.py  — H1cloud Client API v1
  h1cloud_pelican.py — H1cloud Pelican API (legacy)
  h1cloud_browser.py — Playwright-автоматизация «Создать новый конфиг»
  remnawave_client.py— минимальный клиент Remnawave (host/config-profile/node)
  gateway_sync.py     — синхронизация CDN-домена + REALITY-ключей по bindings
  channel_watch.py    — мониторинг t.me/h1cloud_status + автоклик
  keyboards.py / handlers.py — меню и роутинг callback'ов (паттерн ask/go)
  app.py              — главный цикл
  setup_wizard.py      — интерактивный установщик
```

## Безопасность

- `.env`/`bindings.json`/`state/` — в `.gitignore`, никогда не коммитятся.
- Бот отвечает только пользователям из `ADMIN_IDS`, всем остальным — «доступ запрещён».
- Необратимые действия (перевыпуск ключей, headless-клик «Создать новый конфиг», обновление ядра) требуют явного подтверждения кнопкой.
- `TELEGRAM_BOT_TOKEN`/`H1CLOUD_CLIENT_API_KEY`/пароли панели — в `.env` с правами `600`.

## Проверка

```bash
python3 tests/test_config.py     # assert-тест парсинга конфига и feature-флагов, без сети
python3 -m py_compile bot.py h1bot/*.py   # синтаксическая проверка
```

## Лицензия

MIT — см. [LICENSE](LICENSE).
