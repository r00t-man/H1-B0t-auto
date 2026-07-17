"""Тонкая обёртка над Telegram Bot API — сырые HTTP-запросы через requests,
без python-telegram-bot/aiogram — меньше зависимостей, весь протокол виден
напрямую в коде.
"""
import logging

import requests

logger = logging.getLogger("h1bot.telegram")

API_BASE = "https://api.telegram.org/bot{token}"


class TelegramClient:
    def __init__(self, token: str):
        self.token = token
        self.base = API_BASE.format(token=token)

    def _call(self, method: str, **params) -> dict:
        try:
            r = requests.post(f"{self.base}/{method}", json=params, timeout=35)
            data = r.json()
            if not data.get("ok"):
                logger.warning("Telegram API %s failed: %s", method, data)
            return data
        except requests.RequestException as e:
            logger.warning("Telegram API %s error: %s", method, e)
            return {"ok": False, "error": str(e)}

    def get_updates(self, offset: int = 0, timeout: int = 30) -> list:
        data = self._call(
            "getUpdates",
            offset=offset,
            timeout=timeout,
            allowed_updates=["message", "callback_query"],
        )
        return data.get("result", []) if data.get("ok") else []

    def send_message(self, chat_id, text: str, reply_markup: dict = None, parse_mode: str = "HTML") -> dict:
        params = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            params["reply_markup"] = reply_markup
        return self._call("sendMessage", **params)

    def edit_message(self, chat_id, message_id, text: str, reply_markup: dict = None, parse_mode: str = "HTML") -> dict:
        params = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            params["reply_markup"] = reply_markup
        return self._call("editMessageText", **params)

    def answer_callback_query(self, callback_query_id: str, text: str = None, show_alert: bool = False) -> dict:
        params = {"callback_query_id": callback_query_id}
        if text:
            params["text"] = text
            params["show_alert"] = show_alert
        return self._call("answerCallbackQuery", **params)


def button(text: str, callback_data: str) -> dict:
    return {"text": text, "callback_data": callback_data}


def keyboard(rows: list) -> dict:
    """rows: list[list[button(...)]] -> инлайн-клавиатура Telegram."""
    return {"inline_keyboard": rows}
