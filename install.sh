#!/usr/bin/env bash
# H1-B0t-auto — установщик.
#
# Что делает: ставит системные пакеты (python3/venv/pip), создаёт venv,
# ставит зависимости из requirements.txt, запускает интерактивный мастер
# настройки (h1bot/setup_wizard.py — сам спрашивает токены/ключи и объясняет
# зачем каждый нужен), при необходимости ставит Chromium для Playwright,
# генерирует и включает systemd-сервис.
#
# Безопасно перезапускать повторно — venv/зависимости/systemd-юнит просто
# переустановятся, .env/bindings.json НЕ перезаписываются молча (мастер сам
# спросит про существующие значения).
set -e

BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="h1-b0t-auto"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[*]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
fail()  { echo -e "${RED}[x]${NC} $1"; exit 1; }

if [ "$EUID" -ne 0 ]; then
  fail "Запусти установщик от root (sudo bash install.sh)."
fi

info "Каталог бота: $BOT_DIR"

# ── 1. Системные пакеты ─────────────────────────────────────────────────
info "Устанавливаю python3/venv/pip..."
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq python3 python3-venv python3-pip >/dev/null
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y -q python3 python3-pip python3-virtualenv
elif command -v yum >/dev/null 2>&1; then
  yum install -y -q python3 python3-pip python3-virtualenv
else
  fail "Не нашёл apt-get/dnf/yum — установи python3, python3-venv, python3-pip вручную и перезапусти скрипт."
fi

# ── 2. venv + зависимости ───────────────────────────────────────────────
if [ ! -d "$BOT_DIR/venv" ]; then
  info "Создаю venv..."
  python3 -m venv "$BOT_DIR/venv"
fi

info "Ставлю зависимости (requests, playwright)..."
"$BOT_DIR/venv/bin/pip" install -q --upgrade pip
"$BOT_DIR/venv/bin/pip" install -q -r "$BOT_DIR/requirements.txt"

# ── 3. Интерактивный мастер настройки ───────────────────────────────────
if [ ! -f "$BOT_DIR/.env.example" ]; then
  fail ".env.example не найден рядом со скриптом — что-то не так с репозиторием."
fi

info "Запускаю мастер настройки..."
"$BOT_DIR/venv/bin/python3" "$BOT_DIR/h1bot/setup_wizard.py"

# ── 4. Playwright/Chromium — только если настроена браузерная автоматизация ──
if grep -q "^H1CLOUD_PANEL_LOGIN=.\+" "$BOT_DIR/.env" 2>/dev/null; then
  info "Настроен логин панели — ставлю Chromium для Playwright (~300 МБ, один раз)..."
  "$BOT_DIR/venv/bin/playwright" install --with-deps chromium || \
    warn "Не удалось поставить Chromium автоматически — кнопка «Создать новый конфиг» не будет работать, пока не выполнишь: $BOT_DIR/venv/bin/playwright install --with-deps chromium"
else
  info "Логин панели не задан — пропускаю установку Chromium (кнопка «Создать новый конфиг» будет скрыта)."
fi

# ── 5. systemd ───────────────────────────────────────────────────────────
info "Настраиваю systemd-сервис ${SERVICE_NAME}..."
sed "s#{{BOT_DIR}}#${BOT_DIR}#g" "$BOT_DIR/systemd/h1-b0t-auto.service.template" > "/etc/systemd/system/${SERVICE_NAME}.service"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null
systemctl restart "$SERVICE_NAME"

sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
  info "Сервис запущен."
else
  warn "Сервис не запустился — смотри: journalctl -u $SERVICE_NAME -n 50"
fi

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo " Готово."
echo ""
echo " Логи:               journalctl -u $SERVICE_NAME -f"
echo " Статус:              systemctl status $SERVICE_NAME"
echo " Перезапуск:          systemctl restart $SERVICE_NAME"
echo " Ручная донастройка:  $BOT_DIR/.env  и  $BOT_DIR/bindings.json"
echo "                       (после правки — systemctl restart $SERVICE_NAME)"
echo "════════════════════════════════════════════════════════════════════"
