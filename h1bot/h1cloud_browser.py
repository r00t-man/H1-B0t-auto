"""Headless-браузерный клик кнопки «Создать новый конфиг» на my.h1cloud.net.

h1cloud НЕ даёт API-эндпоинт для этого конкретного действия на
Remnawave/CDN-серверах (POST /config/regenerate поддержан только для
3x-ui-серверов) — единственный способ выполнить его программно — залогиниться
как обычный пользователь через веб-форму и нажать кнопку так, как это делает
живой человек. Playwright импортируется лениво: если браузерная автоматизация
не настроена (нет логина/пароля панели), модуль вообще не требует playwright
как реальную зависимость в рантайме.
"""
import logging

logger = logging.getLogger("h1bot.h1cloud_browser")


def click_new_config(login: str, password: str, server_id: int, base_url: str = "https://my.h1cloud.net") -> tuple:
    """Возвращает (ok: bool, message: str). Не бросает исключения наружу —
    любая ошибка автоматизации (интерфейс сайта изменился, таймаут и т.п.)
    возвращается как обычный неуспех, чтобы вызывающий код мог показать
    пользователю понятное сообщение вместо трейсбека."""
    if not login or not password:
        return False, "Логин/пароль панели my.h1cloud.net не настроены (H1CLOUD_PANEL_LOGIN/PASSWORD)"

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, "Playwright не установлен — выполни: pip install playwright && playwright install --with-deps chromium"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(f"{base_url}/", timeout=20000)

                page.fill('input[placeholder*="domain.ru"]', login)
                page.fill('input[placeholder="Введите пароль"]', password)
                page.click('button:has-text("Войти")')
                page.wait_for_timeout(3000)

                if page.get_by_text("Мои серверы").count() == 0:
                    return False, "Не удалось залогиниться — проверь H1CLOUD_PANEL_LOGIN/PASSWORD"

                page.goto(f"{base_url}/servers", timeout=20000)
                page.wait_for_timeout(2000)

                server_marker = page.get_by_text(f"#{server_id}", exact=False)
                if server_marker.count() == 0:
                    return False, f"Сервер #{server_id} не найден в списке на странице /servers"
                server_marker.first.click()
                page.wait_for_timeout(1500)

                new_config_btn = page.get_by_role("button", name="Создать новый конфиг", exact=True)
                if new_config_btn.count() == 0:
                    return False, "Кнопка «Создать новый конфиг» не найдена — интерфейс сайта мог измениться"
                new_config_btn.click()

                confirm_btn = page.get_by_role("button", name="Создать новый", exact=True)
                if confirm_btn.count() == 0:
                    return False, "Кнопка подтверждения в модальном окне не найдена — интерфейс сайта мог измениться"
                confirm_btn.click()

                page.wait_for_timeout(5000)
                body_text = page.inner_text("body")
                if "Обновлено:" in body_text:
                    return True, "Новый конфиг создан и подтверждён панелью (найдена метка «Обновлено:»)"
                return False, "Клик выполнен, но подтверждение «Обновлено:» на странице не найдено"
            finally:
                browser.close()
    except Exception as e:  # автоматизация браузера — широкий диапазон возможных сбоев сайта/сети
        logger.warning("Browser automation failed: %s", e)
        return False, f"Ошибка браузерной автоматизации: {e}"
