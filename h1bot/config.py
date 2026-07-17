"""Загрузка конфигурации: .env (простой KEY=VALUE парсер, без python-dotenv)
+ bindings.json (список привязок h1cloud-сервер -> Remnawave-хост).

Ничего не обязано быть заполнено, кроме токена бота и ADMIN_IDS — остальные
поля включают/выключают целые куски функционала бота через property-флаги
ниже, вместо падения с исключением при отсутствии кредов.
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
BINDINGS_FILE = BASE_DIR / "bindings.json"


def parse_env_file(path: Path) -> dict:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


@dataclass
class Binding:
    h1cloud_server_id: int
    label: str = ""
    remnawave_host_uuid: str = ""
    remnawave_profile_uuid: str = ""
    remnawave_node_uuid: str = ""
    reality_inbound_tag: str = ""

    @property
    def gateway_sync_enabled(self) -> bool:
        return bool(self.remnawave_host_uuid)

    @property
    def reality_apply_enabled(self) -> bool:
        return bool(self.remnawave_profile_uuid and self.remnawave_node_uuid and self.reality_inbound_tag)


@dataclass
class Config:
    telegram_bot_token: str = ""
    admin_ids: list = field(default_factory=list)

    h1cloud_client_api_url: str = "https://my.h1cloud.net"
    h1cloud_client_api_key: str = ""

    h1cloud_panel_login: str = ""
    h1cloud_panel_password: str = ""

    h1cloud_pelican_api_url: str = "https://panel.h1cloud.net"
    h1cloud_pelican_api_token: str = ""

    remnawave_api_url: str = ""
    remnawave_api_token: str = ""

    gateway_check_interval: int = 900
    channel_check_interval: int = 300

    bindings: list = field(default_factory=list)

    # ── feature-флаги: что реально доступно при текущем наборе кредов ──
    @property
    def h1cloud_client_enabled(self) -> bool:
        return bool(self.h1cloud_client_api_key)

    @property
    def h1cloud_pelican_enabled(self) -> bool:
        return bool(self.h1cloud_pelican_api_token)

    @property
    def browser_automation_enabled(self) -> bool:
        return bool(self.h1cloud_panel_login and self.h1cloud_panel_password)

    @property
    def remnawave_enabled(self) -> bool:
        return bool(self.remnawave_api_url and self.remnawave_api_token)

    @property
    def gateway_bindings(self) -> list:
        """Привязки, для которых реально можно синхронизировать CDN-домен — только если
        и Remnawave настроен, и у самой привязки указан remnawave_host_uuid."""
        if not self.remnawave_enabled:
            return []
        return [b for b in self.bindings if b.gateway_sync_enabled]

    def binding_for(self, h1cloud_server_id: int):
        for b in self.bindings:
            if b.h1cloud_server_id == h1cloud_server_id:
                return b
        return None


def _split_ids(raw: str) -> list:
    result = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if chunk.isdigit():
            result.append(int(chunk))
    return result


def load_bindings(path: Path = BINDINGS_FILE) -> list:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    bindings = []
    for item in data:
        if not isinstance(item, dict) or "h1cloud_server_id" not in item:
            continue
        bindings.append(Binding(
            h1cloud_server_id=int(item["h1cloud_server_id"]),
            label=item.get("label", ""),
            remnawave_host_uuid=item.get("remnawave_host_uuid", ""),
            remnawave_profile_uuid=item.get("remnawave_profile_uuid", ""),
            remnawave_node_uuid=item.get("remnawave_node_uuid", ""),
            reality_inbound_tag=item.get("reality_inbound_tag", ""),
        ))
    return bindings


def load_config(env_path: Path = ENV_FILE, bindings_path: Path = BINDINGS_FILE) -> Config:
    env = parse_env_file(env_path)

    def get(key: str, default: str = "") -> str:
        # окружение процесса (напр. systemd Environment=) перекрывает .env
        return os.environ.get(key, env.get(key, default))

    return Config(
        telegram_bot_token=get("TELEGRAM_BOT_TOKEN"),
        admin_ids=_split_ids(get("ADMIN_IDS")),
        h1cloud_client_api_url=get("H1CLOUD_CLIENT_API_URL", "https://my.h1cloud.net").rstrip("/"),
        h1cloud_client_api_key=get("H1CLOUD_CLIENT_API_KEY"),
        h1cloud_panel_login=get("H1CLOUD_PANEL_LOGIN"),
        h1cloud_panel_password=get("H1CLOUD_PANEL_PASSWORD"),
        h1cloud_pelican_api_url=get("H1CLOUD_PELICAN_API_URL", "https://panel.h1cloud.net").rstrip("/"),
        h1cloud_pelican_api_token=get("H1CLOUD_PELICAN_API_TOKEN"),
        remnawave_api_url=get("REMNAWAVE_API_URL").rstrip("/"),
        remnawave_api_token=get("REMNAWAVE_API_TOKEN"),
        gateway_check_interval=int(get("GATEWAY_CHECK_INTERVAL", "900") or 900),
        channel_check_interval=int(get("CHANNEL_CHECK_INTERVAL", "300") or 300),
        bindings=load_bindings(bindings_path),
    )
