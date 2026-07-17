"""Общий HTTP-хелпер с ретраями — используется всеми клиентами API (h1cloud,
Remnawave). h1cloud временами отдаёт 403 от WAF на абсолютно легитимные
запросы (наблюдалось на живой инсталляции) — retry на 403 решает это без
необходимости разбираться в конкретной причине блокировки.
"""
import logging
import time

import requests

logger = logging.getLogger("h1bot.http")


def request_with_retry(method: str, url: str, retries: int = 3, retry_delay: float = 3.0, **kwargs) -> requests.Response:
    last_resp = None
    for attempt in range(retries + 1):
        resp = requests.request(method, url, **kwargs)
        last_resp = resp
        if resp.status_code != 403:
            return resp
        if attempt < retries:
            logger.info("HTTP 403 on %s %s, retry %d/%d", method, url, attempt + 1, retries)
            time.sleep(retry_delay)
    return last_resp
