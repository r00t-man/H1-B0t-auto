"""Минимальный клиент Remnawave API — только то, что нужно для синхронизации
CDN-гейтвея h1cloud с Remnawave: чтение/обновление Host-записи, чтение/патч
config-profile (для REALITY-ключей), рестарт ноды. НЕ полноценный SDK —
осознанно маленький, под конкретную задачу этого бота.
"""
import logging

from .http_utils import request_with_retry

logger = logging.getLogger("h1bot.remnawave_client")


class RemnawaveClient:
    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def get_host(self, host_uuid: str) -> dict:
        r = request_with_retry("GET", f"{self.base_url}/hosts/{host_uuid}", headers=self._headers(), timeout=15)
        r.raise_for_status()
        return r.json().get("response", r.json())

    def update_host(self, host: dict) -> tuple:
        """PATCH /hosts принимает ВЕСЬ объект хоста в теле (uuid внутри host) —
        отдельного /hosts/{uuid} эндпоинта для записи в этом API нет."""
        r = request_with_retry("PATCH", f"{self.base_url}/hosts", headers=self._headers(), json=host, timeout=15)
        if r.status_code >= 400:
            return False, f"HTTP {r.status_code}: {r.text[:300]}"
        return True, ""

    def get_config_profile(self, profile_uuid: str) -> dict:
        r = request_with_retry("GET", f"{self.base_url}/config-profiles/{profile_uuid}", headers=self._headers(), timeout=15)
        r.raise_for_status()
        return r.json().get("response", r.json())

    def patch_config_profile(self, profile: dict) -> tuple:
        """PATCH /config-profiles — БЕЗ uuid в пути (тот отдаёт 404 на PATCH),
        uuid передаётся в теле вместе с полным config."""
        body = {"uuid": profile["uuid"], "name": profile.get("name"), "config": profile["config"]}
        r = request_with_retry("PATCH", f"{self.base_url}/config-profiles", headers=self._headers(), json=body, timeout=15)
        if r.status_code >= 400:
            return False, f"HTTP {r.status_code}: {r.text[:300]}"
        return True, ""

    def get_node(self, node_uuid: str) -> dict:
        r = request_with_retry("GET", f"{self.base_url}/nodes/{node_uuid}", headers=self._headers(), timeout=15)
        r.raise_for_status()
        return r.json().get("response", r.json())

    def restart_node(self, node_uuid: str) -> tuple:
        r = request_with_retry(
            "POST",
            f"{self.base_url}/nodes/{node_uuid}/actions/restart",
            headers=self._headers(),
            json={"forceRestart": True},
            timeout=15,
        )
        if r.status_code >= 400:
            return False, f"HTTP {r.status_code}: {r.text[:300]}"
        return True, ""
