"""Билдеры инлайн-клавиатур. Все пункты меню показываются всегда, независимо
от того, заполнены ли под них креды/привязки — если данных не хватает,
обработчик в handlers.py при нажатии покажет, что именно и в каком файле
нужно дозаполнить, вместо того чтобы прятать кнопку."""
from .telegram import button, keyboard


def kb_main_menu(config) -> dict:
    rows = [
        [button("📋 Мои серверы", "srv_list")],
        [button("💰 Баланс", "balance")],
        [button("🗄 Pelican-панель (устаревший API)", "pelican_list")],
        [button("📖 Помощь", "help")],
    ]
    return keyboard(rows)


def kb_back(callback_data: str = "menu") -> list:
    return [button("⬅️ Назад", callback_data)]


def kb_server_list(servers: list) -> dict:
    rows = [[button(f"{s.get('name', s.get('id'))} (#{s.get('id')})", f"srv:{s.get('id')}")] for s in servers]
    rows.append(kb_back())
    return keyboard(rows)


def kb_server_detail(config, server_id: int) -> dict:
    from . import channel_watch

    state_on = channel_watch.autoclick_enabled(server_id)
    autoclick_label = "🟢 Автоклик при восстановлении: ВКЛ" if state_on else "🔴 Автоклик при восстановлении: ВЫКЛ"

    rows = [
        [button("▶️ Start", f"pwr:{server_id}:start"), button("⏸ Stop", f"pwr:{server_id}:stop"), button("🔄 Restart", f"pwr:{server_id}:restart")],
        [button("🧬 Обновить ядро Xray", f"xray_ask:{server_id}")],
        [button("💳 Продлить на 30 дней", f"renew_ask:{server_id}")],
        [button("🌐 Проверить/применить CDN-домен", f"sync_check:{server_id}")],
        [button("🩺 Диагностика", f"diag:{server_id}")],
        [button("🔑 Перевыпустить REALITY-ключи", f"regen_ask:{server_id}")],
        [button("📥 Применить перевыпущенный ключ", f"apply_ask:{server_id}")],
        [button("🌐 Создать новый конфиг (в панели)", f"newcfg_ask:{server_id}")],
        [button(autoclick_label, f"autoclick_toggle:{server_id}")],
    ]
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
