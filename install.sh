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
TOTAL_STEPS=5
CURRENT_STEP=0

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; MAGENTA='\033[0;35m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

info()    { echo -e "${GREEN}[*]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
fail()    { echo -e "${RED}[x]${NC} $1"; exit 1; }
success() { echo -e "  ${GREEN}✔${NC} $1"; }

rule() { echo -e "${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

# spin PID "надпись" — крутит спиннер, пока фоновый процесс с этим PID жив
spin() {
  local pid=$1 label=$2 frames='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏' i=0
  while kill -0 "$pid" 2>/dev/null; do
    i=$(((i + 1) % ${#frames}))
    printf "\r  ${CYAN}%s${NC} %s" "${frames:$i:1}" "$label"
    sleep 0.1
  done
  printf "\r%*s\r" "$((${#label} + 6))" ""
}

# draw_bar N TOTAL — полоска прогресса вида [██████░░░░] 60%
# (репит через printf '%.0s', не tr — некоторые tr бьют многобайтовый UTF-8 на отдельные байты и портят вывод)
draw_bar() {
  local n=$1 total=$2 width=28
  local filled=$(( n * width / total )) empty
  empty=$(( width - filled ))
  local bar=""
  [ "$filled" -gt 0 ] && bar+=$(printf '█%.0s' $(seq 1 "$filled"))
  [ "$empty" -gt 0 ] && bar+=$(printf '░%.0s' $(seq 1 "$empty"))
  printf "  ${CYAN}[%s]${NC} ${BOLD}%3d%%${NC}\n" "$bar" "$(( n * 100 / total ))"
}

# step "заголовок" "зачем это нужно, понятным языком" — заголовок шага + бар
step() {
  CURRENT_STEP=$((CURRENT_STEP + 1))
  echo ""
  rule
  echo -e "${BOLD}Шаг $CURRENT_STEP/$TOTAL_STEPS${NC} — $1"
  draw_bar "$CURRENT_STEP" "$TOTAL_STEPS"
  [ -n "$2" ] && echo -e "  ${YELLOW}ℹ${NC}  ${DIM}$2${NC}"
  echo ""
}

# run_bg "лог-файл" "надпись спиннера" -- команда... — фон + спиннер + проверка кода возврата
run_bg() {
  local logfile=$1 label=$2; shift 2
  "$@" >"$logfile" 2>&1 &
  local pid=$!
  spin "$pid" "$label"
  wait "$pid"
}

if [ "$EUID" -ne 0 ]; then
  fail "Запусти установщик от root (sudo bash install.sh)."
fi

echo ""
echo -e "${CYAN}${BOLD}   🛸  H1-B0t-auto — установка${NC}"
echo -e "${DIM}   Каталог: $BOT_DIR${NC}"

# ── 1. Системные пакеты ─────────────────────────────────────────────────
if command -v apt-get >/dev/null 2>&1; then
  PKG_LOG=/tmp/h1bot-install-packages.log
  export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
  step "Системные пакеты (python3, venv, pip)" \
    "Это стандартные пакеты из официального репозитория дистрибутива — без них любой Python-скрипт на сервере не запустится, ничего специфичного для бота тут нет."
  if ! run_bg "$PKG_LOG" "apt-get update + install python3/venv/pip..." bash -c "apt-get update -qq && apt-get install -y -qq python3 python3-venv python3-pip"; then
    fail "Не удалось поставить системные пакеты — смотри лог: $PKG_LOG"
  fi
elif command -v dnf >/dev/null 2>&1; then
  step "Системные пакеты (python3, venv, pip)" "Стандартные пакеты дистрибутива, нужны для запуска Python."
  PKG_LOG=/tmp/h1bot-install-packages.log
  if ! run_bg "$PKG_LOG" "dnf install python3/pip/virtualenv..." dnf install -y -q python3 python3-pip python3-virtualenv; then
    fail "Не удалось поставить системные пакеты — смотри лог: $PKG_LOG"
  fi
elif command -v yum >/dev/null 2>&1; then
  step "Системные пакеты (python3, venv, pip)" "Стандартные пакеты дистрибутива, нужны для запуска Python."
  PKG_LOG=/tmp/h1bot-install-packages.log
  if ! run_bg "$PKG_LOG" "yum install python3/pip/virtualenv..." yum install -y -q python3 python3-pip python3-virtualenv; then
    fail "Не удалось поставить системные пакеты — смотри лог: $PKG_LOG"
  fi
else
  fail "Не нашёл apt-get/dnf/yum — установи python3, python3-venv, python3-pip вручную и перезапусти скрипт."
fi
success "Системные пакеты готовы"

# ── 2. venv ──────────────────────────────────────────────────────────────
step "Изолированное окружение (venv)" \
  "venv — это отдельная песочница для Python-библиотек бота внутри его же папки, чтобы они не конфликтовали с другими программами на сервере. Ничего не трогает системный Python."
if [ ! -d "$BOT_DIR/venv" ]; then
  python3 -m venv "$BOT_DIR/venv"
  success "venv создан в $BOT_DIR/venv"
else
  success "venv уже существует — переиспользую"
fi

# ── 3. Python-зависимости ────────────────────────────────────────────────
step "Библиотеки бота (requests, playwright)" \
  "requests — обычные HTTP-запросы к Telegram/h1cloud/Remnawave API. playwright — headless-браузер, нужен ТОЛЬКО кнопке «Создать новый конфиг» (эмулирует клик в панели, там нет API для этого действия)."
DEPS_LOG=/tmp/h1bot-install-deps.log
if ! run_bg "$DEPS_LOG" "ставлю зависимости из requirements.txt..." "$BOT_DIR/venv/bin/pip" install -q --upgrade pip -r "$BOT_DIR/requirements.txt"; then
  fail "Не удалось поставить Python-зависимости — смотри лог: $DEPS_LOG"
fi
success "Зависимости установлены"

# ── интерактивный мастер настройки (без прогресс-бара — тут нужен ввод) ──
if [ ! -f "$BOT_DIR/.env.example" ]; then
  fail ".env.example не найден рядом со скриптом — что-то не так с репозиторием."
fi
echo ""
rule
echo -e "${BOLD}Мастер настройки${NC} — сейчас спросит токены/ключи и объяснит, зачем нужен каждый."
echo -e "${DIM}Enter без ввода = пропустить пункт, потом можно дозаполнить вручную.${NC}"
rule
echo ""
"$BOT_DIR/venv/bin/python3" "$BOT_DIR/h1bot/setup_wizard.py"

# ── 4. Chromium для Playwright — только если настроена браузерная автоматизация ──
step "Chromium для Playwright" \
  "Нужен только кнопке «Создать новый конфиг» (браузерный клик в панели h1cloud). Если логин панели не задан — шаг просто пропускается, кнопка при нажатии подскажет, чего не хватает."
if grep -q "^H1CLOUD_PANEL_LOGIN=.\+" "$BOT_DIR/.env" 2>/dev/null; then
  CHROME_LOG=/tmp/h1bot-install-playwright.log
  if run_bg "$CHROME_LOG" "скачиваю Chromium (~300 МБ, один раз)..." "$BOT_DIR/venv/bin/playwright" install --with-deps chromium; then
    success "Chromium установлен"
  else
    warn "Не удалось поставить Chromium автоматически (лог: $CHROME_LOG) — выполни вручную: $BOT_DIR/venv/bin/playwright install --with-deps chromium"
  fi
else
  success "Логин панели не задан — пропущено (это нормально, не ошибка)"
fi

# ── 5. systemd ───────────────────────────────────────────────────────────
step "systemd-сервис ${SERVICE_NAME}" \
  "Чтобы бот запускался сам при старте сервера и сам перезапускался, если упадёт (Restart=always) — без этого пришлось бы держать терминал открытым вручную."
sed "s#{{BOT_DIR}}#${BOT_DIR}#g" "$BOT_DIR/systemd/h1-b0t-auto.service.template" > "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null
systemctl restart "$SERVICE_NAME"
sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
  success "Сервис запущен"
else
  warn "Сервис не запустился — смотри: journalctl -u $SERVICE_NAME -n 50"
fi

# ── Итоговый чек-лист: что настроено для полного функционала ────────────
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
rule
echo " Логи бота:           journalctl -u $SERVICE_NAME -f"
echo " Статус:              systemctl status $SERVICE_NAME"
echo " Перезапуск:          systemctl restart $SERVICE_NAME"
echo " Ручная донастройка:  $BOT_DIR/.env  и  $BOT_DIR/bindings.json"
echo "                       (после правки — systemctl restart $SERVICE_NAME)"
echo " Мастер повторно:     $BOT_DIR/venv/bin/python3 $BOT_DIR/h1bot/setup_wizard.py"
rule
