"""Синхронизация CDN-гейтвея h1cloud -> Remnawave, обобщённая на произвольный
список привязок (config.Binding) вместо одного захардкоженного сервера.

Крутится в цикле по всем bindings из bindings.json — для пользователей без
Remnawave или без привязок этот модуль просто не вызывается (см.
config.gateway_bindings).
"""
import logging

import requests

from .h1cloud_client import H1CloudClientAPI
from .remnawave_client import RemnawaveClient

logger = logging.getLogger("h1bot.gateway_sync")


def domain_tls_ok(domain: str) -> bool:
    try:
        requests.get(f"https://{domain}/", timeout=10)
        return True
    except requests.RequestException:
        return False


def check_rotation(binding, h1client: H1CloudClientAPI, rw: RemnawaveClient) -> tuple:
    """Возвращает (changed: bool, ok: bool, message: str).
    changed=False значит домен не менялся — ok/message в этом случае не важны."""
    new_domain = h1client.gateway_domain(binding.h1cloud_server_id)
    host = rw.get_host(binding.remnawave_host_uuid)
    old_domain = host.get("address")

    if new_domain == old_domain:
        return False, True, ""

    if not domain_tls_ok(new_domain):
        return True, False, f"Новый домен {new_domain} не прошёл TLS-проверку — НЕ применено, нужна ручная проверка"

    host["address"] = new_domain
    host["sni"] = new_domain
    host["host"] = new_domain
    ok, err = rw.update_host(host)
    if not ok:
        return True, False, f"Домен сменился на {new_domain}, но обновить Remnawave Host не удалось: {err}"

    return True, True, f"Домен гейтвея сменился {old_domain} → {new_domain}, применено в Remnawave"


def key_fingerprint(key: str) -> str:
    if not key or len(key) < 12:
        return key or "?"
    return f"{key[:6]}...{key[-6:]}"


def apply_regenerated_reality(binding, regenerate_data: dict, rw: RemnawaveClient) -> tuple:
    """Точечно вливает privateKey/shortIds из ответа h1cloud config/regenerate
    в конкретный REALITY-инбаунд (binding.reality_inbound_tag) внутри
    config-profile Remnawave. НИКОГДА не пушить ответ regenerate целиком —
    он содержит generic-теги провайдера, а не теги конкретной инсталляции."""
    if not binding.reality_apply_enabled:
        return False, "У этой привязки не заданы remnawave_profile_uuid/remnawave_node_uuid/reality_inbound_tag"

    reality_entry = None
    for inbound in regenerate_data.get("profile", {}).get("inbounds", []):
        if inbound.get("tag") == "VLESS-REALITY":
            reality_entry = inbound
            break
    if reality_entry is None:
        return False, "В ответе h1cloud config/regenerate не найден инбаунд VLESS-REALITY"

    reality_settings = reality_entry.get("streamSettings", {}).get("realitySettings", {})
    private_key = reality_settings.get("privateKey")
    short_ids = reality_settings.get("shortIds")
    if not private_key:
        return False, "В ответе h1cloud нет privateKey для REALITY"

    profile = rw.get_config_profile(binding.remnawave_profile_uuid)
    target_inbound = None
    for inbound in profile.get("config", {}).get("inbounds", []):
        if inbound.get("tag") == binding.reality_inbound_tag:
            target_inbound = inbound
            break
    if target_inbound is None:
        return False, f"В Remnawave config-profile не найден инбаунд с тегом {binding.reality_inbound_tag}"

    target_inbound.setdefault("streamSettings", {}).setdefault("realitySettings", {})["privateKey"] = private_key
    if short_ids is not None:
        target_inbound["streamSettings"]["realitySettings"]["shortIds"] = short_ids

    ok, err = rw.patch_config_profile(profile)
    if not ok:
        return False, f"Не удалось применить новый ключ в Remnawave: {err}"

    ok, err = rw.restart_node(binding.remnawave_node_uuid)
    if not ok:
        return False, f"Ключ применён, но рестарт ноды не удался: {err}"

    return True, f"Новый REALITY-ключ применён и нода перезапущена (fingerprint: {key_fingerprint(private_key)})"


def diagnostics(binding, h1client: H1CloudClientAPI, rw: RemnawaveClient, saved_regenerate: dict = None) -> str:
    """Короткий отчёт по одной привязке: по строке ✅/⚠️/❌ на каждую проверку,
    без разворачивания в глубокую диагностику при сбое — только сигнал что
    именно упало."""
    lines = [f"🩺 Диагностика: {binding.label or binding.h1cloud_server_id}"]

    try:
        stats = h1client.server_stats(binding.h1cloud_server_id)
        lines.append(f"✅ Сервер: {stats.get('state', '?')}, аптайм {stats.get('uptime', '?')}")
    except Exception as e:
        lines.append(f"❌ Сервер: не удалось получить статус ({e})")

    if binding.gateway_sync_enabled:
        try:
            current_domain = h1client.gateway_domain(binding.h1cloud_server_id)
            host = rw.get_host(binding.remnawave_host_uuid)
            host_domain = host.get("address")
            if current_domain == host_domain:
                tls_ok = domain_tls_ok(current_domain)
                lines.append(f"{'✅' if tls_ok else '⚠️'} CDN-домен совпадает с Remnawave ({current_domain}), TLS: {'ok' if tls_ok else 'не отвечает'}")
            else:
                lines.append(f"⚠️ CDN-домен разошёлся: h1cloud={current_domain}, Remnawave={host_domain} — нужна ручная/автопроверка")
        except Exception as e:
            lines.append(f"❌ CDN-домен: ошибка проверки ({e})")

    if binding.reality_apply_enabled:
        try:
            profile = rw.get_config_profile(binding.remnawave_profile_uuid)
            live_key = None
            for inbound in profile.get("config", {}).get("inbounds", []):
                if inbound.get("tag") == binding.reality_inbound_tag:
                    live_key = inbound.get("streamSettings", {}).get("realitySettings", {}).get("privateKey")
                    break
            live_fp = key_fingerprint(live_key) if live_key else "?"
            if saved_regenerate:
                saved_key = None
                for inbound in saved_regenerate.get("profile", {}).get("inbounds", []):
                    if inbound.get("tag") == "VLESS-REALITY":
                        saved_key = inbound.get("streamSettings", {}).get("realitySettings", {}).get("privateKey")
                        break
                saved_fp = key_fingerprint(saved_key) if saved_key else "?"
                match = live_key == saved_key
                lines.append(f"{'✅' if match else '⚠️'} REALITY-ключ: живой {live_fp}, последний скачанный {saved_fp}{' (совпадают)' if match else ' (есть невнесённые изменения)'}")
            else:
                lines.append(f"✅ REALITY-ключ (живой, fingerprint {live_fp})")
        except Exception as e:
            lines.append(f"❌ REALITY-ключ: ошибка проверки ({e})")

        try:
            node = rw.get_node(binding.remnawave_node_uuid)
            connected = node.get("isConnected")
            xray_uptime = node.get("xrayUptime")
            lines.append(f"{'✅' if connected else '❌'} Нода: {'подключена' if connected else 'НЕ подключена'}, xrayUptime: {xray_uptime}")
        except Exception as e:
            lines.append(f"❌ Нода: ошибка проверки ({e})")

    return "\n".join(lines)
