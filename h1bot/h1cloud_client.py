"""H1cloud Client API v1 (my.h1cloud.net/api/v1/...) — основной API: список
серверов, живые метрики, питание, баланс, продление, обновление ядра Xray,
перевыпуск REALITY-ключей. Bearer-ключ создаётся вручную из браузерной сессии
на my.h1cloud.net/api-docs — у h1cloud нет способа выдать его программно.
"""
import logging
import re
from pathlib import Path

from .http_utils import request_with_retry

logger = logging.getLogger("h1bot.h1cloud_client")

XRAY_UPDATE_ERROR_HINTS = {
    503: "сервер сейчас не запущен, подожди ~30 секунд и попробуй снова",
    409: "нет блока пина ядра — нужна помощь поддержки h1cloud",
    502: "не удалось прочитать/записать файлы сервера",
}


class H1CloudClientAPI:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}

    def _get(self, path: str, timeout: int = 15):
        return request_with_retry("GET", f"{self.base_url}{path}", headers=self._headers(), timeout=timeout)

    def _post(self, path: str, json_body: dict = None, timeout: int = 15):
        return request_with_retry("POST", f"{self.base_url}{path}", headers=self._headers(), json=json_body, timeout=timeout)

    def account(self) -> dict:
        r = self._get("/api/v1/me")
        r.raise_for_status()
        return r.json().get("account", {})

    def list_servers(self) -> list:
        r = self._get("/api/v1/servers")
        r.raise_for_status()
        return r.json().get("servers", [])

    def server_stats(self, server_id: int) -> dict:
        r = self._get(f"/api/v1/servers/{server_id}/stats")
        r.raise_for_status()
        return r.json().get("stats", {})

    def power(self, server_id: int, action: str) -> dict:
        """action: start | stop | restart"""
        r = self._post(f"/api/v1/servers/{server_id}/power", {"action": action})
        r.raise_for_status()
        return r.json()

    def renew(self, server_id: int) -> dict:
        r = self._post(f"/api/v1/servers/{server_id}/renew")
        r.raise_for_status()
        return r.json()

    def xray_update(self, server_id: int) -> tuple:
        """Программный эквивалент кнопки «Обновить ядро (обход)» — жёсткий
        рестарт xray-процесса, 2-3 минуты даунтайма. Возвращает (ok, message)."""
        r = self._post(f"/api/v1/servers/{server_id}/xray-update", timeout=30)
        if r.status_code == 200:
            return True, "Ядро Xray обновлено"
        hint = XRAY_UPDATE_ERROR_HINTS.get(r.status_code)
        if hint:
            return False, f"HTTP {r.status_code}: {hint}"
        return False, f"HTTP {r.status_code}: {r.text[:300]}"

    def config_regenerate(self, server_id: int) -> dict:
        """Перевыпускает REALITY private key + shortId на стороне h1cloud —
        НЕОБРАТИМО и мгновенно. Не применяет ничего в Remnawave сама по себе,
        только возвращает новые значения — применение см. gateway_sync.py."""
        r = self._post(f"/api/v1/servers/{server_id}/config/regenerate", timeout=30)
        r.raise_for_status()
        return r.json()

    def gateway_domain(self, server_id: int) -> str:
        """GET /config отдаёт ПРОСТОЙ ТЕКСТ (не JSON) с параметрами клиентского
        конфига — домен гейтвея вытаскивается регуляркой по полю Address."""
        r = self._get(f"/api/v1/servers/{server_id}/config", timeout=15)
        r.raise_for_status()
        match = re.search(r"Address\s*:\s*(\S+)", r.text)
        if not match:
            raise ValueError("В ответе /config не найдено поле Address — формат мог измениться")
        return match.group(1)


def save_json_backup(path: Path, data) -> None:
    import json
    from datetime import datetime, timezone

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"_saved_by_bot_at": datetime.now(timezone.utc).isoformat(), **data} if isinstance(data, dict) else data
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
