"""Точка входа бота: конфиг → Context → long-polling getUpdates + периодические
фоновые проверки в том же цикле (без отдельных потоков — интервалы измеряются
в минутах, обычной гранулярности long-polling с лихвой хватает)."""
import logging
import time

from . import channel_watch, gateway_sync
from .config import load_config
from .handlers import Context, handle_callback, handle_message

logger = logging.getLogger("h1bot.app")


def _run_gateway_checks(ctx: Context) -> None:
    for binding in ctx.config.gateway_bindings:
        try:
            changed, ok, msg = gateway_sync.check_rotation(binding, ctx.h1client, ctx.rw)
            if changed:
                ctx.notify_admins(f"🌐 {msg}")
        except Exception as e:
            logger.exception("gateway check failed for binding %s", binding.h1cloud_server_id)
            ctx.notify_admins(f"❌ Ошибка автопроверки CDN-домена для {binding.label or binding.h1cloud_server_id}: {e}")


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config = load_config()
    if not config.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN не задан в .env — заполни его и перезапусти.")
    if not config.admin_ids:
        logger.warning("ADMIN_IDS пуст в .env — бот будет отвечать «доступ запрещён» абсолютно всем.")

    ctx = Context.build(config)

    gateway_checks_enabled = bool(config.gateway_bindings) and config.h1cloud_client_enabled
    channel_monitoring_enabled = bool(config.gateway_bindings)
    if channel_monitoring_enabled:
        channel_watch.bootstrap()

    ctx.notify_admins("🚀 H1-B0t-auto запущен и готов к работе.")
    logger.info(
        "started: h1cloud_client=%s pelican=%s remnawave=%s browser=%s bindings=%d",
        config.h1cloud_client_enabled, config.h1cloud_pelican_enabled,
        config.remnawave_enabled, config.browser_automation_enabled, len(config.bindings),
    )

    offset = 0
    last_gateway_check = 0.0
    last_channel_check = 0.0

    while True:
        now = time.time()

        if gateway_checks_enabled and now - last_gateway_check >= config.gateway_check_interval:
            last_gateway_check = now
            _run_gateway_checks(ctx)

        if channel_monitoring_enabled and now - last_channel_check >= config.channel_check_interval:
            last_channel_check = now
            try:
                channel_watch.check(config, ctx.h1client, ctx.rw, ctx.notify_admins)
            except Exception:
                logger.exception("channel check failed")

        for update in ctx.tg.get_updates(offset=offset, timeout=25):
            offset = update["update_id"] + 1
            try:
                if "callback_query" in update:
                    handle_callback(ctx, update)
                elif "message" in update:
                    handle_message(ctx, update)
            except Exception:
                logger.exception("update handling failed: %s", update)
