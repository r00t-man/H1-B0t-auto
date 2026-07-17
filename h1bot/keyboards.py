"""Билдеры инлайн-клавиатур. Каждое меню собирается динамически — пункты,
для которых не хватает кредов/привязок, просто не появляются (деградация
функционала вместо падения)."""
from .telegram import button, keyboard


def kb_main_menu(config) -> dict:
    rows = []
    if config.h1cloud_client_enabled:
        rows.append([button("📋 Мои серверы", "srv_list")])
        rows.append([button("💰 Баланс", "balance")])
    if config.h1cloud_pelican_enabled:
        rows.append([button("🗄 Pelican-панель (устаревший API)", "pelican_list")])
    rows.append([button("📖 Помощь", "help")])
    return keyboard(rows)


def kb_back(callback_data: str = "menu") -> list:
    return [button("⬅️ Назад", callback_data)]


def kb_server_list(servers: list) -> dict:
    rows = [[button(f"{s.get('name', s.get('id'))} (#{s.get('id')})", f"srv:{s.get('id')}")] for s in servers]
    rows.append(kb_back())
    return keyboard(rows)


def kb_server_detail(config, server_id: int) -> dict:
    rows = [
        [button("▶️ Start", f"pwr:{server_id}:start"), button("⏸ Stop", f"pwr:{server_id}:stop"), button("🔄 Restart", f"pwr:{server_id}:restart")],
        [button("🧬 Обновить ядро Xray", f"xray_ask:{server_id}")],
        [button("💳 Продлить на 30 дней", f"renew_ask:{server_id}")],
    ]

    binding = config.binding_for(server_id)
    if binding and binding.gateway_sync_enabled:
        rows.append([button("🌐 Проверить/применить CDN-домен", f"sync_check:{server_id}")])
        rows.append([button("🩺 Диагностика", f"diag:{server_id}")])
    if binding and binding.reality_apply_enabled:
        rows.append([button("🔑 Перевыпустить REALITY-ключи", f"regen_ask:{server_id}")])
        rows.append([button("📥 Применить перевыпущенный ключ", f"apply_ask:{server_id}")])

    if config.browser_automation_enabled:
        rows.append([button("🌐 Создать новый конфиг (в панели)", f"newcfg_ask:{server_id}")])
        if binding and binding.gateway_sync_enabled:
            from . import channel_watch
            state_on = channel_watch.autoclick_enabled(server_id)
            label = "🟢 Автоклик при восстановлении: ВКЛ" if state_on else "🔴 Автоклик при восстановлении: ВЫКЛ"
            rows.append([button(label, f"autoclick_toggle:{server_id}")])

    rows.append(kb_back("srv_list"))
    return keyboard(rows)


def kb_confirm(confirm_callback: str, cancel_callback: str, confirm_label: str = "✅ Подтвердить") -> dict:
    return keyboard([[button(confirm_label, confirm_callback), button("❌ Отмена", cancel_callback)]])


def kb_pelican_list(servers: list) -> dict:
    rows = [[button(s.get("name", s.get("identifier")), f"pelican_srv:{s.get('identifier')}")] for s in servers]
    rows.append(kb_back())
    return keyboard(rows)


def kb_pelican_detail(identifier: str) -> dict:
    rows = [
        [button("▶️ Start", f"pelican_pwr:{identifier}:start"), button("⏸ Stop", f"pelican_pwr:{identifier}:stop"), button("🔄 Restart", f"pelican_pwr:{identifier}:restart")],
        kb_back("pelican_list"),
    ]
    return keyboard(rows)
