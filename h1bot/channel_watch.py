"""Мониторинг ПУБЛИЧНОГО Telegram-канала провайдера — t.me/h1cloud_status,
через t.me/s/<channel> HTML-превью (без бота/юзербота/токена). Единственный
адрес, зашитый напрямую в код (по явному согласию пользователя при проектировании
этого бота) — это открытый канал самого h1cloud с объявлениями о
технических работах/восстановлении LTE-гейтвея, не секрет и ни к чьей
инфраструктуре не привязан.
"""
import html
import logging
import re

import requests

from . import state
from .gateway_sync import check_rotation
from .h1cloud_browser import click_new_config

logger = logging.getLogger("h1bot.channel_watch")

MONITORED_CHANNEL = "h1cloud_status"
STATE_KEY_LAST_POST = "h1cloud_status_last_post"

# Пост о ВОССТАНОВЛЕНИИ доступа — только на такие посты имеет смысл автоклик.
RECOVERY_RE = re.compile(r"восстановлен|исправил", re.IGNORECASE)
# Более широкий матч на канальном уровне — ловит и начало проблемы (нужно
# просто уведомить админов), и восстановление (для него ещё отдельно
# проверяем RECOVERY_RE, чтобы не кликнуть на посте о НАЧАЛЕ аварии).
ANY_MATCH_RE = re.compile(r"восстановлен|технические работы|недоступ|исправил", re.IGNORECASE)

_MESSAGE_RE = re.compile(
    r'<div class="tgme_widget_message_wrap.*?data-post="[^/"]+/(\d+)".*?'
    r'tgme_widget_message_text[^>]*>(.*?)</div>',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _fetch_posts(channel: str = MONITORED_CHANNEL) -> list:
    r = requests.get(f"https://t.me/s/{channel}", headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    r.raise_for_status()
    posts = []
    for match in _MESSAGE_RE.finditer(r.text):
        post_id = int(match.group(1))
        text = html.unescape(_TAG_RE.sub("", match.group(2)))
        text = re.sub(r"\s+", " ", text).strip()
        posts.append((post_id, text))
    return posts


def bootstrap() -> None:
    """На первом запуске только запоминает последний пост, без алертов —
    иначе бот наспамит алертами по всей истории канала при первом старте."""
    if state.get_state(STATE_KEY_LAST_POST):
        return
    try:
        posts = _fetch_posts()
    except requests.RequestException as e:
        logger.warning("channel bootstrap failed: %s", e)
        return
    if posts:
        state.set_state(STATE_KEY_LAST_POST, str(max(pid for pid, _ in posts)))


def autoclick_enabled(server_id: int) -> bool:
    return state.get_state(f"autoclick_{server_id}") == "1"


def autoclick_set(server_id: int, enabled: bool) -> None:
    state.set_state(f"autoclick_{server_id}", "1" if enabled else "0")


def check(config, h1client, rw, notify_fn) -> None:
    last_seen = int(state.get_state(STATE_KEY_LAST_POST, "0") or 0)
    try:
        posts = _fetch_posts()
    except requests.RequestException as e:
        logger.warning("channel check failed: %s", e)
        return

    new_posts = [(pid, text) for pid, text in posts if pid > last_seen]
    if not new_posts:
        return

    for post_id, text in new_posts:
        if ANY_MATCH_RE.search(text):
            _handle_post(config, h1client, rw, notify_fn, post_id, text)

    state.set_state(STATE_KEY_LAST_POST, str(max(pid for pid, _ in new_posts)))


def _handle_post(config, h1client, rw, notify_fn, post_id: int, text: str) -> None:
    link = f"https://t.me/{MONITORED_CHANNEL}/{post_id}"
    base_text = f"📡 Новый пост в канале провайдера {MONITORED_CHANNEL}:\n\n{text}\n\n{link}"

    if not RECOVERY_RE.search(text):
        notify_fn(base_text)
        return

    autoclick_bindings = [b for b in config.gateway_bindings if autoclick_enabled(b.h1cloud_server_id)]
    if not autoclick_bindings:
        notify_fn(base_text + "\n\nАвтоклик выключен для всех привязок — при необходимости нажми «Создать новый конфиг» вручную в меню сервера.")
        return

    results = []
    for binding in autoclick_bindings:
        ok, msg = click_new_config(config.h1cloud_panel_login, config.h1cloud_panel_password, binding.h1cloud_server_id)
        results.append(f"{'✅' if ok else '❌'} {binding.label or binding.h1cloud_server_id}: {msg}")
        if ok:
            try:
                changed, sync_ok, sync_msg = check_rotation(binding, h1client, rw)
                if changed:
                    results.append(f"  ↳ {sync_msg}")
            except Exception as e:
                results.append(f"  ↳ Ошибка проверки CDN-домена после клика: {e}")

    notify_fn(base_text + "\n\n🤖 Автоклик «Создать новый конфиг»:\n" + "\n".join(results))
