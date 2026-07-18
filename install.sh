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

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; MAGENTA='\033[0;35m'; BOLD='\033[1m'; NC='\033[0m'
info()  { echo -e "${GREEN}[*]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
fail()  { echo -e "${RED}[x]${NC} $1"; exit 1; }

spin() {
  # spin "надпись" -- крутит спиннер, пока фоновый процесс с этим PID жив
  local pid=$1 label=$2 frames='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏' i=0
  while kill -0 "$pid" 2>/dev/null; do
    i=$(((i + 1) % ${#frames}))
    printf "\r${CYAN}%s${NC} %s" "${frames:$i:1}" "$label"
    sleep 0.1
  done
  printf "\r%*s\r" "$((${#label} + 4))" ""
}

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
  "$BOT_DIR/venv/bin/playwright" install --with-deps chromium >/tmp/h1bot-playwright.log 2>&1 &
  spin $! "Chromium для Playwright..."
  wait $! || warn "Не удалось поставить Chromium автоматически (лог: /tmp/h1bot-playwright.log) — кнопка «Создать новый конфиг» не будет работать, пока не выполнишь: $BOT_DIR/venv/bin/playwright install --with-deps chromium"
else
  info "Логин панели (H1CLOUD_PANEL_LOGIN/PASSWORD) не задан — пропускаю установку Chromium. Кнопка «Создать новый конфиг» в боте всё равно будет видна, но при нажатии подскажет, что дозаполнить."
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


# ── 6. Итоговый чек-лист: что настроено для полного функционала ─────────
ENV_FILE="$BOT_DIR/.env"
BINDINGS_FILE="$BOT_DIR/bindings.json"

has_env() { grep -qE "^$1=.+" "$ENV_FILE" 2>/dev/null; }

client_ok=0; pelican_ok=0; panel_ok=0; rw_ok=0; bind_host=0; bind_reality=0
has_env H1CLOUD_CLIENT_API_KEY && client_ok=1
has_env H1CLOUD_PELICAN_API_TOKEN && pelican_ok=1
has_env H1CLOUD_PANEL_LOGIN && has_env H1CLOUD_PANEL_PASSWORD && panel_ok=1
has_env REMNAWAVE_API_URL && has_env REMNAWAVE_API_TOKEN && rw_ok=1
if [ -f "$BINDINGS_FILE" ]; then
  bind_host=$("$BOT_DIR/venv/bin/python3" -c "
import json
d = json.load(open('$BINDINGS_FILE'))
print(1 if any(b.get('remnawave_host_uuid') for b in d) else 0)
" 2>/dev/null || echo 0)
  bind_reality=$("$BOT_DIR/venv/bin/python3" -c "
import json
d = json.load(open('$BINDINGS_FILE'))
print(1 if any(b.get('remnawave_profile_uuid') and b.get('remnawave_node_uuid') and b.get('reality_inbound_tag') for b in d) else 0)
" 2>/dev/null || echo 0)
fi

mark() { [ "$1" = "1" ] && echo -e "${GREEN}✅${NC}" || echo -e "${RED}❌${NC}"; }
typeline() { echo -e "$1"; sleep 0.12; }

echo ""
echo -e "${MAGENTA}   .  *  .   ✦    .        .   *  .${NC}"
echo -e "${CYAN}         ___${MAGENTA}       *${NC}     ${CYAN}.${NC}"
echo -e "${CYAN}    ____/${BOLD}🛸${NC}${CYAN}\\____${NC}   ${MAGENTA}.${NC}    ${CYAN}*${NC}"
echo -e "${CYAN}   |  H1-B0t-auto  |${NC}       ${MAGENTA}.${NC}"
echo -e "${CYAN}    \\_____________/${NC}   ${MAGENTA}*${NC}    ${CYAN}.${NC}"
echo -e "${MAGENTA}   .    *   .  ✦  .    *    .${NC}"
echo ""
typeline "${BOLD}Готово.${NC} Проверяю, что настроено для ${BOLD}полного функционала${NC}..."
echo ""
typeline "  $(mark $client_ok) H1cloud Client API  ${YELLOW}→${NC} .env: H1CLOUD_CLIENT_API_KEY  ${YELLOW}(my.h1cloud.net/api-docs)${NC}"
typeline "  $(mark $pelican_ok) H1cloud Pelican API ${YELLOW}→${NC} .env: H1CLOUD_PELICAN_API_TOKEN ${YELLOW}(устаревший, опционально)${NC}"
typeline "  $(mark $panel_ok) Логин панели        ${YELLOW}→${NC} .env: H1CLOUD_PANEL_LOGIN + H1CLOUD_PANEL_PASSWORD"
typeline "  $(mark $rw_ok) Remnawave API       ${YELLOW}→${NC} .env: REMNAWAVE_API_URL + REMNAWAVE_API_TOKEN"
typeline "  $(mark $bind_host) Привязка CDN-sync   ${YELLOW}→${NC} bindings.json: remnawave_host_uuid"
typeline "  $(mark $bind_reality) Привязка REALITY   ${YELLOW}→${NC} bindings.json: profile_uuid + node_uuid + inbound_tag"
echo ""
if [ "$client_ok$pelican_ok$panel_ok$rw_ok$bind_host$bind_reality" = "111111" ]; then
  echo -e "${GREEN}${BOLD}   ✦ Всё заполнено — доступны все кнопки бота. ✦${NC}"
else
  echo -e "${YELLOW}${BOLD}   ⚠ Кнопки в боте видны все, но ❌-пункты выше при нажатии${NC}"
  echo -e "${YELLOW}${BOLD}     покажут подсказку, что и в каком файле дозаполнить.${NC}"
fi
echo ""
echo "════════════════════════════════════════════════════════════════════"
echo " Логи:               journalctl -u $SERVICE_NAME -f"
echo " Статус:              systemctl status $SERVICE_NAME"
echo " Перезапуск:          systemctl restart $SERVICE_NAME"
echo " Ручная донастройка:  $BOT_DIR/.env  и  $BOT_DIR/bindings.json"
echo "                       (после правки — systemctl restart $SERVICE_NAME)"
echo " Мастер повторно:     $BOT_DIR/venv/bin/python3 $BOT_DIR/h1bot/setup_wizard.py"
echo "════════════════════════════════════════════════════════════════════"
