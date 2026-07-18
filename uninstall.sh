#!/usr/bin/env bash
# H1-B0t-auto — деинсталлятор.
#
# По умолчанию: останавливает и убирает systemd-сервис, снимает venv и
# кэш Chromium (playwright) — освобождает диск. .env/bindings.json (в них
# реальные API-ключи и пароли) и код бота НЕ трогает, чтобы можно было
# переустановить (sudo bash install.sh) без повторного ввода кредов.
#
# Флаги:
#   -y, --yes            не спрашивать подтверждение
#   --wipe-secrets       дополнительно удалить .env и bindings.json
#   --remove-dir         дополнительно снести всю папку бота целиком
#                        (подразумевает venv + секреты — деться им некуда,
#                        они внутри этой же папки)
#
# Примеры:
#   sudo bash uninstall.sh                              # мягко: только сервис+venv
#   sudo bash uninstall.sh --wipe-secrets                # + стереть ключи/пароли
#   sudo bash uninstall.sh --remove-dir -y               # полностью, без вопросов
set -e

BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="h1-b0t-auto"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
info()    { echo -e "${GREEN}[*]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
fail()    { echo -e "${RED}[x]${NC} $1"; exit 1; }
success() { echo -e "  ${GREEN}✔${NC} $1"; }
rule()    { echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

if [ "$EUID" -ne 0 ]; then
  fail "Запусти от root (sudo bash uninstall.sh)."
fi

ASSUME_YES=0
WIPE_SECRETS=0
REMOVE_DIR=0
for arg in "$@"; do
  case "$arg" in
    -y|--yes) ASSUME_YES=1 ;;
    --wipe-secrets) WIPE_SECRETS=1 ;;
    --remove-dir) REMOVE_DIR=1; WIPE_SECRETS=1 ;;
    *) warn "Неизвестный флаг: $arg (см. комментарий в начале скрипта)" ;;
  esac
done

echo ""
echo -e "${RED}${BOLD}   🗑  H1-B0t-auto — удаление${NC}"
echo -e "${DIM}   Каталог: $BOT_DIR${NC}"
echo ""
echo "Будет сделано:"
echo "  • остановлен и отключён systemd-сервис ${SERVICE_NAME}"
echo "  • удалён venv/ (~python-зависимости) и кэш Chromium (playwright)"
if [ "$WIPE_SECRETS" = "1" ]; then
  echo -e "  • ${RED}удалены .env и bindings.json (реальные API-ключи и пароли!)${NC}"
else
  echo -e "  • ${GREEN}.env и bindings.json НЕ трогаю${NC} — можно переустановить без повторного ввода кредов"
fi
if [ "$REMOVE_DIR" = "1" ]; then
  echo -e "  • ${RED}снесена вся папка бота целиком: $BOT_DIR${NC}"
fi
echo ""

if [ "$ASSUME_YES" != "1" ]; then
  read -r -p "Продолжить? Действие необратимо [y/N]: " answer
  case "$answer" in
    y|Y|yes|Yes|Д|д|да|Да) ;;
    *) info "Отменено."; exit 0 ;;
  esac
fi

rule
info "Останавливаю сервис..."
systemctl stop "$SERVICE_NAME" 2>/dev/null || true
systemctl disable "$SERVICE_NAME" 2>/dev/null || true
rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
success "Сервис остановлен и убран"

if [ -d "$BOT_DIR/venv" ]; then
  rm -rf "$BOT_DIR/venv"
  success "venv удалён"
fi
if [ -d "$HOME/.cache/ms-playwright" ]; then
  rm -rf "$HOME/.cache/ms-playwright"
  success "Кэш Chromium (playwright) удалён"
fi

if [ "$WIPE_SECRETS" = "1" ]; then
  rm -f "$BOT_DIR/.env" "$BOT_DIR/bindings.json"
  success "Секреты (.env, bindings.json) удалены"
fi

if [ "$REMOVE_DIR" = "1" ]; then
  rule
  info "Удаляю папку бота целиком: $BOT_DIR"
  cd /
  rm -rf "$BOT_DIR"
  success "Готово — от H1-B0t-auto на этом сервере ничего не осталось"
else
  echo ""
  rule
  success "Готово."
  echo " Папка бота осталась: $BOT_DIR"
  [ "$WIPE_SECRETS" = "1" ] || echo " Креды в .env/bindings.json сохранены — переустановка: sudo bash install.sh"
  echo " Снести и её:          sudo bash uninstall.sh --remove-dir"
  rule
fi
