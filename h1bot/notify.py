"""Уведомления админам — обычная рассылка и cross-notify (чтобы второй админ
узнал, что первый уже нажал опасную кнопку, и не продублировал действие
вслепую при одновременном онлайне)."""
from .telegram import TelegramClient


def notify_admins(tg: TelegramClient, admin_ids: list, text: str) -> None:
    for admin_id in admin_ids:
        tg.send_message(admin_id, text)


def notify_other_admins(tg: TelegramClient, admin_ids: list, triggering_chat_id, text: str) -> None:
    for admin_id in admin_ids:
        if str(admin_id) != str(triggering_chat_id):
            tg.send_message(admin_id, text)
