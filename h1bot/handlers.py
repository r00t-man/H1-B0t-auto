"""Роутинг callback_query/message + паттерн `_ask`/`_go` для опасных действий:
callback `X_ask:{arg}` рендерит предупреждение с кнопками ✅/❌, отдельный
`X_go:{arg}` выполняет само действие — простой и понятный барьер перед
необратимыми операциями.
"""
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from . import channel_watch, gateway_sync, keyboards, state
from .config import Config
from .h1cloud_browser import click_new_config
from .h1cloud_client import H1CloudClientAPI, save_json_backup
from .h1cloud_pelican import H1CloudPelicanAPI
from .notify import notify_admins, notify_other_admins
from .remnawave_client import RemnawaveClient
from .telegram import TelegramClient

logger = logging.getLogger("h1bot.handlers")

HELP_TEXT = (
    "<b>H1-B0t-auto</b> — управление h1cloud-серверами из Telegram.\n\n"
    "📋 <b>Мои серверы</b> — список, живые метрики, питание, обновление ядра Xray, продление аренды.\n"
    "🌐 <b>Синхронизация CDN-гейтвея</b> с Remnawave — проверка/применение нового домена, "
    "перевыпуск и точечное применение REALITY-ключей.\n"
    "🤖 <b>Автоклик</b> — при появлении в публичном канале провайдера поста о восстановлении доступа "
    "бот сам нажимает «Создать новый конфиг» и применяет новый домен.\n\n"
    "Все кнопки в меню видны сразу. Если для какой-то не хватает данных — при нажатии "
    "бот покажет, чего именно и в каком файле не хватает.\n\n"
    "<b>Что где настраивается (файл .env):</b>\n"
    "• 📋 Серверы / 💰 Баланс / ⏻ питание / 🧬 ядро Xray / 💳 продление / 🔑 REALITY-перевыпуск\n"
    "  ↳ <code>H1CLOUD_CLIENT_API_KEY</code> (my.h1cloud.net → my.h1cloud.net/api-docs)\n"
    "• 🗄 Pelican-панель (устаревший API)\n"
    "  ↳ <code>H1CLOUD_PELICAN_API_TOKEN</code> (panel.h1cloud.net)\n"
    "• 🌐 Создать новый конфиг / 🤖 Автоклик\n"
    "  ↳ <code>H1CLOUD_PANEL_LOGIN</code> + <code>H1CLOUD_PANEL_PASSWORD</code>\n"
    "• 🌐 CDN-домен / 🩺 Диагностика / 📥 Применить REALITY-ключ\n"
    "  ↳ <code>REMNAWAVE_API_URL</code> + <code>REMNAWAVE_API_TOKEN</code>\n\n"
    "<b>Привязка конкретного сервера (файл bindings.json):</b>\n"
    "• <code>remnawave_host_uuid</code> — для CDN-sync/диагностики/автоклика\n"
    "• <code>remnawave_profile_uuid</code> + <code>remnawave_node_uuid</code> + <code>reality_inbound_tag</code> "
    "— для перевыпуска/применения REALITY-ключей\n\n"
    "Проще всего заполнить всё мастером: <code>python3 h1bot/setup_wizard.py</code> — "
    "шаг [6/7] сам подтянет списки серверов/хостов и предложит выбрать привязки, не вводя UUID руками."
)


@dataclass
class Context:
    config: Config
    tg: TelegramClient
    h1client: H1CloudClientAPI = None
    pelican: H1CloudPelicanAPI = None
    rw: RemnawaveClient = None

    @classmethod
    def build(cls, config: Config) -> "Context":
        tg = TelegramClient(config.telegram_bot_token)
        h1client = (
            H1CloudClientAPI(config.h1cloud_client_api_url, config.h1cloud_client_api_key)
            if config.h1cloud_client_enabled else None
        )
        pelican = (
            H1CloudPelicanAPI(config.h1cloud_pelican_api_url, config.h1cloud_pelican_api_token)
            if config.h1cloud_pelican_enabled else None
        )
        rw = (
            RemnawaveClient(config.remnawave_api_url, config.remnawave_api_token)
            if config.remnawave_enabled else None
        )
        return cls(config=config, tg=tg, h1client=h1client, pelican=pelican, rw=rw)

    def is_admin(self, user_id) -> bool:
        return int(user_id) in self.config.admin_ids

    def notify_admins(self, text: str) -> None:
        notify_admins(self.tg, self.config.admin_ids, text)

    def notify_other_admins(self, triggering_chat_id, text: str) -> None:
        notify_other_admins(self.tg, self.config.admin_ids, triggering_chat_id, text)


def _config_error(tg: TelegramClient, chat_id, message_id, back_cb: str, title: str, items: list) -> None:
    """Красиво оформленное сообщение о нехватке настроек: что и в каком файле дозаполнить."""
    lines = [f"⚠️ <b>{title}</b>", "", "Не хватает настроек для этой кнопки:"]
    for what, where in items:
        lines.append(f"• <b>{what}</b>\n  ↳ <code>{where}</code>")
    lines += ["", "Заполни и перезапусти бота: <code>systemctl restart h1-b0t-auto</code>",
              "Проще всего — мастером: <code>python3 h1bot/setup_wizard.py</code>"]
    tg.edit_message(chat_id, message_id, "\n".join(lines), reply_markup=keyboards.keyboard([keyboards.kb_back(back_cb)]))


def _regenerate_backup_path(server_id: int) -> Path:
    return state.STATE_DIR / f"regenerate_{server_id}.json"


def _server_detail_text(ctx: Context, server: dict, stats: dict) -> str:
    binding = ctx.config.binding_for(server.get("id"))
    lines = [
        f"<b>{server.get('name')}</b> (#{server.get('id')})",
        f"Тариф: {server.get('tariff_name', '—')}, цена: {server.get('price', '—')}",
        f"До окончания: {server.get('days_left', '—')} дн. ({server.get('expiration_date', '—')})",
        "",
        f"Состояние: {stats.get('state', '—')}",
        f"Аптайм: {stats.get('uptime', '—')}",
        f"CPU: {stats.get('cpu_percent', '—')}%, RAM: {stats.get('memory_mb', '—')} MB",
    ]
    if binding:
        lines += ["", f"🔗 Привязан к Remnawave: {binding.label or binding.remnawave_host_uuid}"]
    return "\n".join(lines)


def _show_server(ctx: Context, chat_id, message_id, server_id: int) -> None:
    server = next((s for s in ctx.h1client.list_servers() if int(s.get("id")) == server_id), None)
    if server is None:
        ctx.tg.edit_message(chat_id, message_id, "Сервер не найден.", reply_markup=keyboards.keyboard([keyboards.kb_back("srv_list")]))
        return
    stats = ctx.h1client.server_stats(server_id)
    ctx.tg.edit_message(
        chat_id, message_id,
        _server_detail_text(ctx, server, stats),
        reply_markup=keyboards.kb_server_detail(ctx.config, server_id),
    )


def handle_callback(ctx: Context, update: dict) -> None:
    cq = update["callback_query"]
    data = cq.get("data", "")
    chat_id = cq["message"]["chat"]["id"]
    message_id = cq["message"]["message_id"]
    user_id = cq["from"]["id"]

    ctx.tg.answer_callback_query(cq["id"])

    if not ctx.is_admin(user_id):
        ctx.tg.edit_message(chat_id, message_id, "⛔ Доступ запрещён.")
        return

    try:
        _route(ctx, data, chat_id, message_id, user_id)
    except Exception as e:
        logger.exception("callback handling failed: %s", data)
        ctx.tg.edit_message(chat_id, message_id, f"❌ Ошибка: <code>{e}</code>", reply_markup=keyboards.kb_main_menu(ctx.config))


def _route(ctx: Context, data: str, chat_id, message_id, user_id) -> None:
    tg = ctx.tg

    if data == "menu":
        tg.edit_message(chat_id, message_id, "🛸 H1-B0t-auto", reply_markup=keyboards.kb_main_menu(ctx.config))
        return

    if data == "help":
        tg.edit_message(chat_id, message_id, HELP_TEXT, reply_markup=keyboards.keyboard([keyboards.kb_back()]))
        return

    action = data.split(":", 1)[0]

    if action in ("balance", "srv_list", "srv", "pwr", "xray_ask", "xray_go", "renew_ask", "renew_go", "regen_ask", "regen_go"):
        if ctx.h1client is None:
            _config_error(
                tg, chat_id, message_id, "menu",
                "H1cloud Client API не настроен",
                [("H1cloud Client API key", ".env → H1CLOUD_CLIENT_API_KEY (получить: my.h1cloud.net → my.h1cloud.net/api-docs)")],
            )
            return

    if action in ("pelican_list", "pelican_srv", "pelican_pwr"):
        if ctx.pelican is None:
            _config_error(
                tg, chat_id, message_id, "menu",
                "H1cloud Pelican API не настроен",
                [("Pelican API token", ".env → H1CLOUD_PELICAN_API_TOKEN (panel.h1cloud.net, устаревший API)")],
            )
            return

    if action in ("sync_check", "diag", "apply_ask", "apply_go"):
        server_id = int(data.split(":")[1])
        binding = ctx.config.binding_for(server_id)
        needs_reality = action in ("apply_ask", "apply_go")
        binding_ok = bool(binding and (binding.reality_apply_enabled if needs_reality else binding.gateway_sync_enabled))
        if ctx.rw is None or not binding_ok:
            missing = []
            if ctx.rw is None:
                missing.append(("Remnawave API", ".env → REMNAWAVE_API_URL и REMNAWAVE_API_TOKEN"))
            if not binding_ok:
                if needs_reality:
                    missing.append((
                        f"Привязка сервера #{server_id} к профилю/ноде REALITY",
                        f"bindings.json → запись с h1cloud_server_id={server_id}: remnawave_profile_uuid, remnawave_node_uuid, reality_inbound_tag",
                    ))
                else:
                    missing.append((
                        f"Привязка сервера #{server_id} к Remnawave-хосту",
                        f"bindings.json → запись с h1cloud_server_id={server_id}: remnawave_host_uuid",
                    ))
            _config_error(tg, chat_id, message_id, f"srv:{server_id}", "Не настроена интеграция с Remnawave для этого сервера", missing)
            return

    if action in ("newcfg_ask", "newcfg_go", "autoclick_toggle"):
        server_id = int(data.split(":")[1])
        if not ctx.config.browser_automation_enabled:
            _config_error(
                tg, chat_id, message_id, f"srv:{server_id}",
                "Логин панели h1cloud не настроен",
                [("Логин и пароль my.h1cloud.net", ".env → H1CLOUD_PANEL_LOGIN и H1CLOUD_PANEL_PASSWORD")],
            )
            return
        if action == "autoclick_toggle":
            binding = ctx.config.binding_for(server_id)
            if not (binding and binding.gateway_sync_enabled):
                _config_error(
                    tg, chat_id, message_id, f"srv:{server_id}",
                    "Автоклик требует привязки к Remnawave-хосту",
                    [(f"Привязка сервера #{server_id}", f"bindings.json → запись с h1cloud_server_id={server_id}: remnawave_host_uuid")],
                )
                return

    if data == "balance":
        account = ctx.h1client.account()
        text = f"💰 Аккаунт: {account.get('username', '—')}\nБаланс: {account.get('balance', '—')}\nСерверов: {account.get('servers_total', '—')}"
        tg.edit_message(chat_id, message_id, text, reply_markup=keyboards.keyboard([keyboards.kb_back()]))
        return

    if data == "srv_list":
        servers = ctx.h1client.list_servers()
        tg.edit_message(chat_id, message_id, "📋 Твои серверы:", reply_markup=keyboards.kb_server_list(servers))
        return

    if data.startswith("srv:"):
        _show_server(ctx, chat_id, message_id, int(data.split(":", 1)[1]))
        return

    if data.startswith("pwr:"):
        _, server_id, action = data.split(":")
        ctx.h1client.power(int(server_id), action)
        _show_server(ctx, chat_id, message_id, int(server_id))
        return

    # ── обновление ядра Xray ──
    if data.startswith("xray_ask:"):
        server_id = data.split(":", 1)[1]
        tg.edit_message(
            chat_id, message_id,
            "⚠️ <b>Опасный шаг.</b> Жёсткий рестарт ядра Xray, 2-3 минуты даунтайма. "
            "Не вызывай без необходимости — сначала посмотри 🩺 диагностику, если она доступна.",
            reply_markup=keyboards.kb_confirm(f"xray_go:{server_id}", f"srv:{server_id}", "✅ Всё равно обновить"),
        )
        return
    if data.startswith("xray_go:"):
        server_id = int(data.split(":", 1)[1])
        ok, msg = ctx.h1client.xray_update(server_id)
        ctx.notify_other_admins(chat_id, f"🧬 {chat_id} обновил ядро Xray на сервере #{server_id}: {msg}")
        tg.edit_message(chat_id, message_id, f"{'✅' if ok else '❌'} {msg}", reply_markup=keyboards.keyboard([keyboards.kb_back(f'srv:{server_id}')]))
        return

    # ── продление ──
    if data.startswith("renew_ask:"):
        server_id = data.split(":", 1)[1]
        tg.edit_message(
            chat_id, message_id,
            "💳 Продлить сервер на 30 дней? Спишутся реальные деньги с баланса аккаунта.",
            reply_markup=keyboards.kb_confirm(f"renew_go:{server_id}", f"srv:{server_id}"),
        )
        return
    if data.startswith("renew_go:"):
        server_id = int(data.split(":", 1)[1])
        result = ctx.h1client.renew(server_id)
        tg.edit_message(chat_id, message_id, f"✅ {result.get('message', 'Продлено')}. Баланс: {result.get('balance', '—')}", reply_markup=keyboards.keyboard([keyboards.kb_back(f'srv:{server_id}')]))
        return

    # ── CDN-гейтвей: проверка/применение ──
    if data.startswith("sync_check:"):
        server_id = int(data.split(":", 1)[1])
        binding = ctx.config.binding_for(server_id)
        changed, ok, msg = gateway_sync.check_rotation(binding, ctx.h1client, ctx.rw)
        text = msg if changed else "Домен гейтвея не менялся — Remnawave уже актуален."
        if changed:
            ctx.notify_admins(f"🌐 {text}")
        tg.edit_message(chat_id, message_id, f"{'✅' if (not changed or ok) else '⚠️'} {text}", reply_markup=keyboards.keyboard([keyboards.kb_back(f'srv:{server_id}')]))
        return

    if data.startswith("diag:"):
        server_id = int(data.split(":", 1)[1])
        binding = ctx.config.binding_for(server_id)
        backup_path = _regenerate_backup_path(server_id)
        saved = json.loads(backup_path.read_text(encoding="utf-8")) if backup_path.exists() else None
        text = gateway_sync.diagnostics(binding, ctx.h1client, ctx.rw, saved)
        tg.edit_message(chat_id, message_id, text, reply_markup=keyboards.keyboard([keyboards.kb_back(f'srv:{server_id}')]))
        return

    # ── REALITY: перевыпуск и применение (два раздельных подтверждаемых шага) ──
    if data.startswith("regen_ask:"):
        server_id = data.split(":", 1)[1]
        tg.edit_message(
            chat_id, message_id,
            "🔑 <b>Необратимо.</b> Перевыпуск REALITY-ключей на стороне h1cloud — старый ключ умирает "
            "СРАЗУ. Этот шаг только скачивает новый ключ и показывает fingerprint — сам он ничего "
            "не меняет в Remnawave, для этого отдельная кнопка «Применить».",
            reply_markup=keyboards.kb_confirm(f"regen_go:{server_id}", f"srv:{server_id}", "✅ Перевыпустить"),
        )
        return
    if data.startswith("regen_go:"):
        server_id = int(data.split(":", 1)[1])
        data_resp = ctx.h1client.config_regenerate(server_id)
        save_json_backup(_regenerate_backup_path(server_id), data_resp)
        fp = "?"
        for inbound in data_resp.get("profile", {}).get("inbounds", []):
            if inbound.get("tag") == "VLESS-REALITY":
                fp = gateway_sync.key_fingerprint(inbound.get("streamSettings", {}).get("realitySettings", {}).get("privateKey", ""))
        tg.edit_message(
            chat_id, message_id,
            f"✅ Новый ключ скачан и сохранён (fingerprint: {fp}). Он НЕ применён в Remnawave — нажми «Применить», когда будешь готов.",
            reply_markup=keyboards.keyboard([keyboards.kb_back(f'srv:{server_id}')]),
        )
        return

    if data.startswith("apply_ask:"):
        server_id = data.split(":", 1)[1]
        tg.edit_message(
            chat_id, message_id,
            "📥 Применить последний скачанный REALITY-ключ в Remnawave? REALITY/XHTTP/WS на этом "
            "сервере будут недоступны несколько минут во время рестарта ноды.",
            reply_markup=keyboards.kb_confirm(f"apply_go:{server_id}", f"srv:{server_id}", "✅ Применить"),
        )
        return
    if data.startswith("apply_go:"):
        server_id = int(data.split(":", 1)[1])
        binding = ctx.config.binding_for(server_id)
        backup_path = _regenerate_backup_path(server_id)
        if not backup_path.exists():
            tg.edit_message(chat_id, message_id, "❌ Нет скачанного ключа — сначала нажми «Перевыпустить REALITY-ключи».", reply_markup=keyboards.keyboard([keyboards.kb_back(f'srv:{server_id}')]))
            return
        saved = json.loads(backup_path.read_text(encoding="utf-8"))
        ok, msg = gateway_sync.apply_regenerated_reality(binding, saved, ctx.rw)
        ctx.notify_other_admins(chat_id, f"📥 {chat_id} применил REALITY-ключ на сервере #{server_id}: {msg}")
        tg.edit_message(chat_id, message_id, f"{'✅' if ok else '❌'} {msg}", reply_markup=keyboards.keyboard([keyboards.kb_back(f'srv:{server_id}')]))
        return

    # ── создание нового конфига в панели (браузер) ──
    if data.startswith("newcfg_ask:"):
        server_id = data.split(":", 1)[1]
        tg.edit_message(
            chat_id, message_id,
            "⚠️ <b>Необратимо.</b> Текущий whitelist/CDN-конфиг сервера умрёт СРАЗУ после нажатия. "
            "Используй только если провайдер объявил ротацию/восстановление гейтвея.",
            reply_markup=keyboards.kb_confirm(f"newcfg_go:{server_id}", f"srv:{server_id}", "✅ Всё равно создать"),
        )
        return
    if data.startswith("newcfg_go:"):
        server_id = int(data.split(":", 1)[1])
        tg.edit_message(chat_id, message_id, "⏳ Выполняю клик в панели...")
        ok, msg = click_new_config(ctx.config.h1cloud_panel_login, ctx.config.h1cloud_panel_password, server_id)
        tg.edit_message(chat_id, message_id, f"{'✅' if ok else '❌'} {msg}", reply_markup=keyboards.keyboard([keyboards.kb_back(f'srv:{server_id}')]))
        return

    if data.startswith("autoclick_toggle:"):
        server_id = int(data.split(":", 1)[1])
        channel_watch.autoclick_set(server_id, not channel_watch.autoclick_enabled(server_id))
        _show_server(ctx, chat_id, message_id, server_id)
        return

    # ── legacy Pelican API ──
    if data == "pelican_list":
        servers = ctx.pelican.list_servers()
        tg.edit_message(chat_id, message_id, "🗄 Серверы (Pelican, устаревший API):", reply_markup=keyboards.kb_pelican_list(servers))
        return
    if data.startswith("pelican_srv:"):
        identifier = data.split(":", 1)[1]
        resources = ctx.pelican.resources(identifier)
        text = f"Состояние: {resources.get('current_state', '—')}\nCPU: {resources.get('resources', {}).get('cpu_absolute', '—')}%"
        tg.edit_message(chat_id, message_id, text, reply_markup=keyboards.kb_pelican_detail(identifier))
        return
    if data.startswith("pelican_pwr:"):
        _, identifier, signal = data.split(":")
        ctx.pelican.power(identifier, signal)
        tg.edit_message(chat_id, message_id, f"✅ Сигнал {signal} отправлен.", reply_markup=keyboards.kb_pelican_detail(identifier))
        return

    tg.edit_message(chat_id, message_id, "Неизвестная команда.", reply_markup=keyboards.kb_main_menu(ctx.config))


def handle_message(ctx: Context, update: dict) -> None:
    msg = update["message"]
    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    text = msg.get("text", "")

    if not ctx.is_admin(user_id):
        ctx.tg.send_message(chat_id, "⛔ Доступ запрещён. Добавь свой Telegram id в ADMIN_IDS в .env.")
        return

    if text.startswith("/start") or text.startswith("/menu"):
        ctx.tg.send_message(chat_id, "🛸 H1-B0t-auto", reply_markup=keyboards.kb_main_menu(ctx.config))
