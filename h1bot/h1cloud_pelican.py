"""H1cloud Pelican панель (panel.h1cloud.net/api/client/...) — старый API
прямого управления контейнером (форк Pterodactyl). В основном заменён Client
API v1 (h1cloud_client.py), но у части аккаунтов может не быть доступа к
новому API — держим как опциональный фолбэк, включается только если в .env
заполнены H1CLOUD_PELICAN_API_URL/H1CLOUD_PELICAN_API_TOKEN.
"""
import logging

from .http_utils import request_with_retry

logger = logging.getLogger("h1bot.h1cloud_pelican")


class H1CloudPelicanAPI:
    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_token}", "Accept": "application/json"}

    def list_servers(self) -> list:
        r = request_with_retry("GET", f"{self.base_url}/api/client", headers=self._headers(), timeout=15)
        r.raise_for_status()
        return [item["attributes"] for item in r.json().get("data", [])]

    def server(self, identifier: str) -> dict:
        r = request_with_retry("GET", f"{self.base_url}/api/client/servers/{identifier}", headers=self._headers(), timeout=15)
        r.raise_for_status()
        return r.json().get("attributes", {})

    def resources(self, identifier: str) -> dict:
        r = request_with_retry(
            "GET", f"{self.base_url}/api/client/servers/{identifier}/resources", headers=self._headers(), timeout=15
        )
        r.raise_for_status()
        return r.json().get("attributes", {})

    def power(self, identifier: str, signal: str) -> dict:
        """signal: start | stop | restart (kill намеренно не выведен в UI — слишком разрушительно)"""
        r = request_with_retry(
            "POST",
            f"{self.base_url}/api/client/servers/{identifier}/power",
            headers=self._headers(),
            json={"signal": signal},
            timeout=15,
        )
        r.raise_for_status()
        return {"ok": True}
