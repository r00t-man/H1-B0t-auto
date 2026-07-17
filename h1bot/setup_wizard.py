#!/usr/bin/env python3
"""Интерактивный мастер установки — заполняет .env и (опционально) bindings.json.

Можно запускать повторно в любой момент, чтобы дозаполнить то, что пропустили
в первый раз — существующие значения из .env подставляются по умолчанию
(Enter = оставить как есть). Всё, что мастер не заполнил, можно дописать
вручную прямо в .env/bindings.json — оба файла с подробными комментариями,
формат простой (KEY=value / обычный JSON).
"""
import getpass
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_EXAMPLE = BASE_DIR / ".env.example"
ENV_FILE = BASE_DIR / ".env"
BINDINGS_FILE = BASE_DIR / "bindings.json"

sys.path.insert(0, str(BASE_DIR))
from h1bot.config import parse_env_file  # noqa: E402


def ask(prompt: str, default: str = "", secret: bool = False) -> str:
    hint = " [задано]" if secret and default else (f" [{default}]" if default else "")
    full_prompt = f"{prompt}{hint}: "
    value = (getpass.getpass(full_prompt) if secret else input(full_prompt)).strip()
    return value if value else default


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    value = input(f"{prompt} {suffix}: ").strip().lower()
    if not value:
        return default
    return value in ("y", "yes", "д", "да")


def write_env(values: dict) -> None:
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    key_re = re.compile(r"^([A-Z0-9_]+)=")
    out = []
    for line in lines:
        m = key_re.match(line)
        out.append(f"{m.group(1)}={values[m.group(1)]}" if (m and m.group(1) in values) else line)
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    ENV_FILE.chmod(0o600)


def _test_h1cloud_key(base_url: str, api_key: str) -> None:
    try:
        import requests
        r = requests.get(f"{base_url}/api/v1/me", headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
        if r.status_code == 200:
            account = r.json().get("account", {})
            print(f"  ✅ Ключ рабочий, аккаунт: {account.get('username', '?')}, баланс: {account.get('balance', '?')}")
        else:
            print(f"  ⚠️ API ответил HTTP {r.status_code} — проверь ключ, но продолжаю установку.")
    except Exception as e:
        print(f"  ⚠️ Не удалось проверить ключ прямо сейчас ({e}) — не страшно, можно проверить позже.")


def _write_empty_bindings_if_missing() -> None:
    if not BINDINGS_FILE.exists():
        BINDINGS_FILE.write_text("[]\n", encoding="utf-8")
    print(f"{BINDINGS_FILE} можно заполнить вручную по образцу bindings.example.json в любой момент.")


def _pick_index(prompt: str, count: int):
    raw = input(prompt).strip()
    if not raw.isdigit():
        return None
    idx = int(raw) - 1
    return idx if 0 <= idx < count else None


def _bindings_wizard(values: dict) -> None:
    import requests
    from h1bot.h1cloud_client import H1CloudClientAPI

    h1client = H1CloudClientAPI(values["H1CLOUD_CLIENT_API_URL"], values["H1CLOUD_CLIENT_API_KEY"])

    try:
        servers = h1client.list_servers()
    except Exception as e:
        print(f"  ⚠️ Не удалось получить список h1cloud-серверов ({e}) — пропускаю автообнаружение.")
        _write_empty_bindings_if_missing()
        return

    try:
        r = requests.get(
            f"{values['REMNAWAVE_API_URL']}/hosts",
            headers={"Authorization": f"Bearer {values['REMNAWAVE_API_TOKEN']}"},
            timeout=15,
        )
        r.raise_for_status()
        hosts = r.json().get("response", r.json())
        if isinstance(hosts, dict):
            hosts = hosts.get("hosts", [])
    except Exception as e:
        print(f"  ⚠️ Не удалось получить список Remnawave-хостов ({e}) — пропускаю автообнаружение.")
        _write_empty_bindings_if_missing()
        return

    if not servers or not hosts:
        print("  Список серверов или хостов пуст — нечего связывать.")
        _write_empty_bindings_if_missing()
        return

    print("\n  h1cloud-серверы:")
    for i, s in enumerate(servers):
        print(f"   {i + 1}. #{s.get('id')} {s.get('name')}")
    print("\n  Remnawave-хосты:")
    for i, h in enumerate(hosts):
        print(f"   {i + 1}. {h.get('remark', h.get('address'))} ({h.get('address')})")

    bindings = []
    while ask_yes_no("\n  Добавить привязку?", len(bindings) == 0):
        srv_idx = _pick_index("  Номер h1cloud-сервера: ", len(servers))
        host_idx = _pick_index("  Номер Remnawave-хоста: ", len(hosts))
        if srv_idx is None or host_idx is None:
            print("  Некорректный номер, пропускаю эту привязку.")
            continue
        server, host = servers[srv_idx], hosts[host_idx]
        binding = {
            "h1cloud_server_id": server.get("id"),
            "label": server.get("name", ""),
            "remnawave_host_uuid": host.get("uuid"),
            "remnawave_profile_uuid": "",
            "remnawave_node_uuid": "",
            "reality_inbound_tag": "",
        }
        if ask_yes_no("  Настроить ещё и REALITY-перевыпуск (нужны uuid профиля/ноды и тег инбаунда)?", False):
            binding["remnawave_profile_uuid"] = ask("  UUID config-profile")
            binding["remnawave_node_uuid"] = ask("  UUID ноды")
            binding["reality_inbound_tag"] = ask("  Тег REALITY-инбаунда в конфиге")
        bindings.append(binding)
        print(f"  ✅ Привязано: #{server.get('id')} -> {host.get('address')}")

    BINDINGS_FILE.write_text(json.dumps(bindings, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Сохранено в {BINDINGS_FILE} ({len(bindings)} привязок)")


def main() -> None:
    existing = parse_env_file(ENV_FILE) if ENV_FILE.exists() else parse_env_file(ENV_EXAMPLE)
    values: dict = {}

    print("=" * 70)
    print("H1-B0t-auto — мастер установки")
    print("Enter без ввода = пропустить/оставить как есть. Всё это можно")
    print(f"позже поправить вручную в {ENV_FILE} и перезапустить: systemctl restart h1-b0t-auto")
    print("=" * 70)

    print("\n[1/7] Telegram — обязательно")
    print("Бот должен знать свой токен и кому разрешено нажимать кнопки.")
    values["TELEGRAM_BOT_TOKEN"] = ask("Токен бота (от @BotFather)", existing.get("TELEGRAM_BOT_TOKEN", ""))
    values["ADMIN_IDS"] = ask("Telegram id админов через запятую (узнать свой — у @userinfobot)", existing.get("ADMIN_IDS", ""))

    print("\n[2/7] H1cloud Client API — рекомендуется")
    print("Основной API: список серверов, живые метрики, питание, баланс,")
    print("продление, обновление ядра Xray, перевыпуск REALITY-ключей.")
    print("Получить ключ: залогинься на my.h1cloud.net -> my.h1cloud.net/api-docs")
    values["H1CLOUD_CLIENT_API_URL"] = existing.get("H1CLOUD_CLIENT_API_URL") or "https://my.h1cloud.net"
    values["H1CLOUD_CLIENT_API_KEY"] = ask("H1cloud Client API key (h1_...)", existing.get("H1CLOUD_CLIENT_API_KEY", ""), secret=True)
    if values["H1CLOUD_CLIENT_API_KEY"]:
        _test_h1cloud_key(values["H1CLOUD_CLIENT_API_URL"], values["H1CLOUD_CLIENT_API_KEY"])

    print("\n[3/7] H1cloud panel — логин сайта (опционально)")
    print("НЕ то же самое, что API-ключ выше. Нужны ТОЛЬКО для кнопки")
    print("«Создать новый конфиг» — у h1cloud нет API-эндпоинта для этого")
    print("действия, бот логинится как обычный пользователь через headless-браузер.")
    print("Без этого шага кнопка просто не появится в меню, остальное работает.")
    values["H1CLOUD_PANEL_LOGIN"] = ask("Логин my.h1cloud.net", existing.get("H1CLOUD_PANEL_LOGIN", ""))
    values["H1CLOUD_PANEL_PASSWORD"] = ask("Пароль my.h1cloud.net", existing.get("H1CLOUD_PANEL_PASSWORD", ""), secret=True)

    print("\n[4/7] H1cloud Pelican API — устаревший, опционально")
    print("Старый API прямого управления контейнером (panel.h1cloud.net).")
    print("Нужен только если нет доступа к новому Client API из пункта 2.")
    values["H1CLOUD_PELICAN_API_URL"] = existing.get("H1CLOUD_PELICAN_API_URL") or "https://panel.h1cloud.net"
    values["H1CLOUD_PELICAN_API_TOKEN"] = ask("Pelican API token (пусто = пропустить)", existing.get("H1CLOUD_PELICAN_API_TOKEN", ""), secret=True)

    print("\n[5/7] Remnawave — опционально")
    print("Нужно, только если хочешь, чтобы бот сам подставлял новый CDN-домен")
    print("и REALITY-ключи в Remnawave при ротации гейтвея у h1cloud-провайдера.")
    if ask_yes_no("Настроить интеграцию с Remnawave сейчас?", bool(existing.get("REMNAWAVE_API_URL"))):
        values["REMNAWAVE_API_URL"] = ask("URL панели Remnawave, включая /api (например https://panel.example.com/api)", existing.get("REMNAWAVE_API_URL", ""))
        values["REMNAWAVE_API_TOKEN"] = ask("API-токен Remnawave", existing.get("REMNAWAVE_API_TOKEN", ""), secret=True)
    else:
        values["REMNAWAVE_API_URL"] = existing.get("REMNAWAVE_API_URL", "")
        values["REMNAWAVE_API_TOKEN"] = existing.get("REMNAWAVE_API_TOKEN", "")

    values["GATEWAY_CHECK_INTERVAL"] = existing.get("GATEWAY_CHECK_INTERVAL") or "900"
    values["CHANNEL_CHECK_INTERVAL"] = existing.get("CHANNEL_CHECK_INTERVAL") or "300"

    write_env(values)
    print(f"\n✅ Сохранено в {ENV_FILE}")

    print("\n[6/7] Привязки h1cloud-серверов к Remnawave-хостам (bindings.json)")
    if values["REMNAWAVE_API_URL"] and values["REMNAWAVE_API_TOKEN"] and values["H1CLOUD_CLIENT_API_KEY"]:
        if ask_yes_no("Подтянуть списки серверов/хостов и настроить привязки интерактивно?", True):
            _bindings_wizard(values)
        else:
            _write_empty_bindings_if_missing()
    else:
        print("Пропущено — для автообнаружения нужны и h1cloud Client API, и Remnawave одновременно.")
        _write_empty_bindings_if_missing()

    print("\n[7/7] Автоклик при восстановлении LTE/гейтвея")
    print("При появлении в публичном канале провайдера t.me/h1cloud_status поста")
    print("о восстановлении доступа бот может САМ нажать «Создать новый конфиг».")
    print("⚠️ Необратимо — старый whitelist/CDN-конфиг умирает сразу. По умолчанию")
    print("ВЫКЛЮЧЕНО для всех серверов, включается позже прямо в меню бота (per-сервер).")

    print("\nГотово. После запуска сервиса смотри логи: journalctl -u h1-b0t-auto -f")


if __name__ == "__main__":
    main()
