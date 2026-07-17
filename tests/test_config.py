#!/usr/bin/env python3
"""Assert-тест конфигурации и feature-флагов — без сети, без реальных кредов.
Запуск: python3 tests/test_config.py (или venv/bin/python3 tests/test_config.py)
"""
import json
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from h1bot.config import Binding, Config, load_bindings, load_config, parse_env_file  # noqa: E402

failures = []


def check(name: str, condition: bool):
    if condition:
        print(f"  ok: {name}")
    else:
        print(f"  FAIL: {name}")
        failures.append(name)


print("parse_env_file на .env.example")
env = parse_env_file(BASE_DIR / ".env.example")
check("TELEGRAM_BOT_TOKEN ключ присутствует и пуст по умолчанию", env.get("TELEGRAM_BOT_TOKEN") == "")
check("H1CLOUD_CLIENT_API_URL имеет дефолтное значение", env.get("H1CLOUD_CLIENT_API_URL") == "https://my.h1cloud.net")
check("комментарии не попадают как ключи", "тестовый_комментарий" not in env)

print("\nBinding — feature-флаги")
b_empty = Binding(h1cloud_server_id=1)
check("пустая привязка: gateway_sync выключен", b_empty.gateway_sync_enabled is False)
check("пустая привязка: reality_apply выключен", b_empty.reality_apply_enabled is False)

b_gateway = Binding(h1cloud_server_id=2, remnawave_host_uuid="x")
check("привязка с host_uuid: gateway_sync включён", b_gateway.gateway_sync_enabled is True)
check("привязка с host_uuid без остального: reality_apply выключен", b_gateway.reality_apply_enabled is False)

b_full = Binding(h1cloud_server_id=3, remnawave_host_uuid="x", remnawave_profile_uuid="p", remnawave_node_uuid="n", reality_inbound_tag="t")
check("полная привязка: reality_apply включён", b_full.reality_apply_enabled is True)

print("\nConfig — feature-флаги при разных комбинациях")
cfg_empty = Config()
check("пустой Config: h1cloud_client выключен", cfg_empty.h1cloud_client_enabled is False)
check("пустой Config: remnawave выключен", cfg_empty.remnawave_enabled is False)
check("пустой Config: gateway_bindings пуст", cfg_empty.gateway_bindings == [])

cfg_with_bindings_no_rw = Config(bindings=[b_gateway])
check("bindings есть, но Remnawave не настроен -> gateway_bindings пуст", cfg_with_bindings_no_rw.gateway_bindings == [])

cfg_full = Config(
    remnawave_api_url="https://rw.example.com/api",
    remnawave_api_token="tok",
    bindings=[b_empty, b_gateway, b_full],
)
check("Remnawave настроен: только привязки с host_uuid попадают в gateway_bindings", len(cfg_full.gateway_bindings) == 2)
check("binding_for находит привязку по id", cfg_full.binding_for(3) is b_full)
check("binding_for возвращает None для неизвестного id", cfg_full.binding_for(999) is None)

print("\nload_bindings из временного файла")
with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "bindings.json"
    path.write_text(json.dumps([
        {"h1cloud_server_id": 10, "remnawave_host_uuid": "abc"},
        {"_comment": "мусорная запись без h1cloud_server_id — должна быть проигнорирована"},
    ]), encoding="utf-8")
    loaded = load_bindings(path)
    check("загружена ровно 1 валидная привязка", len(loaded) == 1)
    check("значение h1cloud_server_id корректно распарсено", loaded[0].h1cloud_server_id == 10)

print("\nload_config: переменные окружения перекрывают .env")
with tempfile.TemporaryDirectory() as tmp:
    env_path = Path(tmp) / ".env"
    env_path.write_text("TELEGRAM_BOT_TOKEN=from_file\nADMIN_IDS=111,222\n", encoding="utf-8")
    bindings_path = Path(tmp) / "bindings.json"
    bindings_path.write_text("[]", encoding="utf-8")

    cfg = load_config(env_path, bindings_path)
    check("токен читается из .env", cfg.telegram_bot_token == "from_file")
    check("ADMIN_IDS парсится в список int", cfg.admin_ids == [111, 222])

    import os
    os.environ["TELEGRAM_BOT_TOKEN"] = "from_env"
    try:
        cfg2 = load_config(env_path, bindings_path)
        check("переменная окружения имеет приоритет над .env", cfg2.telegram_bot_token == "from_env")
    finally:
        del os.environ["TELEGRAM_BOT_TOKEN"]

print()
if failures:
    print(f"❌ {len(failures)} проверок провалено: {failures}")
    sys.exit(1)
print("✅ Все проверки прошли")
